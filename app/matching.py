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
WEIGHTS: dict[str, float] = {
    "skill": 0.40,
    "salary": 0.20,
    "type": 0.15,
    "work_style": 0.10,
    "location": 0.10,
    "availability": 0.05,
}

# 観点の日本語ラベル（UI 表示用）。
LABELS: dict[str, str] = {
    "skill": "スペックスキル",
    "salary": "待遇条件",
    "type": "タイプ(OS)",
    "work_style": "勤務形態",
    "location": "所在地",
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


def _salary_score(job: Any, talent: Any) -> Component:
    """提示待遇が希望待遇を満たすか."""
    offered = job.offered_salary or 0
    desired = talent.desired_salary or 0
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


def _location_score(job: Any, talent: Any) -> Component:
    """所在地の一致（オンライン勤務なら不問）."""
    if (job.work_style or "") == "online":
        return Component("location", LABELS["location"], 1.0, WEIGHTS["location"], "オンライン勤務")
    j = (job.location or "").strip()
    t = (talent.location or "").strip()
    if not j or not t:
        return Component("location", LABELS["location"], 0.6, WEIGHTS["location"], "所在地未設定")
    if j == t:
        return Component("location", LABELS["location"], 1.0, WEIGHTS["location"], f"一致: {j}")
    return Component("location", LABELS["location"], 0.4, WEIGHTS["location"], f"求人{j} / 人材{t}")


def _availability_score(job: Any, talent: Any) -> Component:
    """稼働可否."""
    a = (talent.availability or "available").strip()
    mapping = {"available": (1.0, "即稼働可"), "assigned": (0.2, "稼働中"), "unavailable": (0.0, "稼働不可")}
    score, detail = mapping.get(a, (0.5, a))
    return Component("availability", LABELS["availability"], score, WEIGHTS["availability"], detail)


def score_talent(job: Any, talent: Any) -> MatchResult:
    """求人 1 件 × 人材 1 名のマッチングスコアを算出."""
    components = [
        _skill_score(job, talent),
        _salary_score(job, talent),
        _type_score(job, talent),
        _work_style_score(job, talent),
        _location_score(job, talent),
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
