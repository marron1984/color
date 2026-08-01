"""スコアリング・マッチングエンジン（求人マッチングのノウハウを集約）.

大手求人プラットフォーム（Indeed / リクルート / LinkedIn 等）で実際に使われる
確立した手法を、学習データ不要の決定論アルゴリズムとして実装している。

採用している主な手法:
  1. 双方向レコメンド（reciprocal recommendation, LinkedIn）
     - 「企業が人材を求める度（employer→candidate）」と
       「人材がその求人を望む度（candidate→employer）」の両方を算出し、
       幾何平均で統合。片側だけ高くても総合は伸びない（＝実際に成立しやすい）。
  2. BM25 テキスト関連度（Indeed の検索ランキング）
     - 職務内容（求人）と人材プロフィールの文章一致を BM25 で評価。
       日本語は形態素解析なしで動くよう文字 bi-gram をトークンとする。
  3. スキル・タクソノミー展開（skill ontology）
     - 近縁スキルを割り引いて部分評価（取りこぼし防止）。
  4. 必須要件ゲート（must-have knockout）
     - 重要度「高」の必須スキル欠落は総合を強く減点。
  5. 経験・練度（seniority）フィット
     - 求人が要求する練度に対し、経験不足も過剰資格も減点。
  6. 待遇バンド整合 & スコア較正（percentile）
     - 提示待遇と本人希望の整合、候補集団内での相対順位を付与。
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

# --------------------------------------------------------------------------- #
# 双方向（reciprocal）の統合ウェイト（幾何平均の指数）
# --------------------------------------------------------------------------- #
EMPLOYER_EXP = 0.6   # 企業→人材（要件充足）の比重
CANDIDATE_EXP = 0.4  # 人材→企業（本人希望充足）の比重

# 企業→人材（要件）側の観点ウェイト（合計 = 1.0）
EMP_WEIGHTS: dict[str, float] = {
    "skill": 0.34,       # スキル要件
    "language": 0.20,    # 対応言語
    "text": 0.16,        # 職務内容との文章適合（BM25）
    "experience": 0.15,  # 経験・練度
    "type": 0.15,        # 職種
}
# 人材→企業（本人希望）側の観点ウェイト（合計 = 1.0）
CAND_WEIGHTS: dict[str, float] = {
    "salary": 0.45,       # 待遇（希望との整合）
    "country": 0.30,      # 勤務地・国（希望との整合）
    "work_style": 0.10,   # 勤務形態
    "availability": 0.15, # 稼働可否
}

LABELS: dict[str, str] = {
    "skill": "スキル要件",
    "language": "対応言語",
    "text": "職務内容マッチ",
    "experience": "経験・練度",
    "type": "職種",
    "salary": "待遇（本人希望）",
    "country": "勤務地・国（本人希望）",
    "work_style": "勤務形態",
    "availability": "稼働可否",
}

# 関連スキル群（同じ群のスキルは割り引いて部分評価）
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
MUST_HAVE_WEIGHT = 3.0  # 重要度「高」= 必須要件とみなす重み
MUST_HAVE_GATE = 0.7    # 必須要件が欠落したときの減点係数（1件につき）

# 近縁の職種（同じ family 内は部分点）
ROLE_FAMILIES: dict[str, set[str]] = {
    "management": {"店長", "副店長", "店舗管理", "マネージャー", "マネジャー", "SV", "エリアマネージャー"},
    "hall": {"ホール", "接客", "サービス", "ホールリーダー", "フロア"},
    "kitchen": {"キッチン", "調理", "調理長", "キッチン補助", "調理補助", "シェフ", "料理長"},
}
ROLE_FAMILY_SCORE = 0.6


# --------------------------------------------------------------------------- #
# 共通ヘルパ（スキル・職種）
# --------------------------------------------------------------------------- #
def _related_members(skill_name: str) -> set[str]:
    members: set[str] = set()
    for fam in SKILL_FAMILIES:
        if skill_name in fam:
            members |= fam
    members.discard(skill_name)
    return members


def _effective_level(req_name: str, talent_skills: dict[str, int]) -> tuple[float, str]:
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
    m = max(1, min_level)
    L = min(5.0, effective_level)
    if L >= m:
        return 1.0 if m >= 5 else 0.8 + 0.2 * ((L - m) / (5 - m))
    return 0.5 * (L / m)


def _role_family(name: str) -> str | None:
    for fam, members in ROLE_FAMILIES.items():
        if name in members:
            return fam
    return None


# --------------------------------------------------------------------------- #
# BM25 テキスト関連度（Indeed 流の職務内容マッチ）
# --------------------------------------------------------------------------- #
def _bigrams(text: str) -> list[str]:
    """日本語対応の簡易トークナイザ（文字 bi-gram）."""
    text = re.sub(r"[\s　]+", "", str(text or ""))
    if len(text) < 2:
        return [text] if text else []
    return [text[i:i + 2] for i in range(len(text) - 1)]


def _talent_text(t: Any) -> str:
    parts = [getattr(t, "type_os", "") or ""]
    parts += [s.get("name", "") for s in (getattr(t, "skills", None) or [])]
    parts.append(getattr(t, "profile", "") or "")
    return " ".join(parts)


def _job_text(j: Any) -> str:
    parts = [getattr(j, "title", "") or "", getattr(j, "type_os", "") or "",
             getattr(j, "description", "") or ""]
    parts += [s.get("name", "") for s in (getattr(j, "required_skills", None) or [])]
    return " ".join(parts)


def _bm25_scores(query: list[str], docs: list[list[str]], k1: float = 1.5, b: float = 0.75) -> list[float]:
    n = len(docs)
    if n == 0:
        return []
    dls = [len(d) for d in docs]
    avgdl = (sum(dls) / n) or 1.0
    df: dict[str, int] = {}
    for d in docs:
        for term in set(d):
            df[term] = df.get(term, 0) + 1
    tfs = [Counter(d) for d in docs]
    qterms = set(query)
    out: list[float] = []
    for i in range(n):
        s = 0.0
        for term in qterms:
            f = tfs[i].get(term, 0)
            if not f:
                continue
            nq = df.get(term, 0)
            idf = math.log(1 + (n - nq + 0.5) / (nq + 0.5))
            s += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dls[i] / avgdl))
        out.append(s)
    return out


def _cosine(a: list[str], b: list[str]) -> float:
    ca, cb = Counter(a), Counter(b)
    common = set(ca) & set(cb)
    if not common:
        return 0.0
    dot = sum(ca[t] * cb[t] for t in common)
    na = math.sqrt(sum(v * v for v in ca.values()))
    nb = math.sqrt(sum(v * v for v in cb.values()))
    return dot / (na * nb) if na and nb else 0.0


# --------------------------------------------------------------------------- #
# データ構造
# --------------------------------------------------------------------------- #
@dataclass
class Component:
    key: str
    label: str
    score: float          # 0.0-1.0
    weight: float
    detail: str = ""
    side: str = "employer"  # employer / candidate

    @property
    def weighted(self) -> float:
        return self.score * self.weight


@dataclass
class MatchResult:
    talent_id: int
    total: float                 # 0-100（双方向統合後）
    components: list[Component] = field(default_factory=list)
    employer_fit: float = 0.0    # 0-100
    candidate_fit: float = 0.0   # 0-100
    percentile: int | None = None

    def breakdown(self) -> dict[str, Any]:
        return {
            "total": round(self.total, 1),
            "employer_fit": round(self.employer_fit, 1),
            "candidate_fit": round(self.candidate_fit, 1),
            "percentile": self.percentile,
            "components": [
                {
                    "key": c.key,
                    "label": c.label,
                    "score": round(c.score * 100, 1),
                    "weight": c.weight,
                    "detail": c.detail,
                    "side": c.side,
                }
                for c in self.components
            ],
        }


# --------------------------------------------------------------------------- #
# 企業→人材（要件充足）側の観点
# --------------------------------------------------------------------------- #
def _skill_component(job: Any, talent: Any) -> tuple[Component, float]:
    """スキル要件の充足（関連スキル・練度差を考慮）と、必須欠落ゲートを返す."""
    required = job.required_skills or []
    talent_skills = {s.get("name"): int(s.get("level", 0)) for s in (talent.skills or [])}
    if not required:
        return Component("skill", LABELS["skill"], 1.0, EMP_WEIGHTS["skill"], "要件指定なし"), 1.0

    total_w = got_w = 0.0
    covered: list[str] = []
    related: list[str] = []
    missing: list[str] = []
    gate = 1.0
    for req in required:
        name = req.get("name")
        weight = float(req.get("weight", 1) or 1)
        min_level = int(req.get("min_level", 1) or 1)
        total_w += weight
        eff, kind = _effective_level(name, talent_skills)
        got_w += weight * _level_strength(eff, min_level)
        if kind == "exact":
            covered.append(f"{name}(Lv{int(talent_skills[name])})")
        elif kind == "related":
            related.append(f"{name}(関連)")
        else:
            missing.append(name)
            if weight >= MUST_HAVE_WEIGHT:  # 必須スキルの欠落はゲート
                gate *= MUST_HAVE_GATE

    score = got_w / total_w if total_w else 1.0
    parts = []
    if covered:
        parts.append("充足: " + ", ".join(covered))
    if related:
        parts.append("近縁: " + ", ".join(related))
    if missing:
        parts.append("不足: " + ", ".join(missing))
    if gate < 1.0:
        parts.append("※必須スキル欠落で減点")
    return Component("skill", LABELS["skill"], score, EMP_WEIGHTS["skill"], " / ".join(parts)), gate


def _language_component(job: Any, talent: Any) -> Component:
    required = job.required_languages or []
    if not required:
        return Component("language", LABELS["language"], 1.0, EMP_WEIGHTS["language"], "必要言語の指定なし")
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
        got += 1.0 if have >= min_level else max(0.0, have / max(min_level, 1))
        covered.append(f"{name}(Lv{have})")
    score = got / total if total else 1.0
    parts = []
    if covered:
        parts.append("対応: " + ", ".join(covered))
    if missing:
        parts.append("不足: " + ", ".join(missing))
    return Component("language", LABELS["language"], score, EMP_WEIGHTS["language"], " / ".join(parts))


def _text_component(text_score: float) -> Component:
    return Component("text", LABELS["text"], text_score, EMP_WEIGHTS["text"],
                     f"職務内容との文章適合 {round(text_score * 100)}%")


def _experience_component(job: Any, talent: Any) -> Component:
    """求人が要求する練度に対する経験フィット（不足も過剰も減点）."""
    required = job.required_skills or []
    avg_min = (sum(int(r.get("min_level", 1) or 1) for r in required) / len(required)) if required else 2.0
    expected = max(1.0, avg_min * 2.0)  # 最低Lv3 ≒ 6年目安
    exp = float(getattr(talent, "experience_years", 0) or 0)
    if exp >= expected:
        over = exp / expected
        # 過剰資格（目安の2.5倍超）は緩やかに減点
        score = 1.0 if over <= 2.5 else max(0.8, 1.0 - (over - 2.5) * 0.06)
        detail = f"経験{exp:g}年（目安{expected:g}年）" + ("・やや過剰" if over > 2.5 else "")
    else:
        score = 0.4 + 0.6 * (exp / expected)
        detail = f"経験{exp:g}年 < 目安{expected:g}年"
    return Component("experience", LABELS["experience"], score, EMP_WEIGHTS["experience"], detail)


def _type_component(job: Any, talent: Any) -> Component:
    j = (job.type_os or "").strip()
    t = (talent.type_os or "").strip()
    if not j or not t:
        return Component("type", LABELS["type"], 0.6, EMP_WEIGHTS["type"], "職種未設定")
    if j == t:
        return Component("type", LABELS["type"], 1.0, EMP_WEIGHTS["type"], f"一致: {j}")
    fj, ft = _role_family(j), _role_family(t)
    if fj and fj == ft:
        return Component("type", LABELS["type"], ROLE_FAMILY_SCORE, EMP_WEIGHTS["type"], f"近縁: 求人{j} / 人材{t}")
    return Component("type", LABELS["type"], 0.3, EMP_WEIGHTS["type"], f"求人{j} / 人材{t}")


# --------------------------------------------------------------------------- #
# 人材→企業（本人希望充足）側の観点
# --------------------------------------------------------------------------- #
def _salary_component(job: Any, talent: Any) -> Component:
    offered = job.offered_salary or 0
    desired = talent.desired_salary or 0
    currency = (getattr(job, "currency", "JPY") or "JPY").strip()
    if currency != "JPY":
        return Component("salary", LABELS["salary"], 0.85, CAND_WEIGHTS["salary"],
                         f"海外給与: {offered:,} {currency}（参考値）", "candidate")
    if desired == 0 or offered == 0:
        return Component("salary", LABELS["salary"], 0.7, CAND_WEIGHTS["salary"], "待遇情報が不完全", "candidate")
    if offered >= desired:
        # 大幅上振れは満点、僅かに上乗せ感を出さず 1.0 上限
        return Component("salary", LABELS["salary"], 1.0, CAND_WEIGHTS["salary"],
                         f"提示{offered}万 ≧ 希望{desired}万", "candidate")
    gap = (desired - offered) / desired
    score = max(0.0, 1.0 - gap / 0.2)  # 20%不足で 0
    return Component("salary", LABELS["salary"], score, CAND_WEIGHTS["salary"],
                     f"提示{offered}万 < 希望{desired}万（本人が敬遠しやすい）", "candidate")


def _country_component(job: Any, talent: Any) -> Component:
    country = (job.country or "").strip()
    desired = [c.strip() for c in (talent.desired_countries or []) if c and c.strip()]
    if not country:
        return Component("country", LABELS["country"], 0.6, CAND_WEIGHTS["country"], "勤務国の指定なし", "candidate")
    if not desired:
        return Component("country", LABELS["country"], 0.6, CAND_WEIGHTS["country"], "希望勤務国の登録なし", "candidate")
    if country in desired:
        return Component("country", LABELS["country"], 1.0, CAND_WEIGHTS["country"], f"{country}勤務を希望", "candidate")
    return Component("country", LABELS["country"], 0.2, CAND_WEIGHTS["country"],
                     f"求人{country} / 希望{'・'.join(desired)}", "candidate")


def _work_style_component(job: Any, talent: Any) -> Component:
    j = (job.work_style or "both").strip()
    t = (talent.work_style or "both").strip()
    if j == "both" or t == "both" or j == t:
        return Component("work_style", LABELS["work_style"], 1.0, CAND_WEIGHTS["work_style"], f"{j}/{t}", "candidate")
    return Component("work_style", LABELS["work_style"], 0.2, CAND_WEIGHTS["work_style"],
                     f"求人{j} / 人材{t}", "candidate")


def _availability_component(job: Any, talent: Any) -> Component:
    a = (talent.availability or "available").strip()
    mapping = {"available": (1.0, "即勤務可"), "assigned": (0.3, "勤務中"), "unavailable": (0.0, "対応不可")}
    score, detail = mapping.get(a, (0.5, a))
    return Component("availability", LABELS["availability"], score, CAND_WEIGHTS["availability"], detail, "candidate")


# --------------------------------------------------------------------------- #
# 統合スコアリング（双方向 reciprocal）
# --------------------------------------------------------------------------- #
def _score(job: Any, talent: Any, text_score: float,
           emp_weights: dict[str, float] | None = None,
           cand_weights: dict[str, float] | None = None) -> MatchResult:
    skill_comp, gate = _skill_component(job, talent)
    employer = [
        skill_comp,
        _language_component(job, talent),
        _text_component(text_score),
        _experience_component(job, talent),
        _type_component(job, talent),
    ]
    candidate = [
        _salary_component(job, talent),
        _country_component(job, talent),
        _work_style_component(job, talent),
        _availability_component(job, talent),
    ]
    # 学習済みの重み等で上書き（指定があれば）
    if emp_weights:
        for c in employer:
            c.weight = emp_weights.get(c.key, c.weight)
    if cand_weights:
        for c in candidate:
            c.weight = cand_weights.get(c.key, c.weight)
    employer_fit = sum(c.weighted for c in employer) * gate
    candidate_fit = sum(c.weighted for c in candidate)
    # 双方向の幾何平均: 片側が低いと総合も伸びない（＝成立しやすさ）
    total = 100.0 * (max(employer_fit, 1e-6) ** EMPLOYER_EXP) * (max(candidate_fit, 1e-6) ** CANDIDATE_EXP)
    return MatchResult(
        talent_id=talent.id,
        total=total,
        components=employer + candidate,
        employer_fit=employer_fit * 100,
        candidate_fit=candidate_fit * 100,
    )


def score_talent(job: Any, talent: Any) -> MatchResult:
    """求人 1 件 × 人材 1 名のスコア（単体・コーパスなしの文章適合フォールバック）."""
    text = _cosine(_bigrams(_talent_text(talent)), _bigrams(_job_text(job)))
    return _score(job, talent, text)


def rank_talents(job: Any, talents: list[Any], top_n: int | None = None,
                 emp_weights: dict[str, float] | None = None,
                 cand_weights: dict[str, float] | None = None) -> list[MatchResult]:
    """求人に対して人材群を双方向スコアで並べる.

    - 稼働不可 (unavailable) は除外
    - BM25 で職務内容の文章適合を候補集団内で相対評価
    - 候補集団内の相対順位（percentile）を付与
    - emp_weights/cand_weights を渡すと学習済み重みで評価する
    """
    pool = [t for t in talents if (getattr(t, "availability", "available") or "available") != "unavailable"]
    if not pool:
        return []

    query = _bigrams(_job_text(job))
    docs = [_bigrams(_talent_text(t)) for t in pool]
    raw = _bm25_scores(query, docs)
    mx = max(raw) if raw else 0.0
    text_scores = [(r / mx if mx > 0 else 0.5) for r in raw]

    results = [_score(job, t, text_scores[i], emp_weights, cand_weights) for i, t in enumerate(pool)]
    results.sort(key=lambda r: r.total, reverse=True)

    n = len(results)
    for rank, r in enumerate(results):
        r.percentile = round(100 * (n - rank) / n)  # トップ ≒ 100

    if top_n is not None:
        results = results[:top_n]
    return results
