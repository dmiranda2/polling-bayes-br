from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.linalg import block_diag, cho_factor, cho_solve
from scipy.optimize import minimize

from common import coerce_canonical, midpoint_date, survey_key
from composition import (
    helmert_basis,
    ilr_inverse,
    ilr_inverse_rows,
    ilr_transform,
    inverse_ilr_jacobian,
    multinomial_ilr_covariance,
    regularize_composition,
)


@dataclass
class JointGaussianFit:
    candidates: list[str]
    basis: np.ndarray
    surveys: pd.DataFrame
    y: np.ndarray
    sampling_covs: list[np.ndarray]
    times: np.ndarray
    houses: np.ndarray
    beta: np.ndarray
    q_rw: np.ndarray
    sd_house: np.ndarray
    sd_poll: np.ndarray
    reml_nll: float
    V: np.ndarray
    chol_V: tuple[np.ndarray, bool]
    X: np.ndarray
    Vinv_X: np.ndarray
    XtVinvX_inv: np.ndarray
    residual: np.ndarray


def _effective_n(n: float, moe_pp: float, default_n: float, design_effect: float) -> float:
    """Conservative effective sample size from reported n and/or margin of error."""
    vals = []
    if np.isfinite(n) and n > 20:
        vals.append(float(n) / max(float(design_effect), 1.0))
    if np.isfinite(moe_pp) and 0.2 < moe_pp < 20:
        m = float(moe_pp) / 100.0
        vals.append(1.96**2 * 0.25 / (m * m))
    return max(50.0, min(vals) if vals else float(default_n) / max(float(design_effect), 1.0))


def _continuity_probability(pct: float, neff: float) -> float:
    """v0.8 compatibility helper; v0.9 regularizes the full composition jointly."""
    p = float(pct) / 100.0
    eps = 0.5 / max(float(neff) + 1.0, 2.0)
    return float(np.clip(p, eps, 1.0 - eps))


def _candidate_order(d: pd.DataFrame) -> list[str]:
    """Deterministic support order used by the structured ILR covariance.

    The two largest named candidates come first, so the first Helmert balance is
    the leading-candidate contrast.  The residual bucket is always last.
    """
    x = d.copy()
    med = (
        x[~x["candidate"].astype(str).eq("Outros candidatos")]
        .groupby(x["candidate"].astype(str))["pct"]
        .median()
        .sort_values(ascending=False)
    )
    names = list(med.index.astype(str))
    all_names = list(dict.fromkeys(x["candidate"].astype(str)))
    for c in all_names:
        if c != "Outros candidatos" and c not in names:
            names.append(c)
    if "Outros candidatos" in all_names:
        names.append("Outros candidatos")
    return names

def _survey_level_data(d: pd.DataFrame, config: dict) -> tuple[pd.DataFrame, np.ndarray, list[np.ndarray], np.ndarray, list[str], np.ndarray]:
    candidates = _candidate_order(d)
    k = len(candidates)
    if k < 2:
        raise RuntimeError("Joint compositional model needs at least two candidates")
    basis = helmert_basis(k)
    default_n = float(config.get("default_n", 1200))
    design_effect = float(config.get("default_design_effect", 1.5))

    rows = []
    ys: list[np.ndarray] = []
    covs: list[np.ndarray] = []
    expected = set(candidates)

    grouped = d.groupby("_survey_key", sort=False)
    for key, g in grouped:
        names = set(g["candidate"].astype(str))
        if names != expected or g["candidate"].astype(str).duplicated().any():
            raise RuntimeError(
                f"Incomplete compositional survey {key}: expected {len(expected)} unique parts, got {len(names)}"
            )
        gg = g.set_index(g["candidate"].astype(str)).reindex(candidates)
        shares = pd.to_numeric(gg["pct"], errors="coerce").to_numpy(dtype=float)
        if not np.isfinite(shares).all() or np.any(shares < 0):
            raise RuntimeError(f"Invalid compositional shares in survey {key}")
        if abs(float(shares.sum()) - 100.0) > 1e-5:
            raise RuntimeError(f"Survey {key} does not sum to 100% after preprocessing")

        n_raw = pd.to_numeric(g["n"], errors="coerce").dropna()
        moe_raw = pd.to_numeric(g["moe"], errors="coerce").dropna()
        n = float(n_raw.median()) if not n_raw.empty else np.nan
        moe = float(moe_raw.median()) if not moe_raw.empty else np.nan
        neff = _effective_n(n, moe, default_n, design_effect)
        p = regularize_composition(shares, neff, alpha=0.5)
        y = ilr_transform(p, basis)
        r = multinomial_ilr_covariance(p, neff, basis)

        first = g.iloc[0]
        measure_date = midpoint_date(g["field_start"], g["field_end"]).dropna()
        if measure_date.empty:
            continue
        measure = pd.Timestamp(measure_date.iloc[0]).normalize()
        rows.append({
            "_survey_key": str(key),
            "measure_date": measure,
            "field_start": pd.to_datetime(first.get("field_start"), errors="coerce"),
            "field_end": pd.to_datetime(first.get("field_end"), errors="coerce"),
            "publish_date": pd.to_datetime(first.get("publish_date"), errors="coerce"),
            "pollster_key": str(first.get("pollster_key", first.get("pollster", ""))),
            "pollster": str(first.get("pollster", "")),
            "n_eff": neff,
            "n_reported": n,
            "moe_reported": moe,
        })
        ys.append(y)
        covs.append(r)

    if not rows:
        raise RuntimeError("No complete surveys available for the joint compositional model")
    surveys = pd.DataFrame(rows)
    order = np.argsort(surveys["measure_date"].to_numpy(dtype="datetime64[ns]"), kind="stable")
    surveys = surveys.iloc[order].reset_index(drop=True)
    ymat = np.vstack([ys[i] for i in order])
    covs = [covs[i] for i in order]
    t0 = surveys["measure_date"].min()
    times = (surveys["measure_date"] - t0).dt.days.to_numpy(dtype=float)
    houses = surveys["pollster_key"].astype(str).to_numpy()
    return surveys, ymat, covs, times, candidates, basis


def _structured_scales(pair_scale: float, field_scale: float, d: int) -> np.ndarray:
    """Two-component scale: leading-pair balance and remaining field balances."""
    if d == 1:
        return np.array([float(pair_scale)], dtype=float)
    return np.r_[float(pair_scale), np.repeat(float(field_scale), d - 1)]


def _marginal_covariance(
    times: np.ndarray,
    houses: np.ndarray,
    sampling_covs: list[np.ndarray],
    q_rw: np.ndarray,
    sd_house: np.ndarray,
    sd_poll: np.ndarray,
) -> np.ndarray:
    n = len(times)
    d = sampling_covs[0].shape[0]
    Q = np.diag(np.asarray(q_rw, dtype=float) ** 2)
    H = np.diag(np.asarray(sd_house, dtype=float) ** 2)
    O = np.diag(np.asarray(sd_poll, dtype=float) ** 2)
    v = np.zeros((n * d, n * d), dtype=float)
    for i in range(n):
        for j in range(n):
            block = min(float(times[i]), float(times[j])) * Q
            if str(houses[i]) == str(houses[j]):
                block = block + H
            if i == j:
                block = block + sampling_covs[i] + O
            v[i*d:(i+1)*d, j*d:(j+1)*d] = block
    v = (v + v.T) / 2.0
    v.flat[:: v.shape[0] + 1] += 1e-9
    return v


def _profile_reml(
    log_scales: np.ndarray,
    yvec: np.ndarray,
    X: np.ndarray,
    times: np.ndarray,
    houses: np.ndarray,
    sampling_covs: list[np.ndarray],
    return_details: bool = False,
):
    d = sampling_covs[0].shape[0]
    raw = np.exp(np.asarray(log_scales, dtype=float))
    if len(raw) != 6:
        raise ValueError("v0.9 structured REML expects six variance-component scales")
    q_rw = _structured_scales(raw[0], raw[1], d)
    sd_house = _structured_scales(raw[2], raw[3], d)
    sd_poll = _structured_scales(raw[4], raw[5], d)
    try:
        V = _marginal_covariance(times, houses, sampling_covs, q_rw, sd_house, sd_poll)
        cf = cho_factor(V, lower=True, check_finite=False)
        Vinv_y = cho_solve(cf, yvec, check_finite=False)
        Vinv_X = cho_solve(cf, X, check_finite=False)
        B = X.T @ Vinv_X
        cb = cho_factor((B + B.T) / 2.0, lower=True, check_finite=False)
        beta = cho_solve(cb, X.T @ Vinv_y, check_finite=False)
        residual = yvec - X @ beta
        Vinv_r = cho_solve(cf, residual, check_finite=False)
        quad = float(residual @ Vinv_r)
        logdetV = 2.0 * float(np.log(np.diag(cf[0])).sum())
        logdetB = 2.0 * float(np.log(np.diag(cb[0])).sum())
        dof = max(len(yvec) - X.shape[1], 1)
        nll = 0.5 * (logdetV + logdetB + quad + dof * np.log(2.0 * np.pi))
        if not np.isfinite(nll):
            raise FloatingPointError
        if not return_details:
            return nll
        return nll, V, cf, Vinv_X, np.linalg.inv(B), beta, residual, q_rw, sd_house, sd_poll
    except (np.linalg.LinAlgError, FloatingPointError, ValueError):
        return (1e100 if not return_details else None)


def _fit_joint_gaussian(
    surveys: pd.DataFrame,
    y: np.ndarray,
    sampling_covs: list[np.ndarray],
    times: np.ndarray,
    candidates: list[str],
    basis: np.ndarray,
    config: dict,
) -> JointGaussianFit:
    n, d = y.shape
    yvec = y.reshape(-1)
    X = np.kron(np.ones((n, 1)), np.eye(d))

    default_start_scales = [
        [0.005, 0.030, 0.030, 0.100, 0.030, 0.100],
        [0.010, 0.060, 0.060, 0.200, 0.050, 0.150],
        [0.002, 0.100, 0.020, 0.300, 0.020, 0.200],
    ]
    warm = config.get("reml_start_scales")
    if warm is not None and len(warm) == 6 and np.all(np.asarray(warm, dtype=float) > 0):
        default_start_scales = [list(map(float, warm))] + default_start_scales
    n_starts = max(1, int(config.get("reml_multistart", 3)))
    starts = [np.log(x) for x in default_start_scales[:n_starts]]
    # Broad numerical bounds only.  All six substantive scales are estimated by REML.
    bounds = [(-9.0, 0.50)] * 6
    best = None
    for x0 in starts:
        res = minimize(
            _profile_reml,
            x0,
            args=(yvec, X, times, surveys["pollster_key"].astype(str).to_numpy(), sampling_covs, False),
            method="L-BFGS-B",
            bounds=bounds,
            options={"maxiter": int(config.get("reml_maxiter", 120)), "ftol": 1e-9},
        )
        if np.isfinite(res.fun) and (best is None or res.fun < best.fun):
            best = res
    if best is None:
        raise RuntimeError("REML hyperparameter optimization failed")

    details = _profile_reml(
        best.x, yvec, X, times, surveys["pollster_key"].astype(str).to_numpy(), sampling_covs, True
    )
    if details is None:
        raise RuntimeError("Could not reconstruct joint Gaussian fit")
    nll, V, cf, Vinv_X, B_inv, beta, residual, q_rw, sd_house, sd_poll = details
    return JointGaussianFit(
        candidates=candidates, basis=basis, surveys=surveys, y=y, sampling_covs=sampling_covs,
        times=times, houses=surveys["pollster_key"].astype(str).to_numpy(), beta=beta,
        q_rw=q_rw, sd_house=sd_house, sd_poll=sd_poll, reml_nll=float(nll), V=V,
        chol_V=cf, X=X, Vinv_X=Vinv_X, XtVinvX_inv=B_inv, residual=residual,
    )

def _theta_posterior(fit: JointGaussianFit, t: float) -> tuple[np.ndarray, np.ndarray]:
    n = len(fit.times)
    d = len(fit.beta)
    eye = np.eye(d)
    k0 = np.zeros((d, n * d), dtype=float)
    for i, ti in enumerate(fit.times):
        k0[:, i * d:(i + 1) * d] = min(float(t), float(ti)) * np.diag(fit.q_rw ** 2)
    Vinv_r = cho_solve(fit.chol_V, fit.residual, check_finite=False)
    mean = fit.beta + k0 @ Vinv_r
    Vinv_k = cho_solve(fit.chol_V, k0.T, check_finite=False)
    k00 = max(float(t), 0.0) * np.diag(fit.q_rw ** 2)
    base = k00 - k0 @ Vinv_k
    dmat = eye - k0 @ fit.Vinv_X
    cov = base + dmat @ fit.XtVinvX_inv @ dmat.T
    cov = (cov + cov.T) / 2.0
    vals, vecs = np.linalg.eigh(cov)
    vals = np.clip(vals, 1e-12, None)
    cov = (vecs * vals) @ vecs.T
    return mean, cov


def _house_posterior(fit: JointGaussianFit, pollster_key: str) -> tuple[np.ndarray, np.ndarray]:
    n = len(fit.times)
    d = len(fit.beta)
    eye = np.eye(d)
    k0 = np.zeros((d, n * d), dtype=float)
    for i, h in enumerate(fit.houses):
        if str(h) == str(pollster_key):
            k0[:, i * d:(i + 1) * d] = np.diag(fit.sd_house ** 2)
    Vinv_r = cho_solve(fit.chol_V, fit.residual, check_finite=False)
    mean = k0 @ Vinv_r
    Vinv_k = cho_solve(fit.chol_V, k0.T, check_finite=False)
    base = np.diag(fit.sd_house ** 2) - k0 @ Vinv_k
    dmat = -k0 @ fit.Vinv_X
    cov = base + dmat @ fit.XtVinvX_inv @ dmat.T
    cov = (cov + cov.T) / 2.0
    vals, vecs = np.linalg.eigh(cov)
    vals = np.clip(vals, 1e-12, None)
    cov = (vecs * vals) @ vecs.T
    return mean, cov


def _external_ilr_sd(p: np.ndarray, candidates: list[str], basis: np.ndarray, target_sd_pp: float) -> float:
    """Translate an external candidate-scale polling-error prior into isotropic ILR noise.

    The scale is chosen so the RMS marginal SD among named candidates (excluding the
    residual 'Outros candidatos' bucket) is approximately ``target_sd_pp``.
    """
    target = max(float(target_sd_pp), 0.0) / 100.0
    if target <= 0:
        return 0.0
    J = inverse_ilr_jacobian(p, basis)
    # The literature scale refers primarily to consequential candidate/election margins.
    # Match the requested marginal SD on the two leading candidates; the induced
    # covariance for the rest follows from the compositional geometry.
    named = [i for i, c in enumerate(candidates) if c != "Outros candidatos"]
    idx = named[:2] if len(named) >= 2 else (named or list(range(len(candidates))))
    rms = float(np.sqrt(np.mean(np.sum(J[idx, :] ** 2, axis=1))))
    return target / max(rms, 1e-9)


def _trajectory_from_fit(fit: JointGaussianFit, as_of_ts: pd.Timestamp, config: dict) -> pd.DataFrame:
    start = fit.surveys["measure_date"].min().normalize()
    end = max(as_of_ts.normalize(), fit.surveys["measure_date"].max().normalize())
    dates = pd.date_range(start, end, freq="D")
    levels = [float(x) for x in config.get("credible_intervals", [0.8, 0.95])]
    draws = int(config.get("posterior_draws", 4000))
    ext_pp = float(config.get("external_election_error_sd_pp", 0.0)) if bool(config.get("external_election_error_enabled", False)) else 0.0
    seed = int(config.get("posterior_seed", 418))
    rng = np.random.default_rng(seed)
    out = []

    for date in dates:
        t = float((date - start).days)
        mu, cov = _theta_posterior(fit, t)
        z = rng.multivariate_normal(mu, cov, size=draws, check_valid="ignore")
        shares = 100.0 * ilr_inverse_rows(z, fit.basis)
        point = 100.0 * ilr_inverse(mu, fit.basis)

        election_shares = None
        if ext_pp > 0:
            p0 = point / 100.0
            ext_sd = _external_ilr_sd(p0, fit.candidates, fit.basis, ext_pp)
            z_e = z + rng.normal(0.0, ext_sd, size=z.shape)
            election_shares = 100.0 * ilr_inverse_rows(z_e, fit.basis)

        for j, cand in enumerate(fit.candidates):
            vals = shares[:, j]
            row = {
                "date": date.date().isoformat(),
                "candidate": cand,
                "median_pct": float(np.median(vals)),
                "mean_pct": float(np.mean(vals)),
                "point_pct": float(point[j]),
                "rw_pair_sd_ilr_sqrt_day": float(fit.q_rw[0]),
                "rw_field_sd_ilr_sqrt_day": float(fit.q_rw[1] if len(fit.q_rw) > 1 else fit.q_rw[0]),
            }
            for level in levels:
                alpha = (1.0 - level) / 2.0
                tag = str(int(round(level * 100)))
                row[f"lower_{tag}_pct"] = float(np.quantile(vals, alpha))
                row[f"upper_{tag}_pct"] = float(np.quantile(vals, 1.0 - alpha))
                row[f"valid_lower_{tag}_pct"] = row[f"lower_{tag}_pct"]
                row[f"valid_upper_{tag}_pct"] = row[f"upper_{tag}_pct"]
                if election_shares is not None:
                    evals = election_shares[:, j]
                    row[f"election_lower_{tag}_pct"] = float(np.quantile(evals, alpha))
                    row[f"election_upper_{tag}_pct"] = float(np.quantile(evals, 1.0 - alpha))
            row["valid_median_pct"] = row["median_pct"]
            row["distance_to_50_pp"] = row["median_pct"] - 50.0
            row["external_election_error_sd_pp"] = ext_pp
            out.append(row)
    return pd.DataFrame(out)


def _house_effect_table(fit: JointGaussianFit, latest_theta: np.ndarray, config: dict) -> pd.DataFrame:
    base = 100.0 * ilr_inverse(latest_theta, fit.basis)
    rng = np.random.default_rng(int(config.get("posterior_seed", 418)) + 1)
    draws = min(int(config.get("posterior_draws", 4000)), 4000)
    rows = []
    poll_counts = fit.surveys.groupby("pollster_key")["_survey_key"].nunique().to_dict()
    labels = fit.surveys.groupby("pollster_key")["pollster"].agg(
        lambda x: x.mode().iloc[0] if not x.mode().empty else x.iloc[0]
    ).to_dict()
    for key in sorted(set(fit.houses)):
        mu, cov = _house_posterior(fit, str(key))
        z = rng.multivariate_normal(mu, cov, size=draws, check_valid="ignore")
        shifted = 100.0 * ilr_inverse_rows(z + latest_theta[None, :], fit.basis)
        effects = shifted - base[None, :]
        for j, cand in enumerate(fit.candidates):
            vals = effects[:, j]
            rows.append({
                "candidate": cand,
                "pollster_key": str(key),
                "pollster": labels.get(str(key), str(key)),
                "n_current_polls": int(poll_counts.get(str(key), 0)),
                "mean_house_effect_pp": float(np.median(vals)),
                "lower_80_house_effect_pp": float(np.quantile(vals, 0.10)),
                "upper_80_house_effect_pp": float(np.quantile(vals, 0.90)),
                "house_effect_ilr_norm": float(np.linalg.norm(mu)),
                "rw_pair_sd_ilr_sqrt_day": float(fit.q_rw[0]),
                "rw_field_sd_ilr_sqrt_day": float(fit.q_rw[1] if len(fit.q_rw) > 1 else fit.q_rw[0]),
                "house_pair_sd_ilr": float(fit.sd_house[0]),
                "house_field_sd_ilr": float(fit.sd_house[1] if len(fit.sd_house) > 1 else fit.sd_house[0]),
                "poll_pair_sd_ilr": float(fit.sd_poll[0]),
                "poll_field_sd_ilr": float(fit.sd_poll[1] if len(fit.sd_poll) > 1 else fit.sd_poll[0]),
                "reml_nll": fit.reml_nll,
            })
    return pd.DataFrame(rows)


def fit_nowcast(
    current: pd.DataFrame,
    quality: pd.DataFrame | None = None,
    bias: pd.DataFrame | None = None,
    config: dict | None = None,
    as_of: str | None = None,
):
    """Fit the v0.9 joint compositional Gaussian nowcast.

    ``quality`` and ``bias`` are accepted only for API compatibility with v0.8;
    they are deliberately ignored.  v0.9 estimates process, house and poll-noise
    scales by REML from the data used in each fit.
    """
    del quality, bias
    if config is None:
        raise ValueError("config is required")
    d = coerce_canonical(current)
    as_of_ts = pd.Timestamp(as_of).normalize() if as_of else pd.Timestamp.today().normalize()
    d = d[(d["election_year"] == int(config["current_year"])) & (d["round"] == int(config["current_round"]))]
    pattern = config.get("scenario_regex")
    if pattern:
        d = d[d["scenario"].astype(str).str.contains(pattern, regex=True, na=False)]
    d = d[d["publish_date"] <= as_of_ts].copy()
    if d.empty:
        raise RuntimeError("No prepared valid-vote polls matched the requested current slice")
    if "_survey_key" not in d.columns:
        d["_survey_key"] = survey_key(d)
    else:
        d["_survey_key"] = d["_survey_key"].astype(str)

    surveys, y, sampling_covs, times, candidates, basis = _survey_level_data(d, config)
    fit = _fit_joint_gaussian(surveys, y, sampling_covs, times, candidates, basis, config)
    trajectory = _trajectory_from_fit(fit, as_of_ts, config)
    if trajectory.empty:
        raise RuntimeError("Joint compositional fit produced no trajectory")

    latest = trajectory.sort_values("date").groupby("candidate", as_index=False, sort=False).tail(1).copy()
    n_polls = int(surveys["_survey_key"].nunique())
    last_poll_date = pd.to_datetime(surveys["field_end"], errors="coerce").max()
    latest["n_polls"] = n_polls
    latest["last_poll_date"] = last_poll_date.date().isoformat() if pd.notna(last_poll_date) else None

    start = surveys["measure_date"].min().normalize()
    latest_t = float((as_of_ts - start).days)
    theta_latest, _ = _theta_posterior(fit, latest_t)
    houses = _house_effect_table(fit, theta_latest, config)

    # Attach survey-level effective n to the exact rows used for auditability.
    neff_map = surveys.set_index("_survey_key")["n_eff"].to_dict()
    used = d.copy()
    used["model_n_eff"] = used["_survey_key"].map(neff_map)
    used["model_version"] = "0.9"

    latest = latest.sort_values("candidate").reset_index(drop=True)
    houses = houses.sort_values(["candidate", "pollster"]).reset_index(drop=True)
    return latest, trajectory, houses, used