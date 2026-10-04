from __future__ import annotations

import argparse
import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.linalg import cho_factor, cho_solve
from scipy.optimize import minimize
from scipy.stats import norm

BD_PODER360_URL = (
    "https://storage.googleapis.com/basedosdados-public/"
    "one-click-download/br_poder360_pesquisas/microdados/microdados.csv.gz"
)


def _norm_text(value: object) -> str:
    s = "" if value is None or (isinstance(value, float) and np.isnan(value)) else str(value)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^A-Za-z0-9]+", " ", s).strip().upper()
    return re.sub(r"\s+", " ", s)


def _split_aliases(value: object) -> set[str]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return set()
    return {_norm_text(x) for x in str(value).split("|") if _norm_text(x)}


def _effective_n(n: float, moe_pp: float, default_n: float = 1200.0, design_effect: float = 1.5) -> float:
    vals: list[float] = []
    if np.isfinite(n) and n > 20:
        vals.append(float(n) / max(float(design_effect), 1.0))
    if np.isfinite(moe_pp) and 0.2 < moe_pp < 20:
        m = float(moe_pp) / 100.0
        vals.append(1.96**2 * 0.25 / (m * m))
    return max(50.0, min(vals) if vals else float(default_n) / max(float(design_effect), 1.0))


def load_pollster_aliases(path: str | Path | None) -> dict[str, str]:
    if path is None:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    d = pd.read_csv(p)
    if not {"alias", "canonical"}.issubset(d.columns):
        return {}
    return {_norm_text(a): str(c) for a, c in zip(d["alias"], d["canonical"]) if _norm_text(a)}


def canonical_pollster(name: object, aliases: dict[str, str]) -> str:
    raw = "" if name is None else str(name).strip()
    return aliases.get(_norm_text(raw), raw)


def load_results(path: str | Path) -> pd.DataFrame:
    d = pd.read_csv(path)
    required = {
        "election_year", "election_date", "reference_candidate", "opponent_candidate",
        "reference_votes", "opponent_votes", "total_valid_votes",
        "reference_aliases", "opponent_aliases",
    }
    missing = required - set(d.columns)
    if missing:
        raise ValueError(f"Historical result file missing columns: {sorted(missing)}")
    d = d.copy()
    d["election_year"] = pd.to_numeric(d["election_year"], errors="raise").astype(int)
    d["election_date"] = pd.to_datetime(d["election_date"], errors="raise")
    for c in ["reference_votes", "opponent_votes", "total_valid_votes"]:
        d[c] = pd.to_numeric(d[c], errors="raise").astype(float)
    d["reference_share"] = d["reference_votes"] / d["total_valid_votes"]
    d["opponent_share"] = d["opponent_votes"] / d["total_valid_votes"]
    d["result_pair_ilr"] = np.log(d["reference_share"] / d["opponent_share"]) / np.sqrt(2.0)
    d["result_margin_pp"] = 100.0 * (d["reference_share"] - d["opponent_share"])
    return d


def load_poder360_history(path_or_url: str | Path | None = None) -> pd.DataFrame:
    source = BD_PODER360_URL if path_or_url is None else str(path_or_url)
    return pd.read_csv(source, compression="infer", low_memory=False)


def _poll_type_is_stimulated(s: pd.Series) -> pd.Series:
    return s.astype(str).map(_norm_text).str.contains("ESTIMUL", na=False)


def _national_mask(s: pd.Series) -> pd.Series:
    raw = s.astype("string")
    norm = raw.fillna("").map(_norm_text)
    return raw.isna() | norm.isin(["", "BR", "BRASIL"])


def _candidate_alias_match(name_norm: str, aliases: set[str]) -> bool:
    if name_norm in aliases:
        return True
    # Only allow a conservative token-contained fallback for aliases with >= 2 tokens.
    tokens = set(name_norm.split())
    for a in aliases:
        at = a.split()
        if len(at) >= 2 and set(at).issubset(tokens):
            return True
    return False


def prepare_historical_final_polls(
    raw: pd.DataFrame,
    results: pd.DataFrame,
    window_days: int = 7,
    pollster_aliases: dict[str, str] | None = None,
    default_n: float = 1200.0,
    design_effect: float = 1.5,
) -> pd.DataFrame:
    """Build one final national first-round poll per institute and election.

    The reference direction is fixed by ``results`` (for this project: PT candidate
    minus the principal rival). Poll percentages are converted to a valid-vote
    subcomposition by renormalizing candidate rows inside the selected scenario.
    """
    aliases = pollster_aliases or {}
    required = {
        "id_pesquisa", "ano", "sigla_uf", "cargo", "data", "instituto", "tipo",
        "turno", "tipo_voto", "id_cenario", "nome_candidato", "condicao", "percentual",
        "quantidade_entrevistas", "margem_mais",
    }
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"Poder360 historical file missing columns: {sorted(missing)}")

    d = raw.copy()
    d["ano"] = pd.to_numeric(d["ano"], errors="coerce")
    d["turno"] = pd.to_numeric(d["turno"], errors="coerce")
    d["condicao"] = pd.to_numeric(d["condicao"], errors="coerce")
    d["data"] = pd.to_datetime(d["data"], errors="coerce")
    years = set(results["election_year"].astype(int))
    d = d[
        d["ano"].isin(years)
        & d["cargo"].astype(str).map(_norm_text).eq("PRESIDENTE")
        & _national_mask(d["sigla_uf"])
        & d["turno"].eq(1)
        & _poll_type_is_stimulated(d["tipo"])
        & d["condicao"].eq(0)
        & d["data"].notna()
    ].copy()
    if d.empty:
        raise RuntimeError("No national stimulated first-round candidate rows found")

    d["percentual"] = pd.to_numeric(d["percentual"], errors="coerce")
    d["quantidade_entrevistas"] = pd.to_numeric(d["quantidade_entrevistas"], errors="coerce")
    d["margem_mais"] = pd.to_numeric(d["margem_mais"], errors="coerce")
    d["candidate_norm"] = d["nome_candidato"].map(_norm_text)
    d["pollster_canonical"] = d["instituto"].map(lambda x: canonical_pollster(x, aliases))

    result_by_year = {int(r.election_year): r for r in results.itertuples(index=False)}
    rows: list[dict] = []

    for (year, poll_id, scenario_id), g in d.groupby(["ano", "id_pesquisa", "id_cenario"], dropna=False, sort=False):
        year = int(year)
        rr = result_by_year.get(year)
        if rr is None:
            continue
        days_before = int((pd.Timestamp(rr.election_date).normalize() - g["data"].max().normalize()).days)
        if days_before < 0 or days_before > int(window_days):
            continue

        pct = g["percentual"].dropna().astype(float)
        if pct.empty:
            continue
        # Some mirrors may store proportions rather than percentages.
        scale = 100.0 if pct.max() <= 1.5 and pct.sum() <= 1.5 else 1.0
        gg = g.loc[pct.index].copy()
        gg["pct_work"] = pct * scale
        candidate_mass = float(gg["pct_work"].sum())
        if not (50.0 <= candidate_mass <= 105.0):
            continue

        ref_aliases = _split_aliases(rr.reference_aliases) | {_norm_text(rr.reference_candidate)}
        opp_aliases = _split_aliases(rr.opponent_aliases) | {_norm_text(rr.opponent_candidate)}
        ref_vals = gg.loc[gg["candidate_norm"].map(lambda x: _candidate_alias_match(x, ref_aliases)), "pct_work"]
        opp_vals = gg.loc[gg["candidate_norm"].map(lambda x: _candidate_alias_match(x, opp_aliases)), "pct_work"]
        if ref_vals.empty or opp_vals.empty:
            continue
        # Multiple matches usually indicate duplicate source rows; fail closed if materially inconsistent.
        if ref_vals.max() - ref_vals.min() > 0.25 or opp_vals.max() - opp_vals.min() > 0.25:
            continue
        ref_pct = float(ref_vals.median()) / candidate_mass
        opp_pct = float(opp_vals.median()) / candidate_mass
        if ref_pct <= 0 or opp_pct <= 0 or ref_pct >= 1 or opp_pct >= 1:
            continue

        nvals = gg["quantidade_entrevistas"].dropna()
        mvals = gg["margem_mais"].dropna()
        n = float(nvals.median()) if not nvals.empty else np.nan
        moe = float(mvals.median()) if not mvals.empty else np.nan
        neff = _effective_n(n, moe, default_n, design_effect)
        pair_ilr = math.log(ref_pct / opp_pct) / math.sqrt(2.0)
        # First Helmert-balance sampling variance under the multinomial delta method.
        sampling_var = 0.5 * (1.0 / ref_pct + 1.0 / opp_pct) / neff
        vote_type = " ".join(sorted({_norm_text(x) for x in gg["tipo_voto"].dropna().astype(str)}))
        valid_flag = int("VALID" in vote_type)
        rows.append({
            "election_year": year,
            "election_date": pd.Timestamp(rr.election_date).date().isoformat(),
            "poll_date": gg["data"].max().date().isoformat(),
            "days_before": days_before,
            "poll_id": str(poll_id),
            "scenario_id": str(scenario_id),
            "pollster": str(gg["pollster_canonical"].iloc[0]),
            "pollster_raw": str(gg["instituto"].iloc[0]),
            "vote_type": vote_type,
            "published_valid": bool(valid_flag),
            "candidate_mass_pct": candidate_mass,
            "n_reported": n,
            "moe_reported": moe,
            "n_eff": neff,
            "reference_candidate": str(rr.reference_candidate),
            "opponent_candidate": str(rr.opponent_candidate),
            "reference_poll_valid_pct": 100.0 * ref_pct,
            "opponent_poll_valid_pct": 100.0 * opp_pct,
            "poll_margin_pp": 100.0 * (ref_pct - opp_pct),
            "result_reference_share": float(rr.reference_share),
            "result_opponent_share": float(rr.opponent_share),
            "result_other_share": float(max(0.0, 1.0 - rr.reference_share - rr.opponent_share)),
            "result_margin_pp": float(rr.result_margin_pp),
            "margin_error_pp": 100.0 * (ref_pct - opp_pct) - float(rr.result_margin_pp),
            "pair_ilr_poll": pair_ilr,
            "pair_ilr_result": float(rr.result_pair_ilr),
            "pair_ilr_error": pair_ilr - float(rr.result_pair_ilr),
            "sampling_var_ilr": sampling_var,
            # deterministic scenario preference: published valid > mass closest to 100 > larger neff
            "_scenario_score_valid": valid_flag,
            "_scenario_score_mass": -abs(candidate_mass - 100.0),
            "_scenario_score_neff": neff,
        })

    if not rows:
        raise RuntimeError("No defensible historical poll scenarios after filtering")
    x = pd.DataFrame(rows)

    # One scenario per poll.
    x = x.sort_values(
        ["election_year", "poll_id", "_scenario_score_valid", "_scenario_score_mass", "_scenario_score_neff"],
        ascending=[True, True, False, False, False],
    ).drop_duplicates(["election_year", "poll_id"], keep="first")

    # One final poll per institute/election to avoid pseudo-replication from trackers.
    x["poll_date_ts"] = pd.to_datetime(x["poll_date"])
    x = x.sort_values(
        ["election_year", "pollster", "poll_date_ts", "published_valid", "n_eff"],
        ascending=[True, True, True, True, True],
    ).drop_duplicates(["election_year", "pollster"], keep="last")
    x = x.sort_values(["election_year", "pollster"]).reset_index(drop=True)
    return x.drop(columns=[c for c in x.columns if c.startswith("_scenario_")] + ["poll_date_ts"])


@dataclass
class HistoricalErrorFit:
    free_mean: bool
    mu: float
    mu_var: float
    election_sd: float
    house_sd: float
    poll_sd: float
    nll: float
    data: pd.DataFrame
    V: np.ndarray
    chol_V: tuple[np.ndarray, bool]
    residual: np.ndarray
    X: np.ndarray
    Vinv_X: np.ndarray | None
    XtVinvX_inv: np.ndarray | None


def _covariance(data: pd.DataFrame, election_sd: float, house_sd: float, poll_sd: float) -> np.ndarray:
    e = data["election_year"].astype(str).to_numpy()
    h = data["pollster"].astype(str).to_numpy()
    s = pd.to_numeric(data["sampling_var_ilr"], errors="raise").to_numpy(dtype=float)
    v = (e[:, None] == e[None, :]).astype(float) * election_sd**2
    v += (h[:, None] == h[None, :]).astype(float) * house_sd**2
    v[np.diag_indices_from(v)] += s + poll_sd**2 + 1e-10
    return (v + v.T) / 2.0


def _objective(log_scales: np.ndarray, data: pd.DataFrame, free_mean: bool, details: bool = False):
    scales = np.exp(np.asarray(log_scales, dtype=float))
    if len(scales) != 3:
        raise ValueError("Expected election, house and poll scales")
    y = pd.to_numeric(data["pair_ilr_error"], errors="raise").to_numpy(dtype=float)
    try:
        V = _covariance(data, *scales)
        cf = cho_factor(V, lower=True, check_finite=False)
        Vinv_y = cho_solve(cf, y, check_finite=False)
        logdetV = 2.0 * float(np.log(np.diag(cf[0])).sum())
        if free_mean:
            X = np.ones((len(y), 1), dtype=float)
            Vinv_X = cho_solve(cf, X, check_finite=False)
            B = X.T @ Vinv_X
            B_inv = np.linalg.inv(B)
            beta = B_inv @ (X.T @ Vinv_y)
            mu = float(beta[0])
            residual = y - mu
            quad = float(residual @ cho_solve(cf, residual, check_finite=False))
            logdetB = float(np.log(B[0, 0]))
            dof = max(len(y) - 1, 1)
            nll = 0.5 * (logdetV + logdetB + quad + dof * np.log(2.0 * np.pi))
        else:
            X = np.zeros((len(y), 0), dtype=float)
            Vinv_X = None
            B_inv = None
            mu = 0.0
            residual = y
            quad = float(y @ Vinv_y)
            nll = 0.5 * (logdetV + quad + len(y) * np.log(2.0 * np.pi))
        if not np.isfinite(nll):
            raise FloatingPointError
        if not details:
            return nll
        mu_var = float(B_inv[0, 0]) if free_mean else 0.0
        return nll, V, cf, residual, X, Vinv_X, B_inv, mu, mu_var, scales
    except (np.linalg.LinAlgError, FloatingPointError, ValueError):
        return None if details else 1e100


def fit_historical_error(data: pd.DataFrame, free_mean: bool = True, maxiter: int = 300) -> HistoricalErrorFit:
    if len(data) < 6 or data["election_year"].nunique() < 2:
        raise ValueError("Need multiple elections and at least six poll observations")
    starts = [
        [0.04, 0.03, 0.02],
        [0.08, 0.04, 0.04],
        [0.02, 0.08, 0.02],
        [0.12, 0.02, 0.06],
    ]
    best = None
    for st in starts:
        res = minimize(
            _objective,
            np.log(st),
            args=(data, free_mean, False),
            method="L-BFGS-B",
            bounds=[(-8.0, 0.0)] * 3,
            options={"maxiter": int(maxiter), "ftol": 1e-11},
        )
        if np.isfinite(res.fun) and (best is None or res.fun < best.fun):
            best = res
    if best is None:
        raise RuntimeError("Historical error variance-component optimization failed")
    det = _objective(best.x, data, free_mean, True)
    if det is None:
        raise RuntimeError("Could not reconstruct historical error fit")
    nll, V, cf, residual, X, Vinv_X, B_inv, mu, mu_var, scales = det
    return HistoricalErrorFit(
        free_mean=free_mean,
        mu=float(mu), mu_var=float(mu_var),
        election_sd=float(scales[0]), house_sd=float(scales[1]), poll_sd=float(scales[2]),
        nll=float(nll), data=data.reset_index(drop=True).copy(), V=V, chol_V=cf,
        residual=residual, X=X, Vinv_X=Vinv_X, XtVinvX_inv=B_inv,
    )


def _group_posterior(fit: HistoricalErrorFit, column: str, label: object, sd: float, include_fixed: bool) -> tuple[float, float]:
    n = len(fit.data)
    k = (fit.data[column].astype(str).to_numpy() == str(label)).astype(float) * sd**2
    Vinv_r = cho_solve(fit.chol_V, fit.residual, check_finite=False)
    mean = (fit.mu if include_fixed else 0.0) + float(k @ Vinv_r)
    Vinv_k = cho_solve(fit.chol_V, k, check_finite=False)
    var = sd**2 - float(k @ Vinv_k)
    if fit.free_mean and fit.Vinv_X is not None and fit.XtVinvX_inv is not None:
        x0 = 1.0 if include_fixed else 0.0
        d = x0 - float(k @ fit.Vinv_X[:, 0])
        var += d * d * float(fit.XtVinvX_inv[0, 0])
    return mean, max(var, 1e-12)


def election_effects(fit: HistoricalErrorFit) -> pd.DataFrame:
    rows = []
    for e in sorted(fit.data["election_year"].unique()):
        mean, var = _group_posterior(fit, "election_year", e, fit.election_sd, include_fixed=True)
        rows.append({
            "election_year": int(e),
            "posterior_common_error_ilr": mean,
            "posterior_common_error_ilr_sd": math.sqrt(var),
            "n_pollsters": int(fit.data.loc[fit.data["election_year"].eq(e), "pollster"].nunique()),
        })
    return pd.DataFrame(rows)


def house_effects(fit: HistoricalErrorFit) -> pd.DataFrame:
    rows = []
    for h in sorted(fit.data["pollster"].astype(str).unique()):
        mean, var = _group_posterior(fit, "pollster", h, fit.house_sd, include_fixed=False)
        rows.append({
            "pollster": h,
            "posterior_house_effect_ilr": mean,
            "posterior_house_effect_ilr_sd": math.sqrt(var),
            "n_elections": int(fit.data.loc[fit.data["pollster"].astype(str).eq(h), "election_year"].nunique()),
        })
    return pd.DataFrame(rows)


def predictive_new_election(fit: HistoricalErrorFit) -> tuple[float, float]:
    """Predict poll-minus-result common pair error for a new election."""
    var = fit.election_sd**2 + (fit.mu_var if fit.free_mean else 0.0)
    return fit.mu, math.sqrt(max(var, 1e-12))


def loo_validate(data: pd.DataFrame, free_mean: bool = True) -> pd.DataFrame:
    """Leave one whole election out.

    The held-out target is the inverse-variance mean poll error after subtracting
    house effects learned only from the other elections. Its measurement variance
    includes sampling noise, residual poll dispersion and uncertainty in the
    historical house effect.
    """
    rows = []
    for e in sorted(data["election_year"].unique()):
        train = data[data["election_year"].ne(e)].copy()
        test = data[data["election_year"].eq(e)].copy()
        fit = fit_historical_error(train, free_mean=free_mean)
        htab = house_effects(fit).set_index("pollster")
        adjusted = []
        variances = []
        for r in test.itertuples(index=False):
            h = str(r.pollster)
            if h in htab.index:
                hm = float(htab.loc[h, "posterior_house_effect_ilr"])
                hv = float(htab.loc[h, "posterior_house_effect_ilr_sd"]) ** 2
            else:
                hm = 0.0
                hv = fit.house_sd**2
            adjusted.append(float(r.pair_ilr_error) - hm)
            variances.append(float(r.sampling_var_ilr) + fit.poll_sd**2 + hv)
        adjusted = np.asarray(adjusted)
        variances = np.asarray(variances)
        w = 1.0 / np.maximum(variances, 1e-12)
        observed = float(np.sum(w * adjusted) / np.sum(w))
        observed_var = float(1.0 / np.sum(w))
        pred_mean, pred_sd_latent = predictive_new_election(fit)
        pred_var_obs = pred_sd_latent**2 + observed_var
        z = (observed - pred_mean) / math.sqrt(pred_var_obs)
        rows.append({
            "heldout_election": int(e),
            "n_pollsters": int(test["pollster"].nunique()),
            "observed_common_error_ilr": observed,
            "observed_se_ilr": math.sqrt(observed_var),
            "pred_mean_ilr": pred_mean,
            "pred_sd_latent_ilr": pred_sd_latent,
            "pred_sd_observed_ilr": math.sqrt(pred_var_obs),
            "z_score": z,
            "log_score": float(norm.logpdf(observed, loc=pred_mean, scale=math.sqrt(pred_var_obs))),
            "covered_80": bool(abs(z) <= norm.ppf(0.90)),
            "covered_95": bool(abs(z) <= norm.ppf(0.975)),
            "free_mean": bool(free_mean),
        })
    return pd.DataFrame(rows)


def jackknife_parameters(data: pd.DataFrame, free_mean: bool = True) -> pd.DataFrame:
    """Refit after deleting each entire election and report parameter stability."""
    rows = []
    for e in sorted(data["election_year"].unique()):
        train = data[data["election_year"].ne(e)].copy()
        fit = fit_historical_error(train, free_mean=free_mean)
        pred_mean, pred_sd = predictive_new_election(fit)
        rows.append({
            "omitted_election": int(e),
            "free_mean": bool(free_mean),
            "n_elections_train": int(train["election_year"].nunique()),
            "n_observations_train": int(len(train)),
            "mu_pair_error_ilr": fit.mu,
            "mu_pair_error_ilr_se": math.sqrt(max(fit.mu_var, 0.0)),
            "election_sd_ilr": fit.election_sd,
            "house_sd_ilr": fit.house_sd,
            "poll_sd_ilr": fit.poll_sd,
            "predictive_new_election_error_mean_ilr": pred_mean,
            "predictive_new_election_error_sd_ilr": pred_sd,
            "nll": fit.nll,
        })
    return pd.DataFrame(rows)


def summarize_fit(fit: HistoricalErrorFit, window_days: int) -> pd.DataFrame:
    pred_mean, pred_sd = predictive_new_election(fit)
    return pd.DataFrame([{
        "window_days": int(window_days),
        "free_mean": bool(fit.free_mean),
        "n_elections": int(fit.data["election_year"].nunique()),
        "n_pollsters": int(fit.data["pollster"].nunique()),
        "n_observations": int(len(fit.data)),
        "mu_pair_error_ilr": fit.mu,
        "mu_pair_error_ilr_se": math.sqrt(max(fit.mu_var, 0.0)),
        "election_sd_ilr": fit.election_sd,
        "house_sd_ilr": fit.house_sd,
        "poll_sd_ilr": fit.poll_sd,
        "predictive_new_election_error_mean_ilr": pred_mean,
        "predictive_new_election_error_sd_ilr": pred_sd,
        "nll": fit.nll,
    }])


def run_calibration(
    raw: pd.DataFrame,
    results: pd.DataFrame,
    aliases: dict[str, str],
    windows: list[int],
    output_dir: str | Path,
) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    all_summary = []
    all_loo = []
    all_jackknife = []
    for w in windows:
        p = prepare_historical_final_polls(raw, results, window_days=w, pollster_aliases=aliases)
        p.to_csv(out / f"historical_final_polls_w{w}.csv", index=False)
        for free_mean in [False, True]:
            fit = fit_historical_error(p, free_mean=free_mean)
            tag = "free_mean" if free_mean else "zero_mean"
            election_effects(fit).to_csv(out / f"historical_election_effects_w{w}_{tag}.csv", index=False)
            house_effects(fit).to_csv(out / f"historical_house_effects_w{w}_{tag}.csv", index=False)
            all_summary.append(summarize_fit(fit, w))
            loo = loo_validate(p, free_mean=free_mean)
            loo["window_days"] = w
            all_loo.append(loo)
            jk = jackknife_parameters(p, free_mean=free_mean)
            jk["window_days"] = w
            all_jackknife.append(jk)
    pd.concat(all_summary, ignore_index=True).to_csv(out / "historical_error_fit_summary.csv", index=False)
    pd.concat(all_jackknife, ignore_index=True).to_csv(out / "historical_error_jackknife.csv", index=False)
    loo = pd.concat(all_loo, ignore_index=True)
    loo.to_csv(out / "historical_error_loo.csv", index=False)
    metrics = (
        loo.groupby(["window_days", "free_mean"], as_index=False)
        .agg(
            mean_log_score=("log_score", "mean"),
            total_log_score=("log_score", "sum"),
            coverage_80=("covered_80", "mean"),
            coverage_95=("covered_95", "mean"),
            mean_abs_z=("z_score", lambda x: float(np.mean(np.abs(x)))),
        )
    )
    metrics.to_csv(out / "historical_error_loo_metrics.csv", index=False)


def main() -> None:
    ap = argparse.ArgumentParser(description="Brazil-specific common presidential polling-error calibration")
    ap.add_argument("--polls-file", default=None, help="Local Poder360/Base dos Dados CSV(.gz); omit to use public one-click URL")
    ap.add_argument("--results", default="data/presidential_first_round_results.csv")
    ap.add_argument("--pollster-aliases", default="data/pollster_aliases.csv")
    ap.add_argument("--windows", default="3,7,14")
    ap.add_argument("--output-dir", default="output_historical_error")
    args = ap.parse_args()
    results = load_results(args.results)
    aliases = load_pollster_aliases(args.pollster_aliases)
    raw = load_poder360_history(args.polls_file)
    windows = [int(x) for x in str(args.windows).split(",") if str(x).strip()]
    run_calibration(raw, results, aliases, windows, args.output_dir)


if __name__ == "__main__":
    main()