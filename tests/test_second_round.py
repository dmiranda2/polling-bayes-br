from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from historical_second_round import (
    extract_window_errors, load_results, pair_ilr,
)
from runoff_nowcast import (
    _candidate_pct, estimate, read_current_polls,
)

ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "data" / "manual_second_round_2026.csv"
RESULTS = ROOT / "data" / "presidential_second_round_results.csv"


def test_official_results_are_second_round_and_counts_match():
    d = load_results(RESULTS)
    assert len(d) == 6
    assert d["election_year"].tolist() == [2002, 2006, 2010, 2014, 2018, 2022]
    assert np.allclose(
        d["reference_votes"] + d["opponent_votes"], d["total_valid_votes"]
    )
    assert d.loc[d["election_year"].eq(2018), "result_pair_ilr"].iloc[0] < 0


def test_historical_extractor_only_second_round_and_not_election_day():
    d = pd.DataFrame([{
        "election_year": 2022, "election_date": "2022-10-30",
        "reference_candidate": "Lula", "opponent_candidate": "Bolsonaro",
        "reference_votes": 60, "opponent_votes": 58,
        "total_valid_votes": 118,
        "reference_aliases": "Lula",
        "opponent_aliases": "Bolsonaro",
    }])
    d["election_date"] = pd.to_datetime(d["election_date"])
    d["result_ref_share"] = d["reference_votes"] / d["total_valid_votes"]
    d["result_opp_share"] = d["opponent_votes"] / d["total_valid_votes"]
    d["result_pair_ilr"] = pair_ilr(60, 58)
    rows = []
    for round_, date, poll_id in [
        (1, "2022-10-27", "first_round"),
        (2, "2022-10-27", "proper_runoff"),
        (2, "2022-10-30", "election_day"),
    ]:
        for cand, pct in [("Lula", 49), ("Bolsonaro", 47)]:
            rows.append({
                "ano": 2022, "cargo": "presidente", "data": date,
                "instituto": "A", "turno": round_,
                "nome_candidato": cand, "percentual": pct,
                "sigla_uf": "BR", "tipo": "Estimulada",
                "id_pesquisa": poll_id, "id_cenario": "1",
                "tipo_voto": "Votos Totais",
                "quantidade_entrevistas": 2000,
                "margem_mais": 2.0, "condicao": 0,
            })
    error, audit = extract_window_errors(pd.DataFrame(rows), d, 7)
    assert error["poll_id"].tolist() == ["proper_runoff"]
    assert error["election_year"].tolist() == [2022]
    assert audit.loc[0, "institutes_retained"] == 1


def test_atlas_is_only_a_sensitivity():
    strict = read_current_polls(CURRENT, "2026-10-09")
    inclusive = read_current_polls(CURRENT, "2026-10-09", include_mixed=True)
    assert set(strict["pollster"]) == {"PoderData", "Vox Brasil", "Datafolha"}
    assert set(inclusive["pollster"]) == set(strict["pollster"]) | {"AtlasIntel"}
    assert not strict["is_mixed_field"].any()
    assert inclusive["is_mixed_field"].sum() == 1
    assert strict["lula_valid_pct"].add(strict["flavio_valid_pct"]).between(99.999, 100.001).all()


def test_asof_cannot_see_not_yet_published_polls():
    strict = read_current_polls(CURRENT, "2026-10-08")
    assert set(strict["pollster"]) == {"PoderData", "Datafolha"}


def test_external_fallback_is_reported_and_symmetric():
    data = read_current_polls(CURRENT, "2026-10-09")
    calib = {
        "status": "external_fallback", "directional_mean_used": False,
        "mu_ilr": 0.0, "var_mu_ilr": 0.0,
        "common_sd_ilr": 0.070710678, "tau_p_ilr": 0.0, "fit": None,
    }
    result, used = estimate(data, calib, "2026-10-09", draws=4000)
    r = result.iloc[0]
    assert r["n_surveys"] == 3
    assert not r["directional_mean_used"]
    assert 45 < r["polling_lula_pct"] < 51
    assert r["counterfactual_lula_lo80"] < r["polling_lula_pct"] < r["counterfactual_lula_hi80"]
    assert (used["house_mean_ilr"] == 0).all()


def test_directional_poll_minus_urn_bias_is_subtracted():
    d = read_current_polls(CURRENT, "2026-10-09")
    common = {
        "status": "historical_second_round", "directional_mean_used": True,
        "var_mu_ilr": 0.0, "common_sd_ilr": 0.01, "tau_p_ilr": 0.0, "fit": None,
    }
    a, _ = estimate(d, {**common, "mu_ilr": 0}, "2026-10-09", draws=12000)
    b, _ = estimate(d, {**common, "mu_ilr": 0.1}, "2026-10-09", draws=12000)
    assert b.iloc[0]["counterfactual_lula_pct"] < a.iloc[0]["counterfactual_lula_pct"] - 2


def test_ilr_vote_mapping_is_two_candidate_simplex():
    assert abs(_candidate_pct(0) - 50) < 1e-12
    assert _candidate_pct(0.3) > 50
    assert _candidate_pct(-0.3) < 50
