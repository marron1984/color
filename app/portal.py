"""企業ポータル／候補者ポータル用のデータ整形（プライバシー配慮）.

- 企業ポータル: クライアントが自社求人に提案された候補を確認する。
  個人が特定できる連絡先・氏名は伏せ、興味あり/見送りを返せる。
- 候補者ポータル: 候補者が自分に提案された求人を確認し、応募意思を返せる。

いずれも認証基盤の代わりに推測困難なトークン付きリンクでアクセスする。
"""
from __future__ import annotations

from typing import Any

from app import verification


def masked_name(name: str) -> str:
    """氏名を伏せた表示名（例: 「山下 玲」→「山下 ○○」）."""
    name = (name or "").strip()
    if not name:
        return "候補者"
    parts = name.split()
    if len(parts) >= 2:
        return f"{parts[0]} ○○"
    # スペースなし: 先頭1文字＋伏字
    return name[0] + "○" * max(1, len(name) - 1)


def public_candidate(match: Any) -> dict[str, Any]:
    """企業ポータル向けの候補サマリ（連絡先・氏名・住所は伏せる）."""
    t = match.talent
    langs = [l.get("name") for l in (t.languages or []) if l.get("name")]
    skills = [
        {"name": s.get("name"), "level": s.get("level", 1)}
        for s in (t.skills or []) if s.get("name")
    ]
    return {
        "match_id": match.id,
        "display_name": masked_name(t.name),
        "type_os": t.type_os or "",
        "experience_years": t.experience_years or 0,
        "nationality": t.nationality or "",
        "visa_status": t.visa_status or "",
        "languages": langs,
        "skills": skills,
        "score": match.score,
        "reason": match.reason or "",
        "breakdown": match.breakdown or {},
        "status": match.status,
        "client_interest": match.client_interest or "",
        # 検証サマリはスコア・レベルのみ（詳細な証跡は出さない）
        "trust": _trust_summary(t),
    }


def _trust_summary(talent: Any) -> dict[str, Any]:
    """企業ポータル向けに検証サマリ（スコア・レベル・相違有無）だけ返す。"""
    tr = verification.compute_trust(getattr(talent, "verifications", []) or [])
    return {
        "score": tr["score"],
        "level": tr["level"],
        "level_label": tr["level_label"],
        "has_mismatch": tr["has_mismatch"],
    }


def public_job(job: Any, include_client: bool = True) -> dict[str, Any]:
    """候補者ポータル向けの求人サマリ（社内メモは出さない）."""
    return {
        "job_id": job.id,
        "title": job.title,
        "client_name": (job.client.name if (include_client and job.client) else ""),
        "country": job.country or "",
        "location": job.location or "",
        "offered_salary": job.offered_salary or 0,
        "currency": job.currency or "JPY",
        "employment_type": job.employment_type or "",
        "working_hours": job.working_hours or "",
        "holidays": job.holidays or "",
        "benefits": job.benefits or "",
        "requirements": job.requirements or "",
        "ideal_candidate": job.ideal_candidate or "",
        "description": job.description or "",
        "visa_support": bool(job.visa_support),
        "required_languages": [
            l.get("name") for l in (job.required_languages or []) if l.get("name")
        ],
    }
