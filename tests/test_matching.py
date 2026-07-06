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
    assert len(result.components) == 7


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
    assert "components" in breakdown
    keys = {c["key"] for c in breakdown["components"]}
    assert keys == {"skill", "language", "salary", "country", "type", "work_style", "availability"}
