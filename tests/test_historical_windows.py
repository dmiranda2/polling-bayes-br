"""Separation of presidential rounds and pre-election historical time windows."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import historical_error as first
import historical_second_round as second
from historical_calibration import (
    parse_window_range, parse_windows, module_for_round, window_label,
)
from runoff_nowcast import _calibrate_historical


@pytest.mark.parametrize(
    ("value", "expected"),
    [("7", (1, 7)), ("1:7", (1, 7)), ("14:21", (14, 21)),
     ("1:1", (1, 1)), ("21:21", (21, 21))],
)
def test_window_syntax(value, expected):
    assert parse_window_range(value) == expected


@pytest.mark.parametrize("bad", ["0:7", "21:14", "-2:21", "1:0", "3:150", "", "a:b", "1:2:3"])
def test_invalid_window_is_rejected(bad):
    with pytest.raises(ValueError):
        parse_window_range(bad)


def test_window_list_has_no_duplicate_windows():
    assert parse_windows("7,1:7,14:21") == [(1, 7), (14, 21)]
    assert window_label((14, 21)) == "14:21"


def _result(year, date):
    d = pd.DataFrame([{
        "election_year": year, "election_date": date,
        "reference_candidate": "Lula", "opponent_candidate": "Bolsonaro",
        "reference_aliases": "Lula", "opponent_aliases": "Bolsonaro",
        "reference_votes": 55, "opponent_votes": 45,
        "total_valid_votes": 100,
    }])
    d["election_date"] = pd.to_datetime(d["election_date"])
    d["result_ref_share"] = 0.55
    d["result_opp_share"] = 0.45
    d["result_pair_ilr"] = first.pair_ilr(.55, .45)
    return d


def _polls_for_both_rounds():
    rows = []
    cases = [
        (1, "2022-09-12", "first_early", "A", 48, 42),
        (1, "2022-09-28", "first_late", "A", 49, 41),
        (1, "2022-10-02", "first_election_day", "A", 50, 40),
        (2, "2022-10-12", "second_early", "A", 52, 48),
        (2, "2022-10-26", "second_late", "A", 51, 49),
        (2, "2022-10-30", "second_election_day", "A", 51, 49),
    ]
    for round_, date, poll_id, institute, lula, other in cases:
        for person, pct in [("Lula", lula), ("Bolsonaro", other)]:
            rows.append({
                "ano": 2022, "cargo": "Presidente", "turno": round_,
                "data": date, "instituto": institute,
                "nome_candidato": person, "percentual": pct, "sigla_uf": "BR",
                "tipo": "Estimulada", "id_pesquisa": poll_id,
                "id_cenario": "1", "tipo_voto": "Votos totais",
                "quantidade_entrevistas": 2000, "margem_mais": 2,
                "condicao": 0,
            })
    return pd.DataFrame(rows)


def test_rounds_and_historical_windows_do_not_cross():
    polls = _polls_for_both_rounds()
    for turn, module, election_date, expected_early, expected_late in [
        (1, first, "2022-10-02", "first_early", "first_late"),
        (2, second, "2022-10-30", "second_early", "second_late"),
    ]:
        result = _result(2022, election_date)
        early, ea = module.extract_window_errors(polls, result, 21, min_days_before=14)
        late, la = module.extract_window_errors(polls, result, 7, min_days_before=1)
        assert set(early["poll_id"]) == {expected_early}
        assert set(late["poll_id"]) == {expected_late}
        assert early["election_round"].eq(turn).all()
        assert late["election_round"].eq(turn).all()
        assert early["window_label"].unique().tolist() == ["14:21"]
        assert late["window_label"].unique().tolist() == ["1:7"]
        assert ea["window_min_days"].eq(14).all()
        assert la["window_min_days"].eq(1).all()
    assert module_for_round(1) is first
    assert module_for_round(2) is second


def test_baseline_uses_no_held_out_election_outcome():
    a = pd.Series({"result_ref_share": 0.9, "result_opp_share": 0.1})
    b = pd.Series({"result_ref_share": 0.4, "result_opp_share": 0.6})
    for m in (first, second):
        assert m._baseline_ilr_sd_from_result(a) == m._baseline_ilr_sd_from_result(b)
        assert np.isclose(m._baseline_ilr_sd_from_result(a), 2*np.sqrt(2)*0.025)


def test_runoff_refuses_first_round_historical_cache(tmp_path: Path):
    csv = tmp_path / "history.csv"
    pd.DataFrame([{
        "election_round": 1, "window_min_days": 1, "window_days": 7,
        "election_year": 2022, "pair_error_ilr": 0.01,
    }]).to_csv(csv, index=False)
    got = _calibrate_historical(csv, tmp_path / "unused.csv", "1:7")
    assert got["status"] == "external_fallback"
    assert not got["directional_mean_used"]
    assert any("mixed-round" in msg for msg in got["reasons"])


def test_runoff_windows_can_be_changed_without_past_polling_leak(tmp_path: Path):
    csv = tmp_path / "history.csv"
    pd.DataFrame([
        {"election_round": 2, "window_min_days": 1, "window_days": 7,
         "election_year": 2018, "pair_error_ilr": 0.01},
        {"election_round": 2, "window_min_days": 14, "window_days": 21,
         "election_year": 2018, "pair_error_ilr": 0.02},
    ]).to_csv(csv, index=False)
    recent = _calibrate_historical(csv, tmp_path / "unused.csv", "1:7")
    older = _calibrate_historical(csv, tmp_path / "unused.csv", "14:21")
    assert recent["historical_window_range"] == "1:7"
    assert older["historical_window_range"] == "14:21"
    assert recent["status"] == older["status"] == "external_fallback"
