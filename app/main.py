"""FastAPI アプリ本体（REST API + 静的フロントの配信）."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import ai, matching, models, resume, schemas
from app.database import IS_PERSISTENT, USING_EXTERNAL, get_db, init_db

app = FastAPI(
    title="人材マッチングシステム",
    description="店舗ニーズに応じて飲食店スタッフを AI（スコアリング＋LLM）でピックアップする管理システム",
    version="0.1.0",
)

STATIC_DIR = Path(__file__).parent / "static"


def _bootstrap() -> None:
    """テーブル作成とデモデータ投入.

    サーバーレス(Vercel 等)では ASGI lifespan が実行されない場合があるため、
    起動イベントではなくインポート時に実行する。失敗しても起動は継続する。
    """
    try:
        init_db()
        # デモデータの自動投入:
        #   - 既定: DB が空のときだけ投入する（外部 DB でも）。既に登録があれば何もしない。
        #   - SEED_DEMO=0 で無効化、=1 で明示的に有効化。
        seed_env = os.environ.get("SEED_DEMO")
        do_seed = seed_env != "0"
        if do_seed:
            from app.seed import seed_if_empty

            seed_if_empty()
    except Exception as exc:  # noqa: BLE001 - 初期化失敗でもアプリは起動させる
        import logging

        logging.getLogger("uvicorn.error").warning("DB 初期化をスキップ: %s", exc)


_bootstrap()


# --------------------------------------------------------------------------- #
# メタ / ヘルスチェック
# --------------------------------------------------------------------------- #
@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "llm_enabled": ai.is_llm_enabled(),
        "persistent": IS_PERSISTENT,       # False = 一時ストレージ（再起動で消える）
        "external_db": USING_EXTERNAL,
    }


@app.get("/api/stats")
def stats(db: Session = Depends(get_db)) -> dict:
    """ダッシュボード用の集計値を返す."""
    clients = db.scalars(select(models.Client)).all()
    talents = db.scalars(select(models.Talent)).all()
    jobs = db.scalars(select(models.Job)).all()
    matches = db.scalars(select(models.Match)).all()

    def tally(items, key) -> list[dict]:
        counts: dict[str, int] = {}
        for it in items:
            name = (key(it) or "").strip() or "未設定"
            counts[name] = counts.get(name, 0) + 1
        return sorted(
            ({"name": k, "count": v} for k, v in counts.items()),
            key=lambda x: (-x["count"], x["name"]),
        )

    return {
        "clients": {
            "total": len(clients),
            "new": sum(1 for c in clients if c.kind == "new"),
            "existing": sum(1 for c in clients if c.kind == "existing"),
        },
        "talents": {
            "total": len(talents),
            "available": sum(1 for t in talents if t.availability == "available"),
            "assigned": sum(1 for t in talents if t.availability == "assigned"),
            "unavailable": sum(1 for t in talents if t.availability == "unavailable"),
        },
        "jobs": {
            "total": len(jobs),
            "open": sum(1 for j in jobs if j.status == "open"),
            "overseas": sum(1 for j in jobs if (j.country or "日本") != "日本"),
            "headcount": sum(int(j.headcount or 0) for j in jobs),
        },
        "matches": {"total": len(matches)},
        "talent_by_type": tally(talents, lambda t: t.type_os),
        "talent_by_nationality": tally(talents, lambda t: t.nationality),
        "jobs_by_country": tally(jobs, lambda j: j.country or "日本"),
    }


# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #
@app.get("/api/clients", response_model=list[schemas.ClientOut])
def list_clients(db: Session = Depends(get_db)):
    return db.scalars(select(models.Client).order_by(models.Client.id.desc())).all()


@app.post("/api/clients/fetch-tabelog")
def fetch_tabelog(req: schemas.TabelogFetchRequest):
    """食べログの店舗 URL から店舗情報を取得し、フォームの下書きを返す（保存はしない）。"""
    from app import tabelog

    try:
        fields = tabelog.fetch_store(req.url)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:  # noqa: BLE001 - 取得失敗はまとめて 502 で通知
        raise HTTPException(
            502,
            f"食べログから取得できませんでした（{type(exc).__name__}）。"
            "URL やネットワーク環境をご確認ください。",
        )
    if not fields.get("name"):
        raise HTTPException(422, "店舗情報を抽出できませんでした。URL をご確認ください。")
    return {"fields": fields, "source": "tabelog"}


@app.post("/api/clients", response_model=schemas.ClientOut, status_code=201)
def create_client(payload: schemas.ClientCreate, db: Session = Depends(get_db)):
    client = models.Client(**payload.model_dump())
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


@app.put("/api/clients/{client_id}", response_model=schemas.ClientOut)
def update_client(client_id: int, payload: schemas.ClientCreate, db: Session = Depends(get_db)):
    client = db.get(models.Client, client_id)
    if not client:
        raise HTTPException(404, "店舗が見つかりません")
    for key, value in payload.model_dump().items():
        setattr(client, key, value)
    db.commit()
    db.refresh(client)
    return client


@app.delete("/api/clients/{client_id}", status_code=204)
def delete_client(client_id: int, db: Session = Depends(get_db)):
    client = db.get(models.Client, client_id)
    if not client:
        raise HTTPException(404, "クライアントが見つかりません")
    db.delete(client)
    db.commit()


# --------------------------------------------------------------------------- #
# Talent
# --------------------------------------------------------------------------- #
@app.get("/api/talents", response_model=list[schemas.TalentOut])
def list_talents(db: Session = Depends(get_db)):
    return db.scalars(select(models.Talent).order_by(models.Talent.id.desc())).all()


@app.post("/api/talents/parse-resume")
async def parse_resume(file: UploadFile = File(...)):
    """アップロードされた履歴書（PDF/画像/テキスト）から登録フォームの下書きを生成.

    保存はせず、フォームに自動入力するための項目のみを返す。
    """
    data = await file.read()
    if not data:
        raise HTTPException(400, "ファイルが空です")
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "ファイルが大きすぎます（10MB まで）")
    fields, source = resume.parse_resume(
        file.filename or "", file.content_type or "", data
    )
    return {"fields": fields, "source": source}


@app.post("/api/talents", response_model=schemas.TalentOut, status_code=201)
def create_talent(payload: schemas.TalentCreate, db: Session = Depends(get_db)):
    data = payload.model_dump()
    data["skills"] = [s for s in data.get("skills", [])]
    talent = models.Talent(**data)
    db.add(talent)
    db.commit()
    db.refresh(talent)
    return talent


@app.get("/api/talents/{talent_id}", response_model=schemas.TalentOut)
def get_talent(talent_id: int, db: Session = Depends(get_db)):
    talent = db.get(models.Talent, talent_id)
    if not talent:
        raise HTTPException(404, "人材が見つかりません")
    return talent


@app.put("/api/talents/{talent_id}", response_model=schemas.TalentOut)
def update_talent(talent_id: int, payload: schemas.TalentCreate, db: Session = Depends(get_db)):
    talent = db.get(models.Talent, talent_id)
    if not talent:
        raise HTTPException(404, "人材が見つかりません")
    for key, value in payload.model_dump().items():
        setattr(talent, key, value)
    db.commit()
    db.refresh(talent)
    return talent


@app.delete("/api/talents/{talent_id}", status_code=204)
def delete_talent(talent_id: int, db: Session = Depends(get_db)):
    talent = db.get(models.Talent, talent_id)
    if not talent:
        raise HTTPException(404, "人材が見つかりません")
    db.delete(talent)
    db.commit()


# --------------------------------------------------------------------------- #
# Job
# --------------------------------------------------------------------------- #
def _job_out(job: models.Job) -> schemas.JobOut:
    out = schemas.JobOut.model_validate(job)
    out.client_name = job.client.name if job.client else None
    return out


@app.get("/api/jobs", response_model=list[schemas.JobOut])
def list_jobs(db: Session = Depends(get_db)):
    jobs = db.scalars(select(models.Job).order_by(models.Job.id.desc())).all()
    return [_job_out(j) for j in jobs]


@app.post("/api/jobs", response_model=schemas.JobOut, status_code=201)
def create_job(payload: schemas.JobCreate, db: Session = Depends(get_db)):
    if not db.get(models.Client, payload.client_id):
        raise HTTPException(400, "指定されたクライアントが存在しません")
    job = models.Job(**payload.model_dump())
    db.add(job)
    db.commit()
    db.refresh(job)
    return _job_out(job)


@app.get("/api/jobs/{job_id}", response_model=schemas.JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(models.Job, job_id)
    if not job:
        raise HTTPException(404, "求人が見つかりません")
    return _job_out(job)


@app.put("/api/jobs/{job_id}", response_model=schemas.JobOut)
def update_job(job_id: int, payload: schemas.JobCreate, db: Session = Depends(get_db)):
    job = db.get(models.Job, job_id)
    if not job:
        raise HTTPException(404, "求人が見つかりません")
    if not db.get(models.Client, payload.client_id):
        raise HTTPException(400, "指定された店舗が存在しません")
    for key, value in payload.model_dump().items():
        setattr(job, key, value)
    db.commit()
    db.refresh(job)
    return _job_out(job)


@app.delete("/api/jobs/{job_id}", status_code=204)
def delete_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(models.Job, job_id)
    if not job:
        raise HTTPException(404, "求人が見つかりません")
    db.delete(job)
    db.commit()


# --------------------------------------------------------------------------- #
# マッチング（AI ピックアップ）
# --------------------------------------------------------------------------- #
@app.post("/api/jobs/{job_id}/match", response_model=list[schemas.MatchCandidate])
def run_match(
    job_id: int,
    req: schemas.RunMatchRequest,
    db: Session = Depends(get_db),
):
    """求人に対して登録人材をスコアリングし、上位候補を返す。

    use_llm=True かつ API キーがある場合は Claude で推薦理由を生成、
    それ以外はスコア明細からテンプレート理由を生成する。
    """
    job = db.get(models.Job, job_id)
    if not job:
        raise HTTPException(404, "求人が見つかりません")

    talents = db.scalars(select(models.Talent)).all()
    ranked = matching.rank_talents(job, talents, top_n=req.top_n)

    talent_by_id = {t.id: t for t in talents}
    candidates: list[schemas.MatchCandidate] = []
    for result in ranked:
        talent = talent_by_id[result.talent_id]
        breakdown = result.breakdown()
        if req.use_llm:
            reason, source = ai.generate_reason(job, talent, breakdown)
        else:
            reason, source = ai._template_reason(job, talent, breakdown), "scoring"

        if req.persist:
            match = models.Match(
                job_id=job.id,
                talent_id=talent.id,
                score=round(result.total, 1),
                breakdown=breakdown,
                reason=reason,
                source=source,
                status="proposed",
            )
            db.add(match)

        candidates.append(
            schemas.MatchCandidate(
                talent=schemas.TalentOut.model_validate(talent),
                score=round(result.total, 1),
                breakdown=breakdown,
                reason=reason,
                source=source,
            )
        )
    if req.persist:
        db.commit()
    return candidates


@app.get("/api/jobs/{job_id}/matches", response_model=list[schemas.MatchOut])
def list_matches(job_id: int, db: Session = Depends(get_db)):
    matches = db.scalars(
        select(models.Match)
        .where(models.Match.job_id == job_id)
        .order_by(models.Match.score.desc())
    ).all()
    out = []
    for m in matches:
        mo = schemas.MatchOut.model_validate(m)
        mo.talent = schemas.TalentOut.model_validate(m.talent) if m.talent else None
        out.append(mo)
    return out


@app.patch("/api/matches/{match_id}", response_model=schemas.MatchOut)
def update_match_status(
    match_id: int, payload: schemas.MatchStatusUpdate, db: Session = Depends(get_db)
):
    match = db.get(models.Match, match_id)
    if not match:
        raise HTTPException(404, "マッチングが見つかりません")
    valid = {"proposed", "interview", "offer", "hired", "rejected"}
    if payload.status not in valid:
        raise HTTPException(400, f"status は {valid} のいずれか")
    match.status = payload.status
    db.commit()
    db.refresh(match)
    mo = schemas.MatchOut.model_validate(match)
    mo.talent = schemas.TalentOut.model_validate(match.talent) if match.talent else None
    return mo


# --------------------------------------------------------------------------- #
# 静的フロント配信（最後にマウント）
# --------------------------------------------------------------------------- #
@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
