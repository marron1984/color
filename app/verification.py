"""人材の"検証"レイヤー（信頼性の裏取り）.

登録内容（本人確認・職歴・スキル・語学・資格・学歴・ビザ書類・リファレンス）を
どこまで裏取りできているかを管理し、人材ごとの「検証スコア（信頼度）」を算出する。

海外飲食人材紹介では「経歴・スキルの真偽」が受入店舗の最大の不安要素になるため、
証跡（エビデンス）を残して可視化することが差別化になる。
"""
from __future__ import annotations

from typing import Any

# 検証カテゴリ（key, ラベル, 重み） — 重みは信頼度スコアへの寄与度
CATEGORIES: list[tuple[str, str, int]] = [
    ("identity", "本人確認", 3),          # パスポート・身分証
    ("work_history", "職歴・前職照会", 3),  # 前職への在籍確認
    ("skill", "スキル・実技", 3),          # 実技テスト・調理動画 等
    ("language", "語学レベル", 2),         # TOEIC/JLPT 等の証明
    ("certification", "資格・免許", 2),     # 調理師免許・食品衛生 等
    ("visa_document", "ビザ・在留書類", 2), # 在留カード・査証 等
    ("education", "学歴", 1),              # 卒業証明
    ("reference", "推薦・リファレンス", 1), # 第三者の推薦
]
CATEGORY_LABELS: dict[str, str] = {k: label for k, label, _ in CATEGORIES}
CATEGORY_WEIGHTS: dict[str, int] = {k: w for k, _, w in CATEGORIES}
CATEGORY_KEYS: tuple[str, ...] = tuple(k for k, _, _ in CATEGORIES)

# 検証ステータス
STATUS_LABELS: dict[str, str] = {
    "unverified": "未検証",
    "pending": "確認中",
    "verified": "確認済",
    "mismatch": "相違あり",
}
STATUS_KEYS: tuple[str, ...] = tuple(STATUS_LABELS.keys())

# 検証方法
METHOD_LABELS: dict[str, str] = {
    "document": "書類確認",
    "interview": "面談",
    "test": "実技テスト",
    "reference_call": "前職・第三者照会",
    "third_party": "第三者機関",
    "other": "その他",
}

# ステータスごとのスコア係数（重みに乗じる）
_STATUS_FACTOR = {
    "verified": 1.0,
    "pending": 0.3,
    "mismatch": 0.0,   # 加点しない（さらに has_mismatch で警告）
    "unverified": 0.0,
}

# レベル判定のしきい値（score >= 値）
_LEVELS = [
    (70, "strong", "確認充実"),
    (40, "standard", "標準確認"),
    (1, "basic", "基本確認"),
    (0, "unverified", "未検証"),
]

_RANK = {"unverified": 0, "pending": 1, "mismatch": 2, "verified": 3}


def _best_status(statuses: list[str]) -> str:
    """同一カテゴリ内の最良ステータスを返す（verified > mismatch > pending > unverified）."""
    if not statuses:
        return "unverified"
    return max(statuses, key=lambda s: _RANK.get(s, 0))


def compute_trust(verifications: list[Any]) -> dict[str, Any]:
    """検証項目のリストから、人材の検証スコア（信頼度）を算出する.

    戻り値:
      score       : 0-100（重み付き達成率）
      level        : unverified / basic / standard / strong
      level_label  : 表示用ラベル
      verified_count / pending_count / total_items
      has_mismatch : 相違あり項目があるか（要確認フラグ）
      categories   : カテゴリ別の最良ステータス一覧
    """
    by_cat: dict[str, list[str]] = {k: [] for k in CATEGORY_KEYS}
    verified_count = pending_count = mismatch_count = 0
    for v in verifications:
        cat = getattr(v, "category", "") or ""
        st = getattr(v, "status", "") or "unverified"
        if cat in by_cat:
            by_cat[cat].append(st)
        if st == "verified":
            verified_count += 1
        elif st == "pending":
            pending_count += 1
        elif st == "mismatch":
            mismatch_count += 1

    total_weight = sum(CATEGORY_WEIGHTS.values())
    earned = 0.0
    cats_out: list[dict[str, Any]] = []
    for k in CATEGORY_KEYS:
        best = _best_status(by_cat[k])
        earned += CATEGORY_WEIGHTS[k] * _STATUS_FACTOR.get(best, 0.0)
        cats_out.append({
            "key": k,
            "label": CATEGORY_LABELS[k],
            "weight": CATEGORY_WEIGHTS[k],
            "status": best,
            "status_label": STATUS_LABELS.get(best, best),
        })

    score = round(100 * earned / total_weight) if total_weight else 0
    level = level_label = ""
    for threshold, lv, lv_label in _LEVELS:
        if score >= threshold:
            level, level_label = lv, lv_label
            break

    return {
        "score": score,
        "level": level,
        "level_label": level_label,
        "verified_count": verified_count,
        "pending_count": pending_count,
        "mismatch_count": mismatch_count,
        "total_items": len(verifications),
        "has_mismatch": mismatch_count > 0,
        "categories": cats_out,
    }


def empty_trust() -> dict[str, Any]:
    """検証項目が無い人材の初期 trust."""
    return compute_trust([])
