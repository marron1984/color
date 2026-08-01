"""人材の"検証"レイヤー（信頼性の裏取り）のテスト."""
from __future__ import annotations

from types import SimpleNamespace

from app import verification


def _v(category, status):
    return SimpleNamespace(category=category, status=status)


# --------------------------------------------------------------------------- #
# compute_trust
# --------------------------------------------------------------------------- #
def test_empty_is_unverified():
    t = verification.compute_trust([])
    assert t["score"] == 0
    assert t["level"] == "unverified"
    assert t["total_items"] == 0
    assert t["has_mismatch"] is False
    # カテゴリは全カテゴリ分そろう
    assert len(t["categories"]) == len(verification.CATEGORY_KEYS)


def test_all_verified_is_full_score():
    items = [_v(k, "verified") for k in verification.CATEGORY_KEYS]
    t = verification.compute_trust(items)
    assert t["score"] == 100
    assert t["level"] == "strong"
    assert t["verified_count"] == len(verification.CATEGORY_KEYS)


def test_pending_gives_partial_credit():
    # 全カテゴリ pending → 係数0.3 → 30点
    items = [_v(k, "pending") for k in verification.CATEGORY_KEYS]
    t = verification.compute_trust(items)
    assert t["score"] == 30
    assert t["level"] == "basic"
    assert t["pending_count"] == len(verification.CATEGORY_KEYS)


def test_mismatch_flag_and_no_credit():
    t = verification.compute_trust([_v("identity", "mismatch")])
    assert t["has_mismatch"] is True
    assert t["mismatch_count"] == 1
    # mismatch は加点しない
    assert t["score"] == 0


def test_weights_matter():
    # 重み3の identity のみ verified
    heavy = verification.compute_trust([_v("identity", "verified")])
    # 重み1の education のみ verified
    light = verification.compute_trust([_v("education", "verified")])
    assert heavy["score"] > light["score"]


def test_best_status_per_category():
    # 同一カテゴリに複数 → 最良(verified)を採用
    items = [_v("skill", "unverified"), _v("skill", "verified"), _v("skill", "pending")]
    t = verification.compute_trust(items)
    skill_cat = next(c for c in t["categories"] if c["key"] == "skill")
    assert skill_cat["status"] == "verified"


def test_verified_over_mismatch():
    items = [_v("skill", "mismatch"), _v("skill", "verified")]
    t = verification.compute_trust(items)
    skill_cat = next(c for c in t["categories"] if c["key"] == "skill")
    # verified が mismatch より優先
    assert skill_cat["status"] == "verified"


def test_level_thresholds():
    # identity(3)+work_history(3) verified = 6/16 → 38点 → basic
    basic = verification.compute_trust([_v("identity", "verified"), _v("work_history", "verified")])
    assert basic["level"] == "basic"
    # + skill(3)+language(2) = 11/16 → 69点 → standard
    std = verification.compute_trust([
        _v("identity", "verified"), _v("work_history", "verified"),
        _v("skill", "verified"), _v("language", "verified"),
    ])
    assert std["level"] == "standard"


def test_meta_labels_present():
    assert verification.CATEGORY_LABELS["identity"] == "本人確認"
    assert verification.STATUS_LABELS["verified"] == "確認済"
    assert "document" in verification.METHOD_LABELS
