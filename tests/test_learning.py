"""アウトカム学習（定着率フィードバック）のテスト."""
from __future__ import annotations

from types import SimpleNamespace

from app import learning, matching


def _match(status="proposed", retention="", retention_days=0, components=None):
    """テスト用の擬似 Match（breakdown に観点スコアを持つ）."""
    comps = [{"key": k, "score": v} for k, v in (components or {}).items()]
    return SimpleNamespace(
        status=status,
        retention=retention,
        retention_days=retention_days,
        breakdown={"components": comps},
    )


# --------------------------------------------------------------------------- #
# outcome_label
# --------------------------------------------------------------------------- #
def test_label_rejected_is_failure():
    assert learning.outcome_label(_match(status="rejected")) == "failure"


def test_label_hired_active_is_success():
    assert learning.outcome_label(_match(status="hired", retention="active")) == "success"


def test_label_hired_no_retention_is_success():
    # 採用済みで離職していなければ成功扱い
    assert learning.outcome_label(_match(status="hired")) == "success"


def test_label_hired_left_is_failure():
    assert learning.outcome_label(_match(status="hired", retention="left")) == "failure"


def test_label_in_progress_is_none():
    assert learning.outcome_label(_match(status="interview")) is None
    assert learning.outcome_label(_match(status="proposed")) is None


# --------------------------------------------------------------------------- #
# compute_metrics
# --------------------------------------------------------------------------- #
def test_metrics_counts_and_rates():
    matches = [
        _match(status="hired", retention="active", retention_days=120),
        _match(status="hired", retention="left", retention_days=30),
        _match(status="hired", retention="active", retention_days=200),
        _match(status="rejected"),
        _match(status="interview"),
    ]
    m = learning.compute_metrics(matches)
    assert m["total"] == 5
    assert m["hired"] == 3
    assert m["active"] == 2
    assert m["left"] == 1
    # 決定率 = 採用3 / (採用3+不採用1) = 75.0
    assert m["decision_rate"] == 75.0
    # 定着率 = 在籍2 / (在籍2+離職1) ≒ 66.7
    assert m["retention_rate"] == 66.7
    # 平均在籍 = (120+30+200)/3 ≒ 117
    assert m["avg_retention_days"] == 117


def test_metrics_empty_rates_none():
    m = learning.compute_metrics([])
    assert m["total"] == 0
    assert m["decision_rate"] is None
    assert m["retention_rate"] is None
    assert m["avg_retention_days"] is None


# --------------------------------------------------------------------------- #
# learned_weights
# --------------------------------------------------------------------------- #
def test_learned_weights_no_data_returns_base():
    L = learning.learned_weights([])
    assert L["n_labeled"] == 0
    assert L["confidence"] == 0.0
    # データが無ければ既定重みと一致
    for k, v in matching.EMP_WEIGHTS.items():
        assert L["emp"][k] == round(v, 4)


def test_learned_weights_importance_positive_for_discriminating_component():
    # skill が高い採用は成功、低い採用は離職 → skill の重要度が正
    succ = [_match(status="hired", retention="active",
                   components={"skill": 90, "language": 50, "text": 50,
                               "experience": 50, "type": 50})
            for _ in range(4)]
    fail = [_match(status="hired", retention="left",
                   components={"skill": 20, "language": 50, "text": 50,
                               "experience": 50, "type": 50})
            for _ in range(4)]
    L = learning.learned_weights(succ + fail)
    assert L["n_labeled"] == 8
    assert L["n_success"] == 4
    assert L["n_failure"] == 4
    assert L["importances"]["skill"] > 0
    # 重要度が正の観点は重みが既定より増える
    assert L["emp"]["skill"] > round(matching.EMP_WEIGHTS["skill"], 4)


def test_learned_weights_confidence_scales_with_n():
    succ = [_match(status="hired", retention="active",
                   components={"skill": 80, "language": 50, "text": 50,
                               "experience": 50, "type": 50})
            for _ in range(3)]
    fail = [_match(status="rejected",
                   components={"skill": 30, "language": 50, "text": 50,
                               "experience": 50, "type": 50})
            for _ in range(3)]
    L = learning.learned_weights(succ + fail)
    # n=6, N_REF=30 → confidence = 0.2
    assert L["confidence"] == round(6 / learning.N_REF, 2)
    # 重みは正規化されて合計 ≒ 1
    assert abs(sum(L["emp"].values()) - 1.0) < 0.01
    assert abs(sum(L["cand"].values()) - 1.0) < 0.01
