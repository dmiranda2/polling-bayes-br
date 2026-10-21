"""Regression checks for the data-only October 21 archived update."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
import pytest
from runoff_nowcast import read_current_polls
ROOT=Path(__file__).resolve().parents[1]
SNAP=ROOT/'snapshots/2026-10-21'


def test_oct21_nine_additions_and_full_selection():
    raw=pd.read_csv(SNAP/'data/input_polls.csv')
    assert len(raw)==68 and raw.poll_id.nunique()==34
    assert not raw.duplicated(['poll_id','candidate']).any()
    s=read_current_polls(SNAP/'data/input_polls.csv','2026-10-21')
    assert len(s)==19 and s.pollster.is_unique
    assert s.loc[s.pollster.eq('Quaest'),'poll_id'].item()=='BR-08535/2026'


def test_quaest_is_explicitly_derived_palver_is_published():
    s=read_current_polls(SNAP/'data/input_polls.csv','2026-10-21').set_index('pollster')
    assert s.loc['Quaest','basis']=='derived_valid_from_total'
    assert s.loc['Quaest','lula_valid_pct']==pytest.approx(100*44/89)
    assert s.loc['Palver','basis']=='published_valid'
    assert s.loc['Palver','lula_valid_pct']==49


def test_prior_cutoff_preserved_and_late_datatrends_not_backfilled():
    prior=SNAP/'prior_2026-10-19_1017'
    before=(prior/'valores_diarios.csv').read_bytes().splitlines(keepends=True)
    after=(SNAP/'valores_diarios.csv').read_bytes().splitlines(keepends=True)
    assert before==after[:len(before)]
    assert 'BR-04454/2026' not in set(pd.read_csv(SNAP/'daily_inputs/2026-10-19.csv').poll_id)
    assert 'BR-04454/2026' in set(pd.read_csv(SNAP/'daily_inputs/2026-10-20.csv').poll_id)


def test_output_modes_and_separate_quantities():
    d=pd.read_csv(SNAP/'model_comparison_core_2026-10-21.csv')
    assert len(d)==24 and d.execution_status.eq('executed').sum()==22
    primary=d[d.historical_window.eq('7:14')]
    recent=primary[primary.selection.eq('publication_19_21')].set_index('bias_mode')
    assert set(recent.n_surveys)=={12}
    assert recent.loc['none','polling_lula_pct']==pytest.approx(48.871469,abs=1e-6)
    assert recent.loc['experimental_free_mean_2t','polling_lula_pct']==recent.loc['second_round_history','polling_lula_pct']
    assert recent.loc['experimental_free_mean_2t','counterfactual_lula_pct']!=recent.loc['second_round_history','counterfactual_lula_pct']
    weights=pd.read_csv(SNAP/'daily_weights.csv')
    assert weights.house_mean_applied_ilr.eq(0).all()
    assert np.allclose(weights.groupby('as_of').weight_share_pct.sum(),100)


def test_model_source_and_calibration_are_frozen():
    for name,digest in json.loads((SNAP/'source_code_sha256.json').read_text()).items():
        assert hashlib.sha256((ROOT/'src'/name).read_bytes()).hexdigest()==digest
    assert json.loads((SNAP/'calibration_all_windows.json').read_text())==json.loads((SNAP/'prior_2026-10-19_1017/calibration_all_windows.json').read_text())
