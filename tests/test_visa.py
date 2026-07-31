"""ビザ適格性判定エンジンのテスト（ネットワーク不要）."""
from __future__ import annotations

from app import visa


def _levels(res):
    return {p["name"]: p["level"] for p in res["programs"]}


def test_japanese_national_in_japan_no_visa():
    res = visa.assess("日本", "日本", "ホール")
    assert res["level"] == "eligible"
    assert not res["relevant"]  # 越境要素なし


def test_permanent_resident_unrestricted():
    res = visa.assess("ベトナム", "日本", "調理", held_status="永住者")
    assert res["level"] == "eligible"
    assert res["relevant"]


def test_foreign_kitchen_in_japan_offers_tokutei_ginou():
    res = visa.assess("ベトナム", "日本", "キッチン", experience_years=3)
    names = [p["name"] for p in res["programs"]]
    assert any("特定技能" in n for n in names)
    assert res["relevant"]


def test_held_tokutei_ginou_is_eligible():
    res = visa.assess("ベトナム", "日本", "ホール", held_status="特定技能（外食業）")
    lv = _levels(res)
    assert any(name.startswith("特定技能") and lv[name] == "eligible" for name in lv)


def test_skilled_cook_10y_conditional():
    low = visa.assess("中国", "日本", "調理", experience_years=3)
    high = visa.assess("中国", "日本", "調理", experience_years=12)
    def find(res):
        return next(p for p in res["programs"] if "外国料理" in p["name"])
    assert find(low)["level"] == "review"
    assert find(high)["level"] == "conditional"


def test_overseas_destination_singapore():
    res = visa.assess("日本", "シンガポール", "店長")
    names = [p["name"] for p in res["programs"]]
    assert any("Employment Pass" in n or "EP" in n for n in names)
    assert res["relevant"]


def test_usa_e2_for_japanese():
    res = visa.assess("日本", "アメリカ", "店長")
    assert any("E-2" in p["name"] for p in res["programs"])


def test_unknown_country_review():
    res = visa.assess("日本", "ドイツ", "調理")
    assert res["level"] in ("review", "conditional", "eligible")
    assert res["programs"]


def test_assess_for_match_uses_talent_and_job():
    from types import SimpleNamespace
    job = SimpleNamespace(type_os="寿司職人", country="アメリカ")
    talent = SimpleNamespace(nationality="日本", type_os="寿司職人",
                             experience_years=18,
                             languages=[{"name": "日本語", "level": 5}], visa_status="")
    res = visa.assess_for_match(job, talent)
    assert res["country"] == "アメリカ"
    assert res["relevant"]
