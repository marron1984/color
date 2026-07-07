"""マッチングエンジンのテスト（LLM 不使用の決定論部分）."""
from __future__ import annotations

from types import SimpleNamespace

from app import matching


def make_job(**kw):
    base = dict(
        id=1,
        required_skills=[{"name": "調理", "weight": 3, "min_level": 4},
                         {"name": "仕込み", "weight": 2, "min_level": 3}],
        offered_salary=500,
        type_os="調理長",
        work_style="onsite",
        location="東京",
        country="日本",
        required_languages=[{"name": "日本語", "min_level": 3}],
        visa_support=False,
        currency="JPY",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def make_talent(**kw):
    base = dict(
        id=1,
        skills=[{"name": "調理", "level": 5}, {"name": "仕込み", "level": 4}],
        experience_years=8,
        desired_salary=450,
        type_os="調理長",
        work_style="onsite",
        location="東京",
        availability="available",
        nationality="日本",
        languages=[{"name": "日本語", "level": 5}, {"name": "英語", "level": 3}],
        visa_status="",
        desired_countries=["日本"],
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_perfect_candidate_scores_high():
    result = matching.score_talent(make_job(), make_talent())
    assert result.total > 90
    assert len(result.components) == 9  # 企業側5 + 本人側4


def test_missing_skill_reduces_score():
    weak = make_talent(skills=[{"name": "調理", "level": 2}])  # 仕込みなし & レベル不足
    strong = make_talent()
    assert matching.score_talent(make_job(), weak).total < matching.score_talent(make_job(), strong).total


def test_missing_language_reduces_score():
    no_lang = make_talent(languages=[{"name": "英語", "level": 5}])  # 日本語なし
    with_lang = make_talent()
    assert matching.score_talent(make_job(), no_lang).total < matching.score_talent(make_job(), with_lang).total


def test_country_mismatch_lowers_country_component():
    job = make_job(country="シンガポール")
    talent = make_talent(desired_countries=["日本"])  # シンガポール希望なし
    result = matching.score_talent(job, talent)
    country_comp = next(c for c in result.components if c.key == "country")
    assert country_comp.score < 0.5


def test_language_fulfilled_full_score():
    job = make_job(required_languages=[{"name": "英語", "min_level": 4}])
    talent = make_talent(languages=[{"name": "英語", "level": 5}, {"name": "日本語", "level": 5}])
    result = matching.score_talent(job, talent)
    lang_comp = next(c for c in result.components if c.key == "language")
    assert lang_comp.score == 1.0


def test_salary_below_desired_penalized():
    low_offer = make_job(offered_salary=300)
    high_offer = make_job(offered_salary=500)
    t = make_talent(desired_salary=450)
    assert matching.score_talent(low_offer, t).total < matching.score_talent(high_offer, t).total


def test_type_mismatch_lowers_type_component():
    t = make_talent(type_os="ホール")  # 求人は調理長
    result = matching.score_talent(make_job(), t)
    type_comp = next(c for c in result.components if c.key == "type")
    assert type_comp.score < 0.5


def test_unavailable_talent_excluded_from_ranking():
    talents = [
        make_talent(id=1, availability="available"),
        make_talent(id=2, availability="unavailable"),
    ]
    ranked = matching.rank_talents(make_job(), talents)
    ids = {r.talent_id for r in ranked}
    assert 1 in ids
    assert 2 not in ids


def test_ranking_is_sorted_descending():
    talents = [
        make_talent(id=1, skills=[{"name": "調理", "level": 5}, {"name": "仕込み", "level": 4}]),
        make_talent(id=2, skills=[{"name": "調理", "level": 2}]),
        make_talent(id=3, skills=[{"name": "調理", "level": 4}, {"name": "仕込み", "level": 3}]),
    ]
    ranked = matching.rank_talents(make_job(), talents)
    scores = [r.total for r in ranked]
    assert scores == sorted(scores, reverse=True)


def test_top_n_limits_results():
    talents = [make_talent(id=i) for i in range(1, 11)]
    ranked = matching.rank_talents(make_job(), talents, top_n=3)
    assert len(ranked) == 3


def test_breakdown_structure():
    breakdown = matching.score_talent(make_job(), make_talent()).breakdown()
    assert "total" in breakdown
    assert "employer_fit" in breakdown
    assert "candidate_fit" in breakdown
    keys = {c["key"] for c in breakdown["components"]}
    assert keys == {"skill", "language", "text", "experience", "type",
                    "salary", "country", "work_style", "availability"}
    # 各観点は企業側/本人側のいずれかに分類される
    sides = {c["side"] for c in breakdown["components"]}
    assert sides == {"employer", "candidate"}


def test_reciprocal_two_sided_penalty():
    """スキル完璧でも、本人が敬遠する条件（低待遇＋希望外の勤務国）だと総合が下がる."""
    job_good = make_job(offered_salary=600, country="日本")
    job_bad = make_job(offered_salary=250, country="シンガポール")  # 低待遇＋希望外
    talent = make_talent(desired_salary=500, desired_countries=["日本"])
    good = matching.score_talent(job_good, talent).total
    bad = matching.score_talent(job_bad, talent).total
    assert good > bad
    # 本人希望適合が総合を強く引き下げる
    assert matching.score_talent(job_bad, talent).candidate_fit < 60


def test_must_have_gate_penalizes_missing_required_skill():
    job = make_job(required_skills=[{"name": "寿司握り", "weight": 3, "min_level": 4}])
    has = make_talent(skills=[{"name": "寿司握り", "level": 5}])
    lacks = make_talent(skills=[{"name": "バリスタ", "level": 5}])  # 無関係
    assert matching.score_talent(job, has).total > matching.score_talent(job, lacks).total


def test_percentile_assigned_on_ranking():
    talents = [make_talent(id=i, skills=[{"name": "調理", "level": lv}])
               for i, lv in enumerate([5, 3, 1], start=1)]
    ranked = matching.rank_talents(make_job(), talents)
    assert ranked[0].percentile >= ranked[-1].percentile
    assert ranked[0].breakdown()["percentile"] is not None


# --- 精度改善のテスト ---
def _skill_comp(job, talent):
    r = matching.score_talent(job, talent)
    return next(c for c in r.components if c.key == "skill")


def _comp(job, talent, key):
    r = matching.score_talent(job, talent)
    return next(c for c in r.components if c.key == key)


def test_experience_affects_score():
    veteran = make_talent(experience_years=15)
    rookie = make_talent(experience_years=0)
    # 経験は専用の観点として評価され、総合スコアにも効く
    assert _comp(make_job(), veteran, "experience").score > _comp(make_job(), rookie, "experience").score
    assert matching.score_talent(make_job(), veteran).total > matching.score_talent(make_job(), rookie).total


def test_higher_level_scores_higher_than_minimum():
    job = make_job(required_skills=[{"name": "調理", "weight": 1, "min_level": 3}])
    expert = make_talent(skills=[{"name": "調理", "level": 5}], experience_years=8)
    just_ok = make_talent(skills=[{"name": "調理", "level": 3}], experience_years=8)
    assert _skill_comp(job, expert).score > _skill_comp(job, just_ok).score


def test_related_skill_gives_partial_credit():
    job = make_job(required_skills=[{"name": "仕込み", "weight": 1, "min_level": 3}])
    # 「仕込み」は無いが近縁の「調理」を持つ人材 vs 全く無関係な人材
    related = make_talent(skills=[{"name": "調理", "level": 5}])
    unrelated = make_talent(skills=[{"name": "バリスタ", "level": 5}])
    s_related = _skill_comp(job, related).score
    s_unrelated = _skill_comp(job, unrelated).score
    assert s_related > s_unrelated
    # 完全一致にはやや劣る
    exact = make_talent(skills=[{"name": "仕込み", "level": 5}])
    assert _skill_comp(job, exact).score > s_related


def test_related_role_scores_between_exact_and_unrelated():
    job = make_job(type_os="店長")
    exact = make_talent(type_os="店長")
    related = make_talent(type_os="副店長")     # 同じ management family
    unrelated = make_talent(type_os="寿司職人")

    def type_score(t):
        return next(c for c in matching.score_talent(job, t).components if c.key == "type").score

    assert type_score(exact) == 1.0
    assert type_score(unrelated) < type_score(related) < type_score(exact)
