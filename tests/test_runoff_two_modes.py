"""Only second-round history may shift a second-round nowcast."""
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
import runoff_nowcast
from runoff_nowcast import estimate, read_current_polls
from runoff_calendar import audit_calendar

ROOT = Path(__file__).resolve().parents[1]
POLLS = ROOT / "data/manual_second_round_2026.csv"
CAL = ROOT / "data/scheduled_polls_2026_10_10.csv"


def calibration(match=False, mu=0., accepted=False):
    return {
        "historical_round": 2,
        "status": "historical_second_round" if match else "external_fallback",
        "fit": SimpleNamespace(pollsters=np.array(["DATAFOLHA", "PODERDATA"])) if match else None,
        "mu_ilr": mu, "directional_mean_used": accepted,
        "common_sd_ilr": .07, "tau_p_ilr": .03,
    }


def test_no_2t_history_yields_equal_centers():
    d = read_current_polls(POLLS, "2026-10-10")
    a, _ = estimate(d, calibration(), "2026-10-10", bias_mode="none", draws=4000)
    b, _ = estimate(d, calibration(), "2026-10-10", bias_mode="second_round_history", draws=4000)
    assert a.iloc[0]["polling_lula_pct"] == b.iloc[0]["polling_lula_pct"]


def test_2t_house_bias_applies_only_to_corrected(monkeypatch):
    d = read_current_polls(POLLS, "2026-10-10")
    def post(fit, group, name):
        assert group == "pollster"
        return (.045, .0001) if name == "Datafolha" else (0., .0001)
    monkeypatch.setattr(runoff_nowcast, "_random_effect_posterior", post)
    a, aa = estimate(d, calibration(True), "2026-10-10", bias_mode="none", draws=4000)
    b, bb = estimate(d, calibration(True), "2026-10-10", bias_mode="second_round_history", draws=4000)
    assert np.allclose(aa["obs_var_ilr"], bb["obs_var_ilr"])
    assert np.allclose(aa["z_poll_ilr"], bb["z_poll_ilr"])
    assert b.iloc[0]["polling_lula_pct"] < a.iloc[0]["polling_lula_pct"]
    assert a.iloc[0]["n_house_effects_applied"] == 0
    assert b.iloc[0]["n_house_effects_applied"] == 2


def test_common_2t_bias_needs_validation():
    d = read_current_polls(POLLS, "2026-10-10")
    a, _ = estimate(d, calibration(mu=.1), "2026-10-10", draws=7000)
    b, _ = estimate(d, calibration(mu=.1, accepted=True), "2026-10-10", draws=7000)
    c, _ = estimate(d, calibration(mu=.1, accepted=True), "2026-10-10", draws=7000, bias_mode="none")
    assert b.iloc[0]["counterfactual_lula_pct"] < a.iloc[0]["counterfactual_lula_pct"] - 2
    assert c.iloc[0]["counterfactual_lula_pct"] == a.iloc[0]["counterfactual_lula_pct"]


def test_rejects_first_round_calibration():
    d = read_current_polls(POLLS, "2026-10-10")
    with pytest.raises(ValueError, match="first-round"):
        estimate(d, {**calibration(), "historical_round": 1}, "2026-10-10")


def test_calendar_only_metadata_no_predictions():
    c = audit_calendar(CAL)
    assert len(c) == 19
    assert set(c.loc[c["date_conflict"], "poll_id"]) == {"BR-05187", "BR-06778"}
    assert (c["scope"] == "national").sum() == 11
    assert (c["scope"] == "regional").sum() == 8
    assert "bias_flavio_minus_lula_pp" not in c
    assert len(read_current_polls(POLLS, "2026-10-10")) == 3
