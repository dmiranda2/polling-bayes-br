import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from historical_error import (
    pair_ilr,
    pair_ilr_sampling_var,
    load_results,
    extract_window_errors,
    fit_historical_model,
    jackknife,
    loo_by_election,
)


def test_pair_ilr_ratio_invariant_to_common_renormalization():
    z1 = pair_ilr(0.45, 0.40)
    z2 = pair_ilr(45 / 85, 40 / 85)
    assert abs(z1 - z2) < 1e-12


def test_pair_sampling_variance_positive():
    v = pair_ilr_sampling_var(0.45, 0.40, 2000)
    assert v > 0
    assert math.isfinite(v)


def test_extract_window_latest_poll_per_institute(tmp_path):
    results_path = tmp_path / "results.csv"
    pd.DataFrame([
        {
            "election_year": 2022,
            "election_date": "2022-10-02",
            "reference_candidate": "Lula",
            "reference_party": "PT",
            "opponent_candidate": "Jair Bolsonaro",
            "opponent_party": "PL",
            "reference_votes": 57,
            "opponent_votes": 51,
            "total_valid_votes": 118,
            "reference_aliases": "Lula",
            "opponent_aliases": "Jair Bolsonaro|Bolsonaro",
            "source_url": "x",
        }
    ]).to_csv(results_path, index=False)
    results = load_results(results_path)
    rows = []
    for date, poll_id, inst, lula, bol in [
        ("2022-09-28", "a1", "A", 45, 40),
        ("2022-10-01", "a2", "A", 48, 41),
        ("2022-09-30", "b1", "B", 47, 42),
    ]:
        for cand, pct in [("Lula", lula), ("Jair Bolsonaro", bol), ("Ciro", 8)]:
            rows.append({
                "ano": 2022, "cargo": "presidente", "data": date,
                "instituto": inst, "turno": 1, "nome_candidato": cand,
                "percentual": pct, "sigla_uf": None, "tipo": "Estimulada",
                "id_pesquisa": poll_id, "id_cenario": "1", "tipo_voto": "Votos Totais",
                "quantidade_entrevistas": 2000, "margem_mais": 2.0, "condicao": 0,
            })
    polls = pd.DataFrame(rows)
    out, audit = extract_window_errors(polls, results, 7)
    assert len(out) == 2
    assert set(out["poll_id"]) == {"a2", "b1"}
    assert int(audit.loc[0, "institutes_retained"]) == 2


def test_fit_recovers_positive_mean_synthetic():
    rng = np.random.default_rng(123)
    rows = []
    pollsters = ["A", "B", "C", "D"]
    true_mu = 0.08
    year_effect = {2002: -0.02, 2006: 0.00, 2010: 0.03, 2014: -0.01, 2018: 0.01, 2022: 0.12}
    house = {"A": 0.02, "B": -0.01, "C": 0.0, "D": -0.005}
    for year in year_effect:
        for p in pollsters:
            rows.append({
                "election_year": year,
                "pollster": p,
                "pair_error_ilr": true_mu + year_effect[year] + house[p] + rng.normal(0, 0.015),
                "sampling_var_ilr": 0.01**2,
            })
    d = pd.DataFrame(rows)
    fit = fit_historical_model(d, free_mean=True)
    assert 0.03 < fit.mu < 0.14
    assert fit.tau_e > 0
    assert fit.tau_h > 0
    jk = jackknife(d, free_mean=True)
    assert set(jk["excluded_year"]) == set(year_effect)


def test_loo_uses_same_observed_target_and_baseline_for_competing_means(tmp_path):
    years = [2002, 2006, 2010, 2014]
    rows = []
    for k, year in enumerate(years):
        for j, pollster in enumerate(["A", "B", "C"]):
            rows.append({
                "election_year": year,
                "pollster": pollster,
                "pair_error_ilr": 0.03 + 0.01 * k + 0.002 * j,
                "sampling_var_ilr": 0.015**2,
            })
    d = pd.DataFrame(rows)
    results = pd.DataFrame([{
        "election_year": year,
        "result_ref_share": 0.45,
        "result_opp_share": 0.40,
    } for year in years])
    free = loo_by_election(d, results, free_mean=True).sort_values("heldout_year").reset_index(drop=True)
    zero = loo_by_election(d, results, free_mean=False).sort_values("heldout_year").reset_index(drop=True)
    assert np.allclose(free["observed_consensus_ilr"], zero["observed_consensus_ilr"])
    assert np.allclose(free["baseline_2p5_log_score"], zero["baseline_2p5_log_score"])
    assert np.allclose(free["baseline_2p5_pred_mean_ilr"], zero["baseline_2p5_pred_mean_ilr"])
    assert np.allclose(free["baseline_2p5_pred_sd_ilr"], zero["baseline_2p5_pred_sd_ilr"])


def test_extract_excludes_election_day_rows(tmp_path):
    results_path = tmp_path / "results.csv"
    pd.DataFrame([{
        "election_year": 2022, "election_date": "2022-10-02",
        "reference_candidate": "Lula", "reference_party": "PT",
        "opponent_candidate": "Jair Bolsonaro", "opponent_party": "PL",
        "reference_votes": 57, "opponent_votes": 51, "total_valid_votes": 118,
        "reference_aliases": "Lula", "opponent_aliases": "Jair Bolsonaro|Bolsonaro",
        "source_url": "x",
    }]).to_csv(results_path, index=False)
    results = load_results(results_path)
    rows=[]
    for date,pid in [("2022-10-01","pre"),("2022-10-02","exit")]:
        for cand,pct in [("Lula",48),("Jair Bolsonaro",42)]:
            rows.append({
                "ano":2022,"cargo":"presidente","data":date,"instituto":"A",
                "turno":1,"nome_candidato":cand,"percentual":pct,"sigla_uf":None,
                "tipo":"Estimulada","id_pesquisa":pid,"id_cenario":"1",
                "tipo_voto":"Votos Totais","quantidade_entrevistas":2000,
                "margem_mais":2.0,"condicao":0,
            })
    out,_=extract_window_errors(pd.DataFrame(rows),results,7)
    assert set(out["poll_id"]) == {"pre"}