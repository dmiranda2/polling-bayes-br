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
    assert len(read_current_polls(POLLS, "2026-10-10")) == 4


def test_experimental_free_mean_preserves_rejected_signal_and_uncertainty():
    d = read_current_polls(POLLS, "2026-10-10")
    hist = {**calibration(), "free_mu_ilr": -0.06398579338771775,
            "free_mu_var_ilr": 0.042525**2,
            "directional_mean_used": False}
    approved, b = estimate(d, hist, "2026-10-10", bias_mode="second_round_history", draws=15000)
    exploratory, e = estimate(d, hist, "2026-10-10",
                              bias_mode="experimental_free_mean_2t", draws=15000)
    rb, rx = approved.iloc[0], exploratory.iloc[0]
    assert rx["polling_lula_pct"] == rb["polling_lula_pct"]
    assert rx["polling_latent_sd_ilr"] == rb["polling_latent_sd_ilr"]
    assert np.allclose(b["obs_var_ilr"], e["obs_var_ilr"])
    assert rx["counterfactual_lula_pct"] > rb["counterfactual_lula_pct"] + 2
    assert rx["common_error_sd_ilr"] > rb["common_error_sd_ilr"]
    assert rx["experimental_unvalidated_mean"]
    assert rx["directional_mean_used"] and not rx["directional_mean_validated"]
    assert not rb["directional_mean_used"]
    assert rx["mean_common_shift_applied_ilr"] < 0


def test_experimental_free_mean_requires_independent_2t_data():
    d = read_current_polls(POLLS, "2026-10-10")
    with pytest.raises(ValueError, match="free mean unavailable"):
        estimate(d, calibration(), "2026-10-10",
                 bias_mode="experimental_free_mean_2t")


def test_experimental_free_mean_rejects_1t_history():
    d = read_current_polls(POLLS, "2026-10-10")
    hist = {**calibration(), "historical_round": 1,
            "free_mu_ilr": -0.06, "free_mu_var_ilr": 0.002}
    with pytest.raises(ValueError, match="first-round"):
        estimate(d, hist, "2026-10-10",
                 bias_mode="experimental_free_mean_2t")


def test_experimental_atlas_remains_sensitivity():
    d = read_current_polls(POLLS, "2026-10-10", include_mixed=True)
    hist = {**calibration(), "free_mu_ilr": -0.06, "free_mu_var_ilr": 0.002}
    result, used = estimate(d, hist, "2026-10-10",
                            bias_mode="experimental_free_mean_2t", draws=5000)
    assert result.iloc[0]["scenario"] == "mixed_atlas_included"
    assert set(used.pollster) == {"PoderData", "Datafolha", "Vox Brasil", "AtlasIntel", "Ipespe"}


def test_october_13_new_round_replaces_old_poderdata_and_keeps_atlas_separate():
    current = read_current_polls(POLLS, "2026-10-13")
    assert len(current) == 8
    assert set(current.pollster) == {"Datafolha", "PoderData", "Vox Brasil", "Ipespe", "DataTrends", "Nexus", "Gerp", "Futura"}
    poder = current[current.pollster == "PoderData"].iloc[0]
    assert poder.poll_id == "BR-01209/2026"
    assert poder.lula_valid_pct == 49.0
    assert not current.is_mixed_field.any()
    with_atlas = read_current_polls(POLLS, "2026-10-13", include_mixed=True)
    assert len(with_atlas) == 9
    assert set(with_atlas.loc[with_atlas.is_mixed_field, "pollster"]) == {"AtlasIntel"}


def test_october_14_quaest_is_derived_and_not_visible_on_publication_eve():
    before = read_current_polls(POLLS, "2026-10-13")
    assert "Quaest" not in set(before.pollster)
    current = read_current_polls(POLLS, "2026-10-14")
    assert len(current) == 9
    assert current.pollster.nunique() == 9
    assert not current.is_mixed_field.any()
    quaest = current[current.pollster.eq("Quaest")].iloc[0]
    assert quaest.poll_id == "BR-08729/2026"
    assert quaest.basis == "derived_valid_from_rounded_total"
    assert quaest.lula_valid_pct == pytest.approx(100 * 44 / (44 + 46))
    assert quaest.flavio_valid_pct == pytest.approx(100 * 46 / (44 + 46))
    assert quaest.n_reported == 2154
    assert quaest.moe_pp == 2
    assert quaest.field_start == "2026-10-10"
    assert quaest.field_end == "2026-10-13"
    assert quaest.publish_date == "2026-10-14"
    with_atlas = read_current_polls(POLLS, "2026-10-14", include_mixed=True)
    assert len(with_atlas) == 10
    assert set(with_atlas.loc[with_atlas.is_mixed_field, "pollster"]) == {"AtlasIntel"}


def test_futura_uses_published_valids_and_preserves_reported_totals():
    import pandas as pd
    raw = pd.read_csv(POLLS)
    assert not raw.duplicated(["poll_id", "candidate"]).any()
    future = raw[raw.poll_id.eq("BR-00650/2026")].set_index("candidate")
    assert set(future.index) == {"Lula", "Flávio Bolsonaro"}
    assert future.loc["Lula", "pct"] == 46.6
    assert future.loc["Flávio Bolsonaro", "pct"] == 50.0
    assert future.loc["Lula", "pct_valid"] == 48.2
    assert future.loc["Flávio Bolsonaro", "pct_valid"] == 51.8
    assert set(future.vote_basis) == {"published_valid"}
    assert "Futura" not in set(read_current_polls(POLLS, "2026-10-12").pollster)
    assert "Futura" in set(read_current_polls(POLLS, "2026-10-13").pollster)
    # Old tracking observations stay auditable while only the latest is fitted.
    assert {"BR-08134/2026", "BR-01209/2026"} <= set(raw.poll_id)
    assert set(read_current_polls(POLLS, "2026-10-14").query("pollster == 'PoderData'").poll_id) == {"BR-01209/2026"}
