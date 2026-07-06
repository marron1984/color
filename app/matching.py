"""スコアリング・マッチングエンジン.

求人票 (Job) に対して登録人材 (Talent) の適合度を 0-100 で算出する。
7 観点（スキル・経験 / 対応言語 / 待遇条件 / 勤務国 / 職種 / 勤務形態 / 稼働可否）
を重み付き合算する、決定論的で説明可能なアルゴリズム。

精度向上のための工夫:
  - スキル: 完全一致に加え、関連スキル（近縁）を割り引いて部分評価
  - スキル: 最低レベル超過分を加点し、習熟度の高い人材を差別化
  - 経験年数をスキル観点に合算（ラベル「スキル・経験」に対応）
  - 職種: 近縁の職種（例: 店長↔副店長、調理長↔キッチン）を部分評価
LLM を使わなくても単体で動作する。
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

# 関連スキル群: 必須スキルが完全一致しなくても、同じ群のスキルがあれば
# 一定割合（RELATED_DISCOUNT）で部分的に評価する。飲食店の実務に即した近縁。
SKILL_FAMILIES: list[set[str]] = [
    {"接客", "ホール接客", "配膳", "レジ", "ドリンク", "多言語接客"},
    {"調理", "仕込み", "焼き場", "揚げ場", "盛り付け", "衛生管理"},
    {"店舗管理", "シフト管理", "在庫管理", "原価管理", "発注", "メニュー開発"},
    {"寿司握り", "魚さばき", "仕込み"},
    {"製菓", "パティシエ", "盛り付け"},
    {"ソムリエ", "ワイン", "ドリンク"},
    {"バリスタ", "ラテアート", "ドリンク"},
]
RELATED_DISCOUNT = 0.6  # 関連スキルは実効レベルを 60% に割り引く

# 経験年数を満点扱いする年数（これ以上で経験факターが 1.0）。
EXPERIENCE_FULL_YEARS = 8.0
# スキル観点における スキル一致 と 経験 の配合比。
SKILL_MATCH_RATIO = 0.9
EXPERIENCE_RATIO = 0.1

# 近縁の職種（同じ family 内は部分点）。
ROLE_FAMILIES: dict[str, set[str]] = {
    "management": {"店長", "副店長", "店舗管理", "マネージャー", "マネジャー", "SV", "エリアマネージャー"},
    "hall": {"ホール", "接客", "サービス", "ホールリーダー", "フロア"},
    "kitchen": {"キッチン", "調理", "調理長", "キッチン補助", "調理補助", "シェフ", "料理長"},
}
ROLE_FAMILY_SCORE = 0.6  # 同じ職種 family（別名称）の一致度


def _related_members(skill_name: str) -> set[str]:
    members: set[str] = set()
    for fam in SKILL_FAMILIES:
        if skill_name in fam:
            members |= fam
    members.discard(skill_name)
    return members


def _effective_level(req_name: str, talent_skills: dict[str, int]) -> tuple[float, str]:
    """必須スキルに対する実効レベルと種別(exact/related/none)を返す."""
    if req_name in talent_skills:
        return float(talent_skills[req_name]), "exact"
    related = _related_members(req_name)
    best = 0
    for name, lv in talent_skills.items():
        if name in related and lv > best:
            best = lv
    if best:
        return best * RELATED_DISCOUNT, "related"
    return 0.0, "none"


def _level_strength(effective_level: float, min_level: int) -> float:
    """実効レベルの充足度を 0-1 で返す.

    - 最低レベル未満: 比例（0.5 を上限係数として厳しめ）
    - 最低レベル以上: 0.8 を基準に、超過分で 1.0 まで加点（習熟度を差別化）
    """
    m = max(1, min_level)
    L = min(5.0, effective_level)
    if L >= m:
        if m >= 5:
            return 1.0
        return 0.8 + 0.2 * ((L - m) / (5 - m))
    return 0.5 * (L / m)


def _role_family(name: str) -> str | None:
    for fam, members in ROLE_FAMILIES.items():
        if name in members:
            return fam
    return None


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
    """必須スキルの充足度（関連スキル・習熟度差を考慮）と経験年数を評価.

    - 完全一致に加え、関連スキル（SKILL_FAMILIES）を割り引いて部分評価
    - 最低レベルを満たすだけでなく、超過した習熟度を加点して差別化
    - 経験年数を EXPERIENCE_RATIO の比率で合算（ラベル「スキル・経験」に対応）
    """
    talent_skills = {s.get("name"): int(s.get("level", 0)) for s in (talent.skills or [])}
    experience = float(getattr(talent, "experience_years", 0) or 0)
    exp_factor = min(1.0, experience / EXPERIENCE_FULL_YEARS) if EXPERIENCE_FULL_YEARS else 0.0

    required = job.required_skills or []
    if not required:
        # 必須スキル指定なしでも経験は評価に反映
        score = SKILL_MATCH_RATIO * 1.0 + EXPERIENCE_RATIO * exp_factor
        return Component("skill", LABELS["skill"], score, WEIGHTS["skill"],
                         f"必須スキル指定なし / 経験{experience:g}年")

    total_weight = 0.0
    got_weight = 0.0
    covered: list[str] = []
    related: list[str] = []
    missing: list[str] = []
    for req in required:
        name = req.get("name")
        weight = float(req.get("weight", 1) or 1)
        min_level = int(req.get("min_level", 1) or 1)
        total_weight += weight
        eff, kind = _effective_level(name, talent_skills)
        strength = _level_strength(eff, min_level)
        got_weight += weight * strength
        if kind == "exact":
            covered.append(f"{name}(Lv{int(talent_skills[name])})")
        elif kind == "related":
            related.append(f"{name}(関連)")
        else:
            missing.append(name)

    skill_match = got_weight / total_weight if total_weight else 1.0
    score = SKILL_MATCH_RATIO * skill_match + EXPERIENCE_RATIO * exp_factor

    detail_parts = []
    if covered:
        detail_parts.append("充足: " + ", ".join(covered))
    if related:
        detail_parts.append("近縁: " + ", ".join(related))
    if missing:
        detail_parts.append("不足: " + ", ".join(missing))
    detail_parts.append(f"経験{experience:g}年")
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
    """職種の一致（近縁の職種は部分点）."""
    j = (job.type_os or "").strip()
    t = (talent.type_os or "").strip()
    if not j or not t:
        return Component("type", LABELS["type"], 0.6, WEIGHTS["type"], "職種未設定")
    if j == t:
        return Component("type", LABELS["type"], 1.0, WEIGHTS["type"], f"一致: {j}")
    fj, ft = _role_family(j), _role_family(t)
    if fj and fj == ft:
        return Component("type", LABELS["type"], ROLE_FAMILY_SCORE, WEIGHTS["type"],
                         f"近縁: 求人{j} / 人材{t}")
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
