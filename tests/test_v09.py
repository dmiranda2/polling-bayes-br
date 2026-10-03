import numpy as np
import pandas as pd

from composition import (
    helmert_basis,
    ilr_inverse,
    ilr_transform,
    multinomial_ilr_covariance,
    regularize_composition,
)
from model import fit_nowcast


def test_helmert_basis_is_orthonormal_and_sum_zero():
    h = helmert_basis(7)
    assert h.shape == (7, 6)
    assert np.allclose(h.T @ h, np.eye(6), atol=1e-12)
    assert np.allclose(h.sum(axis=0), 0.0, atol=1e-12)


def test_ilr_roundtrip():
    p = np.array([0.45, 0.41, 0.06, 0.04, 0.025, 0.01, 0.005])
    h = helmert_basis(len(p))
    y = ilr_transform(p, h)
    q = ilr_inverse(y, h)
    assert np.allclose(q, p, atol=1e-12)
    assert np.isclose(q.sum(), 1.0)


def test_zero_regularization_is_sample_size_dependent():
    x = np.array([45.0, 44.0, 6.0, 5.0, 0.0])
    p_small = regularize_composition(x, 500, alpha=0.5)
    p_large = regularize_composition(x, 2000, alpha=0.5)
    assert p_small[-1] > p_large[-1] > 0
    assert np.isclose(p_small.sum(), 1.0)
    assert np.isclose(p_large.sum(), 1.0)


def test_multinomial_ilr_covariance_is_psd():
    p = np.array([0.45, 0.40, 0.08, 0.05, 0.02])
    h = helmert_basis(len(p))
    r = multinomial_ilr_covariance(p, 1000, h)
    assert np.allclose(r, r.T)
    assert np.linalg.eigvalsh(r).min() > 0


def _synthetic_current():
    polls = [
        ("A", "2026-09-20", [45, 41, 8, 6]),
        ("B", "2026-09-22", [44, 42, 8, 6]),
        ("A", "2026-09-25", [46, 41, 7, 6]),
        ("C", "2026-09-27", [45, 42, 7, 6]),
        ("B", "2026-09-29", [46, 42, 6, 6]),
        ("C", "2026-10-01", [46, 43, 6, 5]),
    ]
    cands = ["Lula", "Flávio Bolsonaro", "Candidato C", "Outros candidatos"]
    rows = []
    for i, (house, date, vals) in enumerate(polls):
        for cand, pct in zip(cands, vals):
            rows.append({
                "election_year": 2026,
                "round": 1,
                "scenario": "1º turno",
                "candidate": cand,
                "pct": pct,
                "pollster": house,
                "pollster_key": f"NAME:{house}",
                "field_start": date,
                "field_end": date,
                "publish_date": date,
                "n": 1200,
                "moe": 2.8,
                "poll_id": f"p{i}",
            })
    return pd.DataFrame(rows)


def test_joint_fit_stays_on_simplex_and_ignores_legacy_priors():
    cfg = {
        "current_year": 2026,
        "current_round": 1,
        "scenario_regex": "^1º turno$",
        "default_n": 1200,
        "default_design_effect": 1.5,
        "credible_intervals": [0.8, 0.95],
        "posterior_draws": 500,
        "posterior_seed": 418,
        "reml_multistart": 1,
        "reml_maxiter": 30,
        "external_election_error_enabled": True,
        "external_election_error_sd_pp": 2.5,
    }
    d = _synthetic_current()
    legacy_quality = pd.DataFrame({"pollster_key": ["NAME:A"], "quality_sd_pp": [99.0]})
    legacy_bias = pd.DataFrame({"pollster_key": ["NAME:A"], "candidate": ["Lula"], "bias_pp": [99.0]})
    a, _, _, used_a = fit_nowcast(d, legacy_quality, legacy_bias, cfg, "2026-10-02")
    b, _, _, used_b = fit_nowcast(d, pd.DataFrame(), pd.DataFrame(), cfg, "2026-10-02")
    aa = a.sort_values("candidate").reset_index(drop=True)
    bb = b.sort_values("candidate").reset_index(drop=True)
    assert np.allclose(aa["median_pct"], bb["median_pct"])
    assert np.isclose(aa["point_pct"].sum(), 100.0, atol=1e-8)
    assert (aa["election_upper_80_pct"] - aa["election_lower_80_pct"] >= aa["upper_80_pct"] - aa["lower_80_pct"]).all()
    assert set(used_a["model_version"]) == {"0.9"}
    assert set(used_b["model_version"]) == {"0.9"}