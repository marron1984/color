"""アウトカム学習（定着率フィードバック）.

保存されたマッチング（Match）の「採用・定着の結果」を集計し、
「成功した採用で高かった観点」を学習してマッチングの重みに反映する。

- 成功(success): 採用され、離職していない（在籍 or 未離職）
- 失敗(failure): 不採用、または採用後に離職
- 判定不能(pending): 選考中（学習対象外）

学習データ不要の統計的アプローチ。データが少ないうちは既定重みを重視し、
データが増えるほど学習重みへ寄せる（信頼度ブレンド）。
"""
from __future__ import annotations

from typing import Any

from app import matching

N_REF = 30          # この件数で学習重みを最大採用（信頼度=1.0）
ALPHA = 1.5         # 重要度を重みへ反映する強さ

EMP_KEYS = ("skill", "language", "text", "experience", "type")
CAND_KEYS = ("salary", "country", "work_style", "availability")


def outcome_label(m: Any) -> str | None:
    """Match の結果ラベル: success / failure / None(判定不能)."""
    status = (getattr(m, "status", "") or "").strip()
    retention = (getattr(m, "retention", "") or "").strip()
    if status == "rejected":
        return "failure"
    if status == "hired":
        return "failure" if retention == "left" else "success"
    return None


def compute_metrics(matches: list[Any]) -> dict[str, Any]:
    total = len(matches)
    by_status: dict[str, int] = {}
    hired = active = left = 0
    ret_days: list[int] = []
    for m in matches:
        st = (getattr(m, "status", "") or "proposed")
        by_status[st] = by_status.get(st, 0) + 1
        if st == "hired":
            hired += 1
            r = (getattr(m, "retention", "") or "")
            if r == "left":
                left += 1
            elif r == "active":
                active += 1
            d = int(getattr(m, "retention_days", 0) or 0)
            if d > 0:
                ret_days.append(d)
    decided = hired + by_status.get("rejected", 0)
    retention_known = active + left
    return {
        "total": total,
        "by_status": by_status,
        "hired": hired,
        "active": active,
        "left": left,
        # 決定率 = 採用 / (採用+不採用)
        "decision_rate": round(100 * hired / decided, 1) if decided else None,
        # 定着率 = 在籍 / (在籍+離職)
        "retention_rate": round(100 * active / retention_known, 1) if retention_known else None,
        "avg_retention_days": round(sum(ret_days) / len(ret_days)) if ret_days else None,
    }


def _component_scores(m: Any) -> dict[str, float]:
    bd = getattr(m, "breakdown", None) or {}
    out: dict[str, float] = {}
    for c in bd.get("components", []):
        try:
            out[c["key"]] = float(c["score"])
        except (KeyError, TypeError, ValueError):
            continue
    return out


def learned_weights(matches: list[Any]) -> dict[str, Any]:
    """成功/失敗の観点スコア差から重要度を出し、学習重みを返す.

    戻り値:
      emp/cand: 学習後の重み（信頼度で既定重みとブレンド）
      importances: 観点ごとの重要度（-1..1, 正=成功に寄与）
      n_labeled / confidence
    """
    labeled = [(m, outcome_label(m)) for m in matches]
    labeled = [(m, lab) for m, lab in labeled if lab]
    succ = [m for m, lab in labeled if lab == "success"]
    fail = [m for m, lab in labeled if lab == "failure"]
    n = len(labeled)
    confidence = min(1.0, n / N_REF) if n else 0.0

    keys = EMP_KEYS + CAND_KEYS
    importances: dict[str, float] = {k: 0.0 for k in keys}
    if succ and fail:
        succ_scores = [_component_scores(m) for m in succ]
        fail_scores = [_component_scores(m) for m in fail]
        for k in keys:
            s = [d[k] for d in succ_scores if k in d]
            f = [d[k] for d in fail_scores if k in d]
            if s and f:
                importances[k] = (sum(s) / len(s) - sum(f) / len(f)) / 100.0

    def _blend(keys_, base: dict[str, float]) -> dict[str, float]:
        # 学習重み = 既定 * (1 + ALPHA*重要度)、正規化
        raw = {k: max(0.0, base[k] * (1 + ALPHA * importances[k])) for k in keys_}
        tot = sum(raw.values()) or 1.0
        learned = {k: raw[k] / tot for k in keys_}
        # 信頼度で既定重みとブレンドし、再正規化
        blended = {k: (1 - confidence) * base[k] + confidence * learned[k] for k in keys_}
        tot2 = sum(blended.values()) or 1.0
        return {k: round(blended[k] / tot2, 4) for k in keys_}

    emp = _blend(EMP_KEYS, matching.EMP_WEIGHTS)
    cand = _blend(CAND_KEYS, matching.CAND_WEIGHTS)
    return {
        "emp": emp,
        "cand": cand,
        "importances": {k: round(v, 3) for k, v in importances.items()},
        "labels": {k: matching.LABELS.get(k, k) for k in keys},
        "n_labeled": n,
        "n_success": len(succ),
        "n_failure": len(fail),
        "confidence": round(confidence, 2),
    }
