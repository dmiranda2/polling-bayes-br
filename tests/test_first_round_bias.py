"""Controls for 10 October calendar and conditional 1T bias sensitivity."""
from pathlib import Path
import math

import numpy as np
import pandas as pd
import pytest

from first_round_bias import (
    read_first_round_bias, apply_first_round_bias, audit_calendar,
)
from runoff_nowcast import estimate, read_current_polls

ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "data/manual_second_round_2026.csv"
BIAS = ROOT / "data/first_round_pollster_bias_2026.csv"
CAL = ROOT / "data/scheduled_polls_2026_10_10.csv"
ALIASES = ROOT / "data/pollster_aliases.csv"


def _fallback():
    return {
        "status": "external_fallback", "directional_mean_used": False,
        "mu_ilr": 0, "var_mu_ilr": 0,
        "common_sd_ilr": 2.5 * 2 * math.sqrt(2) / 100,
        "tau_p_ilr": 0, "fit": None,
    }


def test_all_ten_bias_entries_imply_same_flavio_minus_lula_margin():
    d = read_first_round_bias(BIAS, ALIASES)
    assert len(d) == 10
    implied = (d["first_round_flavio_pct"] - d["first_round_lula_pct"]
               - d["bias_flavio_minus_lula_pp"])
    assert np.allclose(implied, 1.8)
    assert not d["canonical_pollster"].duplicated().any()


def test_sign_and_missing_institute_not_silently_imputed():
    raw = read_current_polls(CURRENT, "2026-10-10")
    bias = read_first_round_bias(BIAS, ALIASES)
    a = apply_first_round_bias(raw, bias, "none", ALIASES).set_index("pollster")
    b = apply_first_round_bias(raw, bias, "first_round_2026", ALIASES).set_index("pollster")
    assert np.isclose(a.loc["Datafolha", "lula_valid_pct_after_bias"], 48)
    # Datafolha: margin F-L first-round bias=-3.8 -> L -1.9 pp in 2T.
    assert np.isclose(b.loc["Datafolha", "lula_valid_pct_after_bias"], 46.1)
    assert np.isclose(b.loc["PoderData", "lula_valid_pct_after_bias"], 45.6)
    assert np.isclose(b.loc["Vox Brasil", "lula_valid_pct_after_bias"], 50.86)
    assert not b.loc["Vox Brasil", "first_round_bias_available"]
    assert not b.loc["Vox Brasil", "first_round_bias_applied"]
    assert b["lula_valid_pct_after_bias"].add(b["flavio_valid_pct_after_bias"]).eq(100).all()


def test_same_inputs_both_versions_and_mixed_atlas_remains_sensitivity():
    bias = read_first_round_bias(BIAS, ALIASES)
    for mixed, n in ((False, 3), (True, 4)):
        polls = read_current_polls(CURRENT, "2026-10-10", include_mixed=mixed)
        raw, pr = estimate(polls, _fallback(), "2026-10-10", draws=5000,
                           bias_mode="none", first_round_bias=bias, aliases_path=ALIASES)
        corr, pc = estimate(polls, _fallback(), "2026-10-10", draws=5000,
                            bias_mode="first_round_2026", first_round_bias=bias, aliases_path=ALIASES)
        assert raw.iloc[0]["n_surveys"] == corr.iloc[0]["n_surveys"] == n
        assert set(pr["poll_id"]) == set(pc["poll_id"])
        assert raw.iloc[0]["n_bias_applied"] == 0
        assert corr.iloc[0]["n_bias_applied"] == n-1  # only Vox Brasil missing
        assert corr.iloc[0]["polling_lula_pct"] < raw.iloc[0]["polling_lula_pct"]
        assert corr.iloc[0]["polling_flavio_pct"] > raw.iloc[0]["polling_flavio_pct"]


def test_calendar_is_not_poll_observation_and_conflicts_flagged():
    c = audit_calendar(CAL)
    assert len(c) == 19
    assert (c["scope"] == "national").sum() == 11
    assert (c["scope"] == "regional").sum() == 8
    assert set(c.loc[c["date_conflict"], "poll_id"]) == {"BR-05187", "BR-06778"}
    assert c["data_status"].eq("scheduled_only_no_2026_second_round_result").all()
    existing = read_current_polls(CURRENT, "2026-10-10")
    assert len(existing) == 3
    assert "DataTrends" not in existing["pollster"].tolist()


def test_rejects_bias_sign_inconsistency(tmp_path):
    data = pd.read_csv(BIAS)
    data.loc[0, "bias_flavio_minus_lula_pp"] = +3.8
    path = tmp_path / "bad.csv"
    data.to_csv(path, index=False)
    with pytest.raises(ValueError, match="inconsistent"):
        read_first_round_bias(path, ALIASES)


def test_rejects_no_bias_file_in_corrected_mode():
    raw = read_current_polls(CURRENT, "2026-10-10")
    with pytest.raises(ValueError, match="requires"):
        apply_first_round_bias(raw, None, "first_round_2026", ALIASES)
