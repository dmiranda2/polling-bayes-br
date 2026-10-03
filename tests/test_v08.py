from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from common import parse_num, survey_key
from composition import project_trajectory_to_simplex
from fetch_data import append_manual, fetch_2018
from model import _continuity_probability
from preprocess import make_complete_composition, to_valid_shares
from report import write_report

CFG = json.load(open(ROOT / "config.json", encoding="utf-8"))


def row(candidate, pct, scenario="1º turno", poll_id="BR-X/2026", pollster="Teste"):
    return dict(
        election_year=2026, round=1, poll_id=poll_id, pollster=pollster,
        pollster_source=pollster, field_start="2026-10-01", field_end="2026-10-02",
        publish_date="2026-10-03", method="desconhecido", scenario=scenario,
        candidate=candidate, pct=pct, n=1200, moe=2.0, source_url="x", source="test",
    )


def test_total_to_valid():
    d = pd.DataFrame([row("A", 40), row("B", 30), row("brancos e nulos", 20), row("não sabe", 10)])
    out, audit = to_valid_shares(d, CFG)
    got = dict(zip(out.candidate, out.pct))
    assert abs(got["A"] - 57.142857) < 1e-5
    assert abs(got["B"] - 42.857143) < 1e-5
    assert audit.iloc[0].vote_basis == "total_with_nonvalid"


def test_published_valid_is_not_renormalized():
    d = pd.DataFrame([row("A", 60, "1º turno - válidos"), row("B", 38, "1º turno - válidos")])
    out, audit = to_valid_shares(d, CFG)
    assert dict(zip(out.candidate, out.pct)) == {"A": 60.0, "B": 38.0}
    assert audit.iloc[0].vote_basis == "published_valid"


def test_manual_valid_share_wins_over_total_share():
    d = pd.DataFrame([row("A", 42), row("B", 38)])
    d["pct_valid"] = [45.0, 40.0]
    d["manual_override"] = True
    out, _ = to_valid_shares(d, CFG)
    assert dict(zip(out.candidate, out.pct)) == {"A": 45.0, "B": 40.0}


def test_ambiguous_group_is_dropped():
    d = pd.DataFrame([row("A", 42), row("B", 38)])
    out, audit = to_valid_shares(d, CFG)
    assert out.empty
    assert audit.iloc[0].action == "dropped"


def test_historical_candidate_only_total_fallback_requires_full_modeled_ballot():
    # This mimics a 2018 source table which omitted non-valid rows.  It is only
    # usable because every modeled 2018 ballot coordinate appears and the
    # candidate mass is clearly a total-vote mass rather than a valid-vote table.
    names = ["Jair Bolsonaro", "Fernando Haddad", "Ciro Gomes", "Geraldo Alckmin", "João Amoêdo"]
    d = pd.DataFrame([
        {**row(name, pct, poll_id="2018-A"), "election_year": 2018}
        for name, pct in zip(names, [35, 25, 12, 5, 3])
    ])
    out, audit = to_valid_shares(d, CFG)
    assert audit.iloc[0].vote_basis == "total_implicit_nonvalid"
    assert audit.iloc[0].action == "kept"
    assert abs(out.pct.sum() - 100.0) < 1e-9

    incomplete = d[d.candidate.ne("João Amoêdo")].copy()
    out, audit = to_valid_shares(incomplete, CFG)
    assert out.empty
    assert audit.iloc[0].vote_basis == "ambiguous"


def test_fetch_2018_retains_nonvalid_response_rows(monkeypatch):
    import fetch_data
    raw = """ano;cargos_id;ambito;tipo_id;condicao;turno;num_registro;instituto;data_pesquisa;cenario_descricao;candidato;percentual;qtd_entrevistas;margem_mais\n2018;3;BR;2;0;1;BR-1/2018;Teste;2018-09-20;principal;Jair Bolsonaro;40;1000;3\n2018;3;BR;2;1;1;BR-1/2018;Teste;2018-09-20;principal;Branco/nulo;15;1000;3\n2018;3;BR;2;2;1;BR-1/2018;Teste;2018-09-20;principal;NS/NR;5;1000;3\n"""
    monkeypatch.setattr(fetch_data, "_download", lambda _: raw.encode("utf-8"))
    monkeypatch.setattr(fetch_data, "_attach_tse", lambda df, year: df)
    got = fetch_2018()
    assert set(got.candidate) == {"Jair Bolsonaro", "Branco/nulo", "NS/NR"}


def test_report_labels_latent_interval_and_threshold(tmp_path):
    top = pd.DataFrame([{
        "candidate": "A", "median_pct": 44.5, "lower_80_pct": 43.1,
        "upper_80_pct": 45.9, "distance_to_50_pp": -5.5, "n_polls": 12,
    }])
    target = tmp_path / "report.md"
    write_report(target, top, "2026-10-03")
    report = target.read_text(encoding="utf-8")
    assert "IC 80% é da média latente das pesquisas" in report
    assert "Distância da média latente a 50%" in report
    assert "intervalo do resultado eleitoral" in report
    assert "sigma_0 arbitrário" in report


def test_zero_continuity_depends_on_n():
    p = _continuity_probability(0.0, 1200)
    assert 0 < p < 0.001  # below 0.1%, not the old fixed 0.5%
    assert _continuity_probability(0.0, 5000) < p


def test_complete_composition_and_simplex_projection():
    rows = []
    for k, vals in [("P1", (45, 42, 5)), ("P2", (46, 41, 4))]:
        for cand, pct in zip(["A", "B", "C"], vals):
            r = row(cand, pct, poll_id=k)
            rows.append(r)
    d = pd.DataFrame(rows)
    d["_survey_key"] = survey_key(d)
    comp, audit = make_complete_composition(d, ["A", "B", "C"])
    sums = comp.groupby("_survey_key")["pct"].sum()
    assert np.allclose(sums, 100.0)
    assert set(comp.candidate) == {"A", "B", "C", "Outros candidatos"}

    # Synthetic marginal posterior; projection must enforce the simplex draw-wise.
    tr = pd.DataFrame([
        dict(date="2026-10-03", candidate=c, median_pct=m, sd_logit=.05,
             lower_80_pct=m-1, upper_80_pct=m+1, lower_95_pct=m-2, upper_95_pct=m+2)
        for c, m in [("A", 46), ("B", 43), ("C", 5), ("Outros candidatos", 2)]
    ])
    projected, _ = project_trajectory_to_simplex(tr, comp, CFG, draws=1000, seed=1)
    # Medians need not add exactly to 100, but the gap should be tiny after joint projection.
    assert abs(projected.median_pct.sum() - 100) < 1.0


def test_missing_poll_ids_still_make_distinct_survey_keys():
    d = pd.DataFrame([
        {**row("A", 40, poll_id=""), "field_end": "2026-09-01", "publish_date": "2026-09-02"},
        {**row("A", 41, poll_id=""), "field_end": "2026-09-10", "publish_date": "2026-09-11"},
    ])
    assert survey_key(d).nunique() == 2


def test_parse_num_brazilian_thousands_decimal():
    assert parse_num("1.234,5") == 1234.5
    assert parse_num("43,1%") == 43.1


def test_manual_override_policy(monkeypatch=False):
    import fetch_data
    original = fetch_data._attach_tse
    fetch_data._attach_tse = lambda df, year: df
    try:
        auto = pd.DataFrame([{**row("A", 99), "source": "auto"}])
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "manual.csv"
            man = pd.DataFrame([{**row("A", 42), "pct_valid": 45, "manual_override": True, "source": "manual"}])
            man.to_csv(path, index=False)
            out = append_manual(auto, path)
            assert float(out.loc[out.candidate.eq("A"), "pct"].iloc[0]) == 42.0
            assert float(out.loc[out.candidate.eq("A"), "pct_valid"].iloc[0]) == 45.0
    finally:
        fetch_data._attach_tse = original


def test_candidate_filter_renormalizes_only_surveys_with_removed_candidate():
    from candidate_status import apply_current_candidate_filter
    rows = [
        row("Lula", 40, poll_id="P1"), row("Flávio Bolsonaro", 38, poll_id="P1"),
        row("Leonardo Avalanche", 2, poll_id="P1"), row("Ronaldo Caiado", 20, poll_id="P1"),
        row("Lula", 42, poll_id="P2"), row("Flávio Bolsonaro", 40, poll_id="P2"),
        row("Ronaldo Caiado", 15, poll_id="P2"),
    ]
    d = pd.DataFrame(rows)
    out, audit = apply_current_candidate_filter(d, CFG, "2026-10-03", base_dir=ROOT)
    p1 = out[out.poll_id.eq("P1")]
    assert "Leonardo Avalanche" not in set(p1.candidate)
    assert abs(p1.pct.sum() - 100.0) < 1e-9
    p2 = out[out.poll_id.eq("P2")]
    # No excluded coordinate in P2: preserve the published incomplete sum (97).
    assert abs(p2.pct.sum() - 97.0) < 1e-9
    leo = audit[audit.candidate.eq("Leonardo Avalanche")].iloc[0]
    assert int(leo.unique_polls) == 1


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"v0.8 tests: {len(tests)} OK")


def test_offline_tse_2022_field_date_override():
    from preprocess import apply_historical_field_date_overrides
    d = pd.DataFrame([{
        **row("Lula", 48, poll_id="BR-00245/2022", pollster="Datafolha"),
        "election_year": 2022, "field_start": "2022-10-01", "field_end": "2022-10-01",
        "publish_date": "2022-10-01",
    }])
    out = apply_historical_field_date_overrides(d, 2022)
    assert str(pd.Timestamp(out.iloc[0].field_start).date()) == "2022-09-30"
    assert str(pd.Timestamp(out.iloc[0].field_end).date()) == "2022-10-01"