from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.special import expit, logit


def helmert_basis(k: int) -> np.ndarray:
    """Return a deterministic K x (K-1) orthonormal basis of the simplex tangent space.

    Columns sum to zero and H.T @ H = I.  Using an orthonormal ILR basis avoids
    privileging one candidate as the ALR reference category.
    """
    if k < 2:
        raise ValueError("A composition needs at least two parts")
    h = np.zeros((k, k - 1), dtype=float)
    for j in range(1, k):
        scale = np.sqrt(j * (j + 1.0))
        h[:j, j - 1] = 1.0 / scale
        h[j, j - 1] = -j / scale
    return h


def regularize_composition(shares: np.ndarray, n_eff: float, alpha: float = 0.5) -> np.ndarray:
    """Jeffreys half-count regularization of a reported composition.

    ``shares`` may contain exact zeros.  The correction vanishes as the effective
    sample size increases and therefore replaces a fixed percentage floor.
    """
    x = np.asarray(shares, dtype=float)
    if x.ndim != 1 or len(x) < 2:
        raise ValueError("shares must be a one-dimensional composition")
    if np.any(~np.isfinite(x)) or np.any(x < 0):
        raise ValueError("composition contains invalid shares")
    total = float(x.sum())
    if total <= 0:
        raise ValueError("composition has zero total mass")
    p = x / total
    n = max(float(n_eff), 1.0)
    counts = n * p
    out = (counts + float(alpha)) / (n + float(alpha) * len(x))
    return out / out.sum()


def ilr_transform(p: np.ndarray, basis: np.ndarray | None = None) -> np.ndarray:
    p = np.asarray(p, dtype=float)
    if p.ndim != 1 or len(p) < 2:
        raise ValueError("p must be a one-dimensional composition")
    if np.any(p <= 0) or not np.isfinite(p).all():
        raise ValueError("ILR requires strictly positive finite shares")
    p = p / p.sum()
    h = helmert_basis(len(p)) if basis is None else np.asarray(basis, dtype=float)
    return h.T @ np.log(p)


def ilr_inverse(y: np.ndarray, basis: np.ndarray) -> np.ndarray:
    y = np.asarray(y, dtype=float)
    h = np.asarray(basis, dtype=float)
    z = h @ y
    z = z - np.max(z, axis=0) if z.ndim > 1 else z - np.max(z)
    ez = np.exp(z)
    if ez.ndim == 1:
        return ez / ez.sum()
    return ez / ez.sum(axis=0, keepdims=True)


def ilr_inverse_rows(y: np.ndarray, basis: np.ndarray) -> np.ndarray:
    """Inverse ILR for an array of shape (draws, K-1)."""
    y = np.asarray(y, dtype=float)
    if y.ndim == 1:
        return ilr_inverse(y, basis)[None, :]
    z = y @ np.asarray(basis, dtype=float).T
    z = z - np.max(z, axis=1, keepdims=True)
    ez = np.exp(z)
    return ez / ez.sum(axis=1, keepdims=True)


def multinomial_ilr_covariance(p: np.ndarray, n_eff: float, basis: np.ndarray) -> np.ndarray:
    """Delta-method covariance of ILR coordinates for multinomial proportions.

    For y = H' log(p), H'1=0 implies
        Cov(y) ~= H' diag(1/p) H / n.
    """
    p = np.asarray(p, dtype=float)
    h = np.asarray(basis, dtype=float)
    n = max(float(n_eff), 1.0)
    cov = h.T @ np.diag(1.0 / np.clip(p, 1e-12, None)) @ h / n
    return (cov + cov.T) / 2.0


def inverse_ilr_jacobian(p: np.ndarray, basis: np.ndarray) -> np.ndarray:
    """Jacobian dp/dy for the inverse ILR map evaluated at composition p."""
    p = np.asarray(p, dtype=float)
    h = np.asarray(basis, dtype=float)
    return (np.diag(p) - np.outer(p, p)) @ h


# ---------------------------------------------------------------------------
# Legacy v0.8 compatibility helpers.
# They remain only so old review tests/scripts can be rerun; v0.9 does not use
# an after-the-fact simplex projection or an empirical candidate correlation.
# ---------------------------------------------------------------------------

def _nearest_correlation(a: np.ndarray, floor: float = 1e-4) -> np.ndarray:
    a = np.asarray(a, dtype=float)
    a = (a + a.T) / 2.0
    np.fill_diagonal(a, 1.0)
    vals, vecs = np.linalg.eigh(a)
    vals = np.clip(vals, floor, None)
    b = (vecs * vals) @ vecs.T
    d = np.sqrt(np.clip(np.diag(b), floor, None))
    b = b / np.outer(d, d)
    np.fill_diagonal(b, 1.0)
    return b


def estimate_candidate_correlation(used: pd.DataFrame, candidates: list[str], shrinkage: float = 0.5) -> pd.DataFrame:
    if used.empty or not candidates:
        return pd.DataFrame(np.eye(len(candidates)), index=candidates, columns=candidates)
    d = used[used["candidate"].isin(candidates)].copy()
    key = "_survey_key" if "_survey_key" in d.columns else None
    if key is None:
        raise ValueError("used data must contain _survey_key for compositional correlation")
    piv = d.pivot_table(index=key, columns="candidate", values="pct", aggfunc="first")
    piv = piv.reindex(columns=candidates).dropna()
    if len(piv) < 4:
        corr = np.eye(len(candidates))
    else:
        p = np.clip(piv.to_numpy(dtype=float) / 100.0, 1e-4, 1 - 1e-4)
        z = logit(p)
        z = z - np.nanmean(z, axis=0, keepdims=True)
        corr = np.corrcoef(z, rowvar=False)
        corr = np.nan_to_num(corr, nan=0.0, posinf=0.0, neginf=0.0)
        np.fill_diagonal(corr, 1.0)
    lam = float(np.clip(shrinkage, 0.0, 1.0))
    corr = (1.0 - lam) * corr + lam * np.eye(len(candidates))
    corr = _nearest_correlation(corr)
    return pd.DataFrame(corr, index=candidates, columns=candidates)


def project_trajectory_to_simplex(
    trajectory: pd.DataFrame,
    used: pd.DataFrame,
    config: dict,
    draws: int = 4000,
    seed: int = 418,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if trajectory.empty:
        return trajectory.copy(), pd.DataFrame()
    t = trajectory.copy()
    t["date"] = pd.to_datetime(t["date"])
    candidates = sorted(t["candidate"].dropna().unique())
    corr_df = estimate_candidate_correlation(
        used,
        candidates,
        shrinkage=float(config.get("candidate_correlation_shrinkage", 0.5)),
    )
    corr = corr_df.to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    out = []
    expected = set(candidates)
    for date, g in t.groupby("date", sort=True):
        names = list(g["candidate"])
        if set(names) != expected:
            continue
        g = g.set_index("candidate").reindex(candidates)
        p = np.clip(g["median_pct"].to_numpy(dtype=float) / 100.0, 1e-6, 1 - 1e-6)
        mu = logit(p)
        sd = np.maximum(g["sd_logit"].to_numpy(dtype=float), 1e-6)
        cov = np.outer(sd, sd) * corr
        cov = (cov + cov.T) / 2.0 + np.eye(len(candidates)) * 1e-10
        z = rng.multivariate_normal(mu, cov, size=int(draws), check_valid="ignore")
        raw = expit(z)
        shares = 100.0 * raw / np.maximum(raw.sum(axis=1, keepdims=True), 1e-12)
        for j, cand in enumerate(candidates):
            r = g.loc[cand].to_dict()
            vals = shares[:, j]
            r["date"] = date.date().isoformat()
            r["candidate"] = cand
            r["median_pct"] = float(np.median(vals))
            r["lower_80_pct"] = float(np.quantile(vals, 0.10))
            r["upper_80_pct"] = float(np.quantile(vals, 0.90))
            r["lower_95_pct"] = float(np.quantile(vals, 0.025))
            r["upper_95_pct"] = float(np.quantile(vals, 0.975))
            r["valid_median_pct"] = r["median_pct"]
            r["valid_lower_80_pct"] = r["lower_80_pct"]
            r["valid_upper_80_pct"] = r["upper_80_pct"]
            r["valid_lower_95_pct"] = r["lower_95_pct"]
            r["valid_upper_95_pct"] = r["upper_95_pct"]
            r["distance_to_50_pp"] = r["median_pct"] - 50.0
            out.append(r)
    return pd.DataFrame(out), corr_df