"""AI 推薦理由レイヤー.

スコアリング結果の上位候補に対して、なぜその人材が求人に適合するのかを
自然文で説明する「推薦理由」を生成する。

- 環境変数 ANTHROPIC_API_KEY があれば Claude API を呼び出す。
- 無い / 失敗した場合は、スコア明細からテンプレート文を生成する（オフライン動作）。

これにより API キー無しでもシステム全体が動作しつつ、キーがあれば
より説得力のある自然文の推薦が得られる（スコアリング＋LLM 併用）。
"""
from __future__ import annotations

import json
import os
from typing import Any

import httpx

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
# 最新世代の Claude モデル。
DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")


def is_llm_enabled() -> bool:
    """Claude API が利用可能か（API キーが設定されているか）."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _talent_summary(talent: Any) -> dict[str, Any]:
    return {
        "氏名": talent.name,
        "職種": talent.type_os,
        "スキル": talent.skills,
        "経験年数": talent.experience_years,
        "希望年収_万円": talent.desired_salary,
        "勤務形態": talent.work_style,
        "所在地": talent.location,
        "稼働状況": talent.availability,
        "国籍": talent.nationality,
        "対応言語": talent.languages,
        "在留資格": talent.visa_status,
        "希望勤務国": talent.desired_countries,
        "プロフィール": talent.profile,
    }


def _job_summary(job: Any) -> dict[str, Any]:
    return {
        "求人タイトル": job.title,
        "職種": job.type_os,
        "必須スキル": job.required_skills,
        "提示年収": job.offered_salary,
        "通貨": job.currency,
        "勤務形態": job.work_style,
        "勤務国": job.country,
        "必要言語": job.required_languages,
        "ビザサポート": job.visa_support,
        "説明": job.description,
    }


def _template_reason(job: Any, talent: Any, breakdown: dict[str, Any]) -> str:
    """LLM を使わないフォールバックの推薦理由（スコア明細ベース）."""
    comps = sorted(breakdown.get("components", []), key=lambda c: c["score"], reverse=True)
    strong = [c for c in comps if c["score"] >= 70]
    weak = [c for c in comps if c["score"] < 50]
    parts = [f"総合適合度 {breakdown.get('total', 0)} 点。"]
    emp = breakdown.get("employer_fit")
    cand = breakdown.get("candidate_fit")
    if emp is not None and cand is not None:
        parts.append(f"企業ニーズ適合 {emp} × 本人希望適合 {cand}。")
    if strong:
        parts.append(
            "強み: " + "、".join(f"{c['label']}（{c['detail']}）" for c in strong if c["detail"])
        )
    if weak:
        parts.append(
            "留意点: " + "、".join(f"{c['label']}（{c['detail']}）" for c in weak if c["detail"])
        )
    return " ".join(parts)


def generate_reason(job: Any, talent: Any, breakdown: dict[str, Any]) -> tuple[str, str]:
    """推薦理由を生成し、(理由文, source) を返す.

    source は "ai"（Claude 生成）または "scoring"（テンプレート）。
    """
    if not is_llm_enabled():
        return _template_reason(job, talent, breakdown), "scoring"

    prompt = (
        "あなたは人材紹介会社のキャリアアドバイザーです。"
        "以下の求人票と候補人材、およびシステムが算出した適合度スコアを踏まえ、"
        "この人材を企業に推薦する理由を日本語で簡潔に（120字程度、2〜3文）述べてください。"
        "スコアの強みと留意点の双方に触れ、誇張は避けてください。\n\n"
        f"【求人票】\n{json.dumps(_job_summary(job), ensure_ascii=False, indent=2)}\n\n"
        f"【候補人材】\n{json.dumps(_talent_summary(talent), ensure_ascii=False, indent=2)}\n\n"
        f"【適合度スコア】\n{json.dumps(breakdown, ensure_ascii=False, indent=2)}\n\n"
        "推薦理由のみを出力してください。"
    )
    try:
        resp = httpx.post(
            ANTHROPIC_API_URL,
            headers={
                "x-api-key": os.environ["ANTHROPIC_API_KEY"],
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": DEFAULT_MODEL,
                "max_tokens": 400,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        text = "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        ).strip()
        if text:
            return text, "ai"
    except Exception:  # noqa: BLE001 - LLM 失敗時は必ずフォールバック
        pass
    return _template_reason(job, talent, breakdown), "scoring"
