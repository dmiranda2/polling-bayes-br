"""Independent retrospective first-round diagnostic regression checks."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import pytest
from first_round_counterfactual import compare, correct_pair, write_report


def build(tmp_path: Path, *, round_no=1, future=False):
    now = tmp_path / "nowcast.csv"
    pd.DataFrame({
        "candidate": ["Lula", "Flávio Bolsonaro", "Outros candidatos"],
        "median_pct": [45.61, 43.15, 11.24],
        "last_poll_date": ["2026-10-02"] * 3,
    }).to_csv(now, index=False)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "as_of": "2026-10-03", "historical_bias_transfer": False,
        "model": "joint_ilr_gaussian_reml_structured",
    }))
    hist = tmp_path / "history"
    hist.mkdir()
    pd.DataFrame([
        {"election_round": round_no, "window_label": "1:7", "model": model,
         "mu_ilr": mu, "n_elections": 6, "n_polls": 38}
        for model, mu in [("free_mean", 0.087523), ("zero_mean", 0.)]
    ]).to_csv(hist / "historical_fit_summary.csv", index=False)
    years = [2002, 2006, 2010, 2014, 2018, 2022] + ([2026] if future else [])
    pd.DataFrame([
        {"election_round": round_no, "window_label": "1:7", "election_year": y}
        for y in years
    ]).to_csv(hist / "historical_poll_errors.csv", index=False)
    pd.DataFrame([
        {"election_round": round_no, "window_label": "1:7",
         "heldout_year": year, "model": model,
         "log_score": 0.8 if model == "free_mean" else 0.9,
         "baseline_2p5_log_score": 1.}
        for year in years[:6] for model in ("free_mean", "zero_mean")
    ]).to_csv(hist / "historical_loo.csv", index=False)
    return now, manifest, hist


def test_pair_shift_correct_and_other_candidates_unchanged(tmp_path):
    now, manifest, hist = build(tmp_path)
    table, audit = compare(now, manifest, hist, "2026-10-03")
    r = table.set_index("candidate")
    assert np.isclose(table["delta_pp"].sum(), 0)
    assert r.loc["Lula", "experimental_corrected_pct"] < 45.61
    assert r.loc["Flávio Bolsonaro", "experimental_corrected_pct"] > 43.15
    assert r.loc["Outros candidatos", "experimental_corrected_pct"] == 11.24
    assert not audit["free_mean_wins_loo"]
    assert not audit["is_v08_quality_weighted_model"]
    assert not audit["second_round_pipeline_modified"]
    write_report(table, audit, tmp_path / "out")
    assert (tmp_path / "out" / "comparison_2026-10-03.csv").exists()
    assert "NÃO É PREVISÃO ARQUIVADA" in (tmp_path / "out" / "report_2026-10-03.md").read_text()


def test_ilr_definition_is_preserved():
    a, b = correct_pair(45.61, 43.15, 0.087523)
    assert np.isclose(a + b, 88.76)
    assert np.isclose(
        (np.log(45.61/43.15) - np.log(a/b))/np.sqrt(2), 0.087523
    )


def test_rejects_second_round_calibration(tmp_path):
    a,b,c = build(tmp_path, round_no=2)
    with pytest.raises(ValueError, match="second-round"):
        compare(a,b,c,"2026-10-03")


def test_rejects_future_results_in_historical_training(tmp_path):
    a,b,c = build(tmp_path, future=True)
    with pytest.raises(ValueError, match="look-ahead"):
        compare(a,b,c,"2026-10-03")


def test_rejects_post_election_cutoff(tmp_path):
    a,b,c = build(tmp_path)
    with pytest.raises(ValueError, match="PRE-ELECTION"):
        compare(a,b,c,"2026-10-04")


def test_rejects_mismatched_manifest(tmp_path):
    a,b,c = build(tmp_path)
    with pytest.raises(ValueError, match="manifest date"):
        compare(a,b,c,"2026-10-02")


def test_refuses_double_correction(tmp_path):
    a,b,c = build(tmp_path)
    info=json.loads(b.read_text())
    info["historical_bias_transfer"]=True
    b.write_text(json.dumps(info))
    with pytest.raises(ValueError, match="double-correct"):
        compare(a,b,c,"2026-10-03")


def test_rejects_unknown_round_metadata(tmp_path):
    a,b,c=build(tmp_path)
    p=c/"historical_fit_summary.csv"
    d=pd.read_csv(p).drop(columns="election_round")
    d.to_csv(p,index=False)
    with pytest.raises(ValueError, match="audit columns"):
        compare(a,b,c,"2026-10-03")
