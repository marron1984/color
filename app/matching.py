"""スコアリング・マッチングエンジン.

求人票 (Job) に対して登録人材 (Talent) の適合度を 0-100 で算出する。
PDF「マッチング業務」の観点に対応:
  - スペックスキル   -> skill
  - 待遇条件         -> salary
  - タイプ(OS)       -> type
  - 面接調整/勤務形態 -> work_style
  - （所在地）        -> location
  - （稼働可否）      -> availability
LLM を使わなくても単体で動作する、決定論的なアルゴリズム。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# 各観点の重み（合計 = 1.0）。運用に合わせて調整可能。
# 海外人材紹介向けに「対応言語」「勤務国」を重視した配分。
WEIGHTS: dict[str, float] = {
    "skill": 0.30,
    "language": 0.20,
    "salary": 0.15,
    "country": 0.15,
    "type": 0.10,
    "work_style": 0.05,
    "availability": 0.05,
}

# 観点の日本語ラベル（UI 表示用）。
LABELS: dict[str, str] = {
    "skill": "スキル・経験",
    "language": "対応言語",
    "salary": "待遇条件",
    "country": "勤務国",
    "type": "職種",
    "work_style": "勤務形態",
    "availability": "稼働可否",
}


@dataclass
class Component:
    """1 観点あたりのスコア明細."""

    key: str
    label: str
    score: float  # 0.0-1.0
    weight: float
    detail: str = ""

    @property
    def weighted(self) -> float:
        return self.score * self.weight


@dataclass
class MatchResult:
    """人材 1 名分のマッチング結果."""

    talent_id: int
    total: float  # 0-100
    components: list[Component] = field(default_factory=list)

    def breakdown(self) -> dict[str, Any]:
        """DB 保存 / API 応答用の辞書に変換."""
        return {
            "total": round(self.total, 1),
            "components": [
                {
                    "key": c.key,
                    "label": c.label,
                    "score": round(c.score * 100, 1),
                    "weight": c.weight,
                    "detail": c.detail,
                }
                for c in self.components
            ],
        }


def _skill_score(job: Any, talent: Any) -> Component:
    """必須スキルのカバー率とレベル充足度を評価."""
    required = job.required_skills or []
    if not required:
        return Component("skill", LABELS["skill"], 1.0, WEIGHTS["skill"], "必須スキル指定なし")

    talent_skills = {s.get("name"): int(s.get("level", 0)) for s in (talent.skills or [])}
    total_weight = 0.0
    got_weight = 0.0
    covered: list[str] = []
    missing: list[str] = []
    for req in required:
        name = req.get("name")
        weight = float(req.get("weight", 1) or 1)
        min_level = int(req.get("min_level", 1) or 1)
        total_weight += weight
        have = talent_skills.get(name)
        if have is None:
            missing.append(name)
            continue
        # レベル充足度: min_level 以上で満点、未満は比例。
        ratio = 1.0 if have >= min_level else max(0.0, have / max(min_level, 1))
        got_weight += weight * ratio
        covered.append(f"{name}(Lv{have})")

    score = got_weight / total_weight if total_weight else 1.0
    detail_parts = []
    if covered:
        detail_parts.append("充足: " + ", ".join(covered))
    if missing:
        detail_parts.append("不足: " + ", ".join(missing))
    return Component("skill", LABELS["skill"], score, WEIGHTS["skill"], " / ".join(detail_parts))


def _language_score(job: Any, talent: Any) -> Component:
    """必要言語のカバー率とレベル充足度を評価（海外人材紹介の要）."""
    required = job.required_languages or []
    if not required:
        return Component("language", LABELS["language"], 1.0, WEIGHTS["language"], "必要言語の指定なし")

    talent_langs = {l.get("name"): int(l.get("level", 0)) for l in (talent.languages or [])}
    total = len(required)
    got = 0.0
    covered: list[str] = []
    missing: list[str] = []
    for req in required:
        name = req.get("name")
        min_level = int(req.get("min_level", 1) or 1)
        have = talent_langs.get(name)
        if have is None:
            missing.append(name)
            continue
        ratio = 1.0 if have >= min_level else max(0.0, have / max(min_level, 1))
        got += ratio
        covered.append(f"{name}(Lv{have})")

    score = got / total if total else 1.0
    detail_parts = []
    if covered:
        detail_parts.append("対応: " + ", ".join(covered))
    if missing:
        detail_parts.append("不足: " + ", ".join(missing))
    return Component("language", LABELS["language"], score, WEIGHTS["language"], " / ".join(detail_parts))


def _country_score(job: Any, talent: Any) -> Component:
    """勤務国と本人の就労意向（希望勤務国）の適合."""
    country = (job.country or "").strip()
    desired = [c.strip() for c in (talent.desired_countries or []) if c and c.strip()]
    if not country:
        return Component("country", LABELS["country"], 0.6, WEIGHTS["country"], "勤務国の指定なし")
    if not desired:
        return Component("country", LABELS["country"], 0.6, WEIGHTS["country"], "希望勤務国の登録なし")
    if country in desired:
        return Component("country", LABELS["country"], 1.0, WEIGHTS["country"], f"{country}勤務を希望")
    return Component(
        "country", LABELS["country"], 0.2, WEIGHTS["country"],
        f"求人{country} / 希望{'・'.join(desired)}",
    )


def _salary_score(job: Any, talent: Any) -> Component:
    """提示待遇が希望待遇を満たすか.

    通貨(currency)が JPY 以外（海外求人）の場合は、希望年収(万円)との
    単純比較ができないため、参考値として高めの中立スコアを返す。
    """
    offered = job.offered_salary or 0
    desired = talent.desired_salary or 0
    currency = (getattr(job, "currency", "JPY") or "JPY").strip()

    if currency != "JPY":
        detail = f"海外給与: {offered:,} {currency}（通貨差のため参考値）"
        return Component("salary", LABELS["salary"], 0.85, WEIGHTS["salary"], detail)

    if desired == 0 or offered == 0:
        return Component("salary", LABELS["salary"], 0.7, WEIGHTS["salary"], "待遇情報が不完全")
    if offered >= desired:
        return Component(
            "salary", LABELS["salary"], 1.0, WEIGHTS["salary"],
            f"提示{offered}万 ≧ 希望{desired}万",
        )
    # 希望に届かない場合は不足率に応じて減点（20%不足で 0 点）。
    gap = (desired - offered) / desired
    score = max(0.0, 1.0 - gap / 0.2)
    return Component(
        "salary", LABELS["salary"], score, WEIGHTS["salary"],
        f"提示{offered}万 < 希望{desired}万",
    )


def _type_score(job: Any, talent: Any) -> Component:
    """タイプ(OS) の一致."""
    j = (job.type_os or "").strip()
    t = (talent.type_os or "").strip()
    if not j or not t:
        return Component("type", LABELS["type"], 0.6, WEIGHTS["type"], "タイプ未設定")
    if j == t:
        return Component("type", LABELS["type"], 1.0, WEIGHTS["type"], f"一致: {j}")
    return Component("type", LABELS["type"], 0.3, WEIGHTS["type"], f"求人{j} / 人材{t}")


def _work_style_score(job: Any, talent: Any) -> Component:
    """勤務形態（オンライン/実地）の適合."""
    j = (job.work_style or "both").strip()
    t = (talent.work_style or "both").strip()
    if j == "both" or t == "both" or j == t:
        return Component("work_style", LABELS["work_style"], 1.0, WEIGHTS["work_style"], f"{j}/{t}")
    return Component("work_style", LABELS["work_style"], 0.2, WEIGHTS["work_style"], f"求人{j} / 人材{t}")


def _availability_score(job: Any, talent: Any) -> Component:
    """稼働可否."""
    a = (talent.availability or "available").strip()
    mapping = {"available": (1.0, "即勤務可"), "assigned": (0.2, "勤務中"), "unavailable": (0.0, "対応不可")}
    score, detail = mapping.get(a, (0.5, a))
    return Component("availability", LABELS["availability"], score, WEIGHTS["availability"], detail)


def score_talent(job: Any, talent: Any) -> MatchResult:
    """求人 1 件 × 人材 1 名のマッチングスコアを算出."""
    components = [
        _skill_score(job, talent),
        _language_score(job, talent),
        _salary_score(job, talent),
        _country_score(job, talent),
        _type_score(job, talent),
        _work_style_score(job, talent),
        _availability_score(job, talent),
    ]
    total = sum(c.weighted for c in components) * 100
    return MatchResult(talent_id=talent.id, total=total, components=components)


def rank_talents(job: Any, talents: list[Any], top_n: int | None = None) -> list[MatchResult]:
    """求人に対して人材群をスコア降順に並べる.

    稼働不可 (unavailable) の人材は候補から除外する。
    """
    results = [
        score_talent(job, t)
        for t in talents
        if (t.availability or "available") != "unavailable"
    ]
    results.sort(key=lambda r: r.total, reverse=True)
    if top_n is not None:
        results = results[:top_n]
    return results
