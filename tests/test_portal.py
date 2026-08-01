"""企業ポータル／候補者ポータルの整形・マスキングのテスト."""
from __future__ import annotations

from types import SimpleNamespace

from app import portal


def _talent(**kw):
    base = dict(
        name="山下 玲", type_os="寿司職人", experience_years=8,
        nationality="日本", visa_status="",
        skills=[{"name": "寿司", "level": 5}],
        languages=[{"name": "英語", "level": 4}],
        verifications=[],
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _match(**kw):
    base = dict(
        id=1, talent=_talent(), score=82.0, reason="要件を満たします",
        breakdown={"components": []}, status="proposed", client_interest="",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _job(**kw):
    base = dict(
        id=1, title="寿司職人", country="日本", location="東京",
        offered_salary=5000000, currency="JPY", employment_type="正社員",
        working_hours="", holidays="", benefits="", requirements="",
        ideal_candidate="", description="", visa_support=True,
        required_languages=[{"name": "英語"}],
        client=SimpleNamespace(name="鮨 銀座 本店"),
    )
    base.update(kw)
    return SimpleNamespace(**base)


# --------------------------------------------------------------------------- #
# masked_name
# --------------------------------------------------------------------------- #
def test_masked_name_two_parts():
    assert portal.masked_name("山下 玲") == "山下 ○○"


def test_masked_name_single_token():
    out = portal.masked_name("玲")
    assert out.startswith("玲") and "○" in out


def test_masked_name_empty():
    assert portal.masked_name("") == "候補者"


# --------------------------------------------------------------------------- #
# public_candidate — 個人情報を伏せる
# --------------------------------------------------------------------------- #
def test_public_candidate_masks_identity_and_contact():
    c = portal.public_candidate(_match())
    assert c["display_name"] == "山下 ○○"
    # 連絡先・住所・氏名フルは含めない
    for leaked in ("phone", "email", "contact_note", "address", "name"):
        assert leaked not in c
    assert c["score"] == 82.0
    assert c["languages"] == ["英語"]
    assert c["skills"][0]["name"] == "寿司"


def test_public_candidate_includes_trust_summary_only():
    t = _talent(verifications=[
        SimpleNamespace(category="identity", status="verified"),
        SimpleNamespace(category="skill", status="verified"),
    ])
    c = portal.public_candidate(_match(talent=t))
    assert "trust" in c
    # サマリのみ（証跡やカテゴリ詳細は出さない）
    assert set(c["trust"].keys()) == {"score", "level", "level_label", "has_mismatch"}
    assert c["trust"]["score"] > 0


# --------------------------------------------------------------------------- #
# public_job
# --------------------------------------------------------------------------- #
def test_public_job_includes_client_when_asked():
    j = portal.public_job(_job(), include_client=True)
    assert j["client_name"] == "鮨 銀座 本店"
    assert j["title"] == "寿司職人"
    assert j["visa_support"] is True
    assert j["required_languages"] == ["英語"]


def test_public_job_hides_client_for_employer_view():
    j = portal.public_job(_job(), include_client=False)
    assert j["client_name"] == ""
