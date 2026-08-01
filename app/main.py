"""FastAPI アプリ本体（REST API + 静的フロントの配信）."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import ai, learning, matching, models, portal, resume, schemas, verification, visa
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
        _backfill_portal_tokens()
    except Exception as exc:  # noqa: BLE001 - 初期化失敗でもアプリは起動させる
        import logging

        logging.getLogger("uvicorn.error").warning("DB 初期化をスキップ: %s", exc)


def _backfill_portal_tokens() -> None:
    """既存レコード（列追加前に作成）に共有トークンを付与する。"""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        changed = False
        for model in (models.Client, models.Talent):
            for row in db.scalars(select(model).where(
                (model.portal_token == "") | (model.portal_token.is_(None))
            )).all():
                row.portal_token = models._token()
                changed = True
        if changed:
            db.commit()
    finally:
        db.close()


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


@app.post("/api/visa/assess")
def visa_assess(req: schemas.VisaAssessRequest) -> dict:
    """ビザ／在留資格の適格性を単体で判定する（国籍×勤務国×職種 等）。"""
    return visa.assess(
        nationality=req.nationality,
        country=req.country,
        role=req.role,
        experience_years=req.experience_years,
        japanese_level=req.japanese_level,
        held_status=req.held_status,
    )


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
def _talent_out(talent: models.Talent, verifs: list[models.Verification] | None = None) -> schemas.TalentOut:
    out = schemas.TalentOut.model_validate(talent)
    items = talent.verifications if verifs is None else verifs
    out.trust = verification.compute_trust(items)
    return out


@app.get("/api/talents", response_model=list[schemas.TalentOut])
def list_talents(db: Session = Depends(get_db)):
    talents = db.scalars(select(models.Talent).order_by(models.Talent.id.desc())).all()
    # 検証項目を一括ロードして人材ごとに集計（N+1 回避）
    verifs = db.scalars(select(models.Verification)).all()
    by_talent: dict[int, list[models.Verification]] = {}
    for v in verifs:
        by_talent.setdefault(v.talent_id, []).append(v)
    return [_talent_out(t, by_talent.get(t.id, [])) for t in talents]


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
    return _talent_out(talent, [])


@app.get("/api/talents/{talent_id}", response_model=schemas.TalentOut)
def get_talent(talent_id: int, db: Session = Depends(get_db)):
    talent = db.get(models.Talent, talent_id)
    if not talent:
        raise HTTPException(404, "人材が見つかりません")
    return _talent_out(talent)


@app.put("/api/talents/{talent_id}", response_model=schemas.TalentOut)
def update_talent(talent_id: int, payload: schemas.TalentCreate, db: Session = Depends(get_db)):
    talent = db.get(models.Talent, talent_id)
    if not talent:
        raise HTTPException(404, "人材が見つかりません")
    for key, value in payload.model_dump().items():
        setattr(talent, key, value)
    db.commit()
    db.refresh(talent)
    return _talent_out(talent)


@app.delete("/api/talents/{talent_id}", status_code=204)
def delete_talent(talent_id: int, db: Session = Depends(get_db)):
    talent = db.get(models.Talent, talent_id)
    if not talent:
        raise HTTPException(404, "人材が見つかりません")
    db.delete(talent)
    db.commit()


# --------------------------------------------------------------------------- #
# Verification（検証レイヤー）
# --------------------------------------------------------------------------- #
@app.get("/api/verifications/meta")
def verification_meta() -> dict:
    """検証項目の選択肢（カテゴリ・ステータス・方法）を返す。"""
    return {
        "categories": [
            {"key": k, "label": label, "weight": w}
            for k, label, w in verification.CATEGORIES
        ],
        "statuses": [
            {"key": k, "label": v} for k, v in verification.STATUS_LABELS.items()
        ],
        "methods": [
            {"key": k, "label": v} for k, v in verification.METHOD_LABELS.items()
        ],
    }


@app.get("/api/talents/{talent_id}/verifications")
def list_verifications(talent_id: int, db: Session = Depends(get_db)) -> dict:
    """人材の検証項目一覧と、検証スコア（信頼度サマリ）を返す。"""
    talent = db.get(models.Talent, talent_id)
    if not talent:
        raise HTTPException(404, "人材が見つかりません")
    items = db.scalars(
        select(models.Verification)
        .where(models.Verification.talent_id == talent_id)
        .order_by(models.Verification.id.desc())
    ).all()
    return {
        "trust": verification.compute_trust(items),
        "items": [schemas.VerificationOut.model_validate(v) for v in items],
    }


@app.post("/api/talents/{talent_id}/verifications",
          response_model=schemas.VerificationOut, status_code=201)
def create_verification(
    talent_id: int, payload: schemas.VerificationCreate, db: Session = Depends(get_db)
):
    talent = db.get(models.Talent, talent_id)
    if not talent:
        raise HTTPException(404, "人材が見つかりません")
    if payload.category not in verification.CATEGORY_KEYS:
        raise HTTPException(400, "カテゴリが不正です")
    if payload.status not in verification.STATUS_KEYS:
        raise HTTPException(400, "ステータスが不正です")
    v = models.Verification(talent_id=talent_id, **payload.model_dump())
    if v.status == "verified":
        v.verified_at = models._now()
    db.add(v)
    db.commit()
    db.refresh(v)
    return schemas.VerificationOut.model_validate(v)


@app.patch("/api/verifications/{verification_id}",
           response_model=schemas.VerificationOut)
def update_verification(
    verification_id: int, payload: schemas.VerificationUpdate, db: Session = Depends(get_db)
):
    v = db.get(models.Verification, verification_id)
    if not v:
        raise HTTPException(404, "検証項目が見つかりません")
    data = payload.model_dump(exclude_unset=True)
    if "category" in data and data["category"] not in verification.CATEGORY_KEYS:
        raise HTTPException(400, "カテゴリが不正です")
    if "status" in data and data["status"] not in verification.STATUS_KEYS:
        raise HTTPException(400, "ステータスが不正です")
    for key, value in data.items():
        setattr(v, key, value)
    # 確認済へ変わったら確認日時を記録、取り消したらクリア
    if "status" in data:
        v.verified_at = models._now() if v.status == "verified" else None
    db.commit()
    db.refresh(v)
    return schemas.VerificationOut.model_validate(v)


@app.delete("/api/verifications/{verification_id}", status_code=204)
def delete_verification(verification_id: int, db: Session = Depends(get_db)):
    v = db.get(models.Verification, verification_id)
    if not v:
        raise HTTPException(404, "検証項目が見つかりません")
    db.delete(v)
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
    emp_w = cand_w = None
    if req.use_learned:
        lw = learning.learned_weights(db.scalars(select(models.Match)).all())
        emp_w, cand_w = lw["emp"], lw["cand"]
    ranked = matching.rank_talents(job, talents, top_n=req.top_n,
                                   emp_weights=emp_w, cand_weights=cand_w)

    talent_by_id = {t.id: t for t in talents}
    # 検証項目を一括ロード（候補ごとの信頼度サマリ用）
    verifs = db.scalars(select(models.Verification)).all()
    verifs_by_talent: dict[int, list[models.Verification]] = {}
    for v in verifs:
        verifs_by_talent.setdefault(v.talent_id, []).append(v)
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
                visa=visa.assess_for_match(job, talent),
                trust=verification.compute_trust(verifs_by_talent.get(talent.id, [])),
            )
        )
    if req.persist:
        db.commit()
    return candidates


def _match_out(m: models.Match) -> schemas.MatchOut:
    mo = schemas.MatchOut.model_validate(m)
    mo.talent = schemas.TalentOut.model_validate(m.talent) if m.talent else None
    mo.job_title = m.job.title if m.job else None
    mo.client_name = m.job.client.name if (m.job and m.job.client) else None
    return mo


@app.get("/api/matches", response_model=list[schemas.MatchOut])
def list_all_matches(db: Session = Depends(get_db)):
    """保存済みマッチング（採用管理）を全件返す。"""
    matches = db.scalars(select(models.Match).order_by(models.Match.id.desc())).all()
    return [_match_out(m) for m in matches]


@app.post("/api/matches", response_model=schemas.MatchOut, status_code=201)
def create_match(payload: schemas.MatchCreate, db: Session = Depends(get_db)):
    """候補を採用管理（パイプライン）に保存する。"""
    job = db.get(models.Job, payload.job_id)
    talent = db.get(models.Talent, payload.talent_id)
    if not job or not talent:
        raise HTTPException(404, "求人または人材が見つかりません")
    existing = db.scalar(
        select(models.Match).where(
            models.Match.job_id == payload.job_id,
            models.Match.talent_id == payload.talent_id,
        )
    )
    if existing:
        return _match_out(existing)
    result = matching.score_talent(job, talent)
    breakdown = result.breakdown()
    reason, source = ai._template_reason(job, talent, breakdown), "scoring"
    match = models.Match(
        job_id=job.id, talent_id=talent.id, score=round(result.total, 1),
        breakdown=breakdown, reason=reason, source=source, status="proposed",
    )
    db.add(match)
    db.commit()
    db.refresh(match)
    return _match_out(match)


@app.get("/api/jobs/{job_id}/matches", response_model=list[schemas.MatchOut])
def list_matches(job_id: int, db: Session = Depends(get_db)):
    matches = db.scalars(
        select(models.Match)
        .where(models.Match.job_id == job_id)
        .order_by(models.Match.score.desc())
    ).all()
    return [_match_out(m) for m in matches]


@app.patch("/api/matches/{match_id}", response_model=schemas.MatchOut)
def update_match(match_id: int, payload: schemas.MatchUpdate, db: Session = Depends(get_db)):
    match = db.get(models.Match, match_id)
    if not match:
        raise HTTPException(404, "マッチングが見つかりません")
    if payload.status is not None:
        valid = {"proposed", "interview", "offer", "hired", "rejected"}
        if payload.status not in valid:
            raise HTTPException(400, f"status は {valid} のいずれか")
        match.status = payload.status
        if payload.status == "hired" and match.hired_at is None:
            import datetime as _dt
            match.hired_at = _dt.datetime.now(_dt.timezone.utc)
    if payload.retention is not None:
        if payload.retention not in {"", "active", "left"}:
            raise HTTPException(400, "retention は active / left / 空")
        match.retention = payload.retention
    if payload.retention_days is not None:
        match.retention_days = int(payload.retention_days)
    if payload.left_reason is not None:
        match.left_reason = payload.left_reason
    db.commit()
    db.refresh(match)
    return _match_out(match)


@app.delete("/api/matches/{match_id}", status_code=204)
def delete_match(match_id: int, db: Session = Depends(get_db)):
    match = db.get(models.Match, match_id)
    if not match:
        raise HTTPException(404, "マッチングが見つかりません")
    db.delete(match)
    db.commit()


@app.get("/api/learning")
def get_learning(db: Session = Depends(get_db)) -> dict:
    """アウトカム学習の状況（指標・重要度・学習重み）を返す。"""
    matches = db.scalars(select(models.Match)).all()
    return {
        "metrics": learning.compute_metrics(matches),
        "learned": learning.learned_weights(matches),
    }


# --------------------------------------------------------------------------- #
# ポータル（企業ポータル / 候補者ポータル）— トークン付き共有リンクでアクセス
# --------------------------------------------------------------------------- #
def _client_by_token(token: str, db: Session) -> models.Client:
    if not token:
        raise HTTPException(404, "リンクが無効です")
    c = db.scalar(select(models.Client).where(models.Client.portal_token == token))
    if not c:
        raise HTTPException(404, "リンクが無効です")
    return c


def _talent_by_token(token: str, db: Session) -> models.Talent:
    if not token:
        raise HTTPException(404, "リンクが無効です")
    t = db.scalar(select(models.Talent).where(models.Talent.portal_token == token))
    if not t:
        raise HTTPException(404, "リンクが無効です")
    return t


@app.get("/api/portal/client/{token}")
def portal_client(token: str, db: Session = Depends(get_db)) -> dict:
    """企業ポータル: 自社求人に提案された候補を（個人情報を伏せて）確認する。"""
    client = _client_by_token(token, db)
    jobs = db.scalars(
        select(models.Job).where(models.Job.client_id == client.id)
        .order_by(models.Job.id.desc())
    ).all()
    job_out = []
    for job in jobs:
        matches = db.scalars(
            select(models.Match).where(models.Match.job_id == job.id)
            .order_by(models.Match.score.desc())
        ).all()
        job_out.append({
            "job": portal.public_job(job, include_client=False),
            "candidates": [portal.public_candidate(m) for m in matches],
        })
    return {"client": {"name": client.name}, "jobs": job_out}


@app.post("/api/portal/client/{token}/matches/{match_id}")
def portal_client_interest(
    token: str, match_id: int, payload: schemas.PortalInterest,
    db: Session = Depends(get_db),
) -> dict:
    """企業ポータル: 候補への反応（興味あり/見送り）を記録する。"""
    client = _client_by_token(token, db)
    match = db.get(models.Match, match_id)
    if not match or not match.job or match.job.client_id != client.id:
        raise HTTPException(404, "対象が見つかりません")
    if payload.interest not in {"", "interested", "passed"}:
        raise HTTPException(400, "interest は interested / passed / 空")
    match.client_interest = payload.interest
    # 興味ありは選考を面接段階へ進める（未進行のときのみ）
    if payload.interest == "interested" and match.status == "proposed":
        match.status = "interview"
    db.commit()
    return {"ok": True, "client_interest": match.client_interest, "status": match.status}


@app.get("/api/portal/talent/{token}")
def portal_talent(token: str, db: Session = Depends(get_db)) -> dict:
    """候補者ポータル: 自分に提案された求人を確認する。"""
    talent = _talent_by_token(token, db)
    matches = db.scalars(
        select(models.Match).where(models.Match.talent_id == talent.id)
        .order_by(models.Match.score.desc())
    ).all()
    offers = []
    for m in matches:
        if not m.job:
            continue
        offers.append({
            "match_id": m.id,
            "score": m.score,
            "reason": m.reason or "",
            "status": m.status,
            "candidate_interest": m.candidate_interest or "",
            **portal.public_job(m.job, include_client=True),
        })
    return {
        "talent": {"name": talent.name, "availability": talent.availability},
        "offers": offers,
    }


@app.post("/api/portal/talent/{token}/matches/{match_id}")
def portal_talent_interest(
    token: str, match_id: int, payload: schemas.PortalInterest,
    db: Session = Depends(get_db),
) -> dict:
    """候補者ポータル: 求人への反応（応募したい/見送り）を記録する。"""
    talent = _talent_by_token(token, db)
    match = db.get(models.Match, match_id)
    if not match or match.talent_id != talent.id:
        raise HTTPException(404, "対象が見つかりません")
    if payload.interest not in {"", "interested", "declined"}:
        raise HTTPException(400, "interest は interested / declined / 空")
    match.candidate_interest = payload.interest
    db.commit()
    return {"ok": True, "candidate_interest": match.candidate_interest}


# --------------------------------------------------------------------------- #
# 静的フロント配信（最後にマウント）
# --------------------------------------------------------------------------- #
@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/portal")
def portal_page():
    """企業／候補者ポータル（トークンはクエリで受け取り、JS で読み込む）。"""
    return FileResponse(STATIC_DIR / "portal.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
