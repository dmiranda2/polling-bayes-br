"""Second-round presidential nowcast: historical bias only from *second-round* polls.

This intentionally does not refit the six-component first-round model on four
new observations. All reported shares are two-candidate valid-vote shares.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from historical_second_round import (
    _effective_n, _norm_text, _random_effect_posterior,
    fit_historical_model, jackknife, load_results, loo_by_election,
    pair_ilr, pair_ilr_sampling_var,
)

FIRST_ROUND_DATE = pd.Timestamp("2026-10-04")
CANDIDATES = {"Lula", "Flávio Bolsonaro"}
DEFAULT_EXTERNAL_SD_PP = 2.5


def read_current_polls(path: str | Path, as_of: str, include_mixed: bool = False) -> pd.DataFrame:
    """Reject incomplete, early, future, duplicated or non-national 2T records."""
    d = pd.read_csv(path)
    needed = {
        "election_year", "round", "poll_id", "pollster", "field_start", "field_end",
        "publish_date", "scenario", "candidate", "pct_valid", "n", "moe",
        "source_url", "vote_basis",
    }
    if needed - set(d.columns):
        raise ValueError(f"Missing columns in current polls: {sorted(needed - set(d.columns))}")
    asof = pd.Timestamp(as_of).normalize()
    for col in ["field_start", "field_end", "publish_date"]:
        d[col] = pd.to_datetime(d[col], errors="raise").dt.normalize()
    d = d[(d["election_year"] == 2026) & (d["round"] == 2)].copy()
    d = d[d["publish_date"].le(asof) & d["field_end"].le(asof)].copy()
    d = d[d["scenario"].astype(str).str.fullmatch("2º turno", na=False)].copy()
    if not include_mixed:
        d = d[d["field_start"] > FIRST_ROUND_DATE].copy()
    else:
        d = d[d["field_end"] > FIRST_ROUND_DATE].copy()

    if d.empty:
        raise ValueError("No national post-first-round polls with available field dates")
    if d.duplicated(["poll_id", "candidate"]).any():
        raise ValueError("Duplicate registration / candidate rows; audit before fitting")
    if d["field_start"].gt(d["field_end"]).any():
        raise ValueError("Impossible field start/end")
    rows = []
    for reg, g in d.groupby("poll_id", sort=True):
        if set(g["candidate"]) != CANDIDATES or len(g) != 2:
            raise ValueError(f"Incomplete or invalid two-candidate ballot: {reg}")
        g = g.set_index("candidate")
        meta = g.loc["Lula"]
        lula = float(g.loc["Lula", "pct_valid"])
        flavio = float(g.loc["Flávio Bolsonaro", "pct_valid"])
        if not (0 < lula < 100 and 0 < flavio < 100 and abs(lula + flavio - 100) < 0.12):
            raise ValueError(f"Invalid vote-valid pair in {reg}: {lula} + {flavio}")
        if g["pollster"].nunique() != 1 or g["field_start"].nunique() != 1:
            raise ValueError(f"Inconsistent metadata in {reg}")
        n = float(meta["n"])
        moe = float(meta["moe"])
        neff = _effective_n(n, moe)
        p_l, p_f = lula / (lula + flavio), flavio / (lula + flavio)
        mixed = pd.Timestamp(meta["field_start"]) <= FIRST_ROUND_DATE
        rows.append({
            "poll_id": reg, "pollster": str(meta["pollster"]),
            "field_start": meta["field_start"].date().isoformat(),
            "field_end": meta["field_end"].date().isoformat(),
            "publish_date": meta["publish_date"].date().isoformat(),
            "is_mixed_field": bool(mixed),
            "basis": str(meta["vote_basis"]),
            "source_url": str(meta["source_url"]),
            "lula_valid_pct": 100 * p_l, "flavio_valid_pct": 100 * p_f,
            "n_reported": n, "moe_pp": moe, "n_eff": neff,
            "z_poll_ilr": pair_ilr(p_l, p_f),
            "sampling_var_ilr": pair_ilr_sampling_var(p_l, p_f, neff),
        })
    surveys = pd.DataFrame(rows)
    # Repeated tracking surveys by the same company are not independent house effects.
    surveys = (surveys.sort_values(["pollster", "field_end", "publish_date", "poll_id"])
               .drop_duplicates("pollster", keep="last")
               .sort_values(["field_end", "pollster"]).reset_index(drop=True))
    return surveys


def _calibrate_historical(error_path: str | Path, results_path: str | Path) -> dict:
    """Gate directional historical bias on election-level validation, not poll LOO."""
    info: dict = {
        "status": "external_fallback", "directional_mean_used": False,
        "mu_ilr": 0.0, "var_mu_ilr": 0.0,
        "common_sd_ilr": DEFAULT_EXTERNAL_SD_PP / 100.0 * 2 * math.sqrt(2), "tau_h_ilr": 0.0, "tau_p_ilr": 0.0,
        "reasons": [], "fit": None,
    }
    if not Path(error_path).exists():
        info["reasons"].append("historical second-round calibration file absent")
        return info
    e = pd.read_csv(error_path)
    x = e[e["window_days"].eq(7)].copy()
    if x["election_year"].nunique() < 4 or len(x) < 12:
        info["reasons"].append("fewer than four elections or twelve historical institute observations")
        return info

    try:
        zero = fit_historical_model(x, free_mean=False)
        free = fit_historical_model(x, free_mean=True)
        results = load_results(results_path)
        loo0 = loo_by_election(x, results, free_mean=False)
        loof = loo_by_election(x, results, free_mean=True)
        jk = jackknife(x, free_mean=True)
    except (ValueError, RuntimeError, np.linalg.LinAlgError) as exc:
        info["reasons"].append("historical fit/LOO failed: " + str(exc))
        return info

    if loo0.empty or loof.empty:
        info["reasons"].append("historical hold-out scores unavailable")
        return info

    baseline_score = float(loo0["baseline_2p5_log_score"].sum())
    score0 = float(loo0["log_score"].sum())
    scoref = float(loof["log_score"].sum())
    info.update({
        "n_historical_polls": int(len(x)),
        "n_historical_elections": int(x["election_year"].nunique()),
        "loo_zero_logscore": score0, "loo_free_logscore": scoref,
        "loo_baseline_2p5_logscore": baseline_score,
        "jackknife_mu_min": float(jk["mu_ilr"].min()),
        "jackknife_mu_max": float(jk["mu_ilr"].max()),
        "free_mu_ilr": float(free.mu),
        "tau_e_zero_ilr": float(zero.tau_e),
        "tau_e_free_ilr": float(free.tau_e),
    })
    if score0 < baseline_score:
        # Keep independently estimable poll-level / institute heterogeneity, but
        # use the better-validated external common-election error prior.
        info["reasons"].append(
            "zero-mean historical common-error scale loses whole-election LOO "
            "to 2.5 pp external baseline; retaining second-round poll noise"
        )
        info.update({
            "status": "external_common_prior_historical_poll_noise",
            "tau_h_ilr": float(zero.tau_h),
            "tau_p_ilr": float(zero.tau_p),
            "fit": zero,
        })
        return info

    jack_sign_stable = bool(abs(free.mu) > 1e-9 and (jk["mu_ilr"] * free.mu > 0).all())
    window_sign_stable = True
    for window in (3, 14):
        ww = e[e["window_days"].eq(window)]
        if ww["election_year"].nunique() < 4 or len(ww) < 12:
            window_sign_stable = False
            info["reasons"].append(f"{window}-day historical window has insufficient coverage")
            continue
        fw = fit_historical_model(ww, free_mean=True)
        if fw.mu * free.mu <= 0:
            window_sign_stable = False
    accept_mean = bool(
        scoref > score0 and scoref >= baseline_score
        and jack_sign_stable and window_sign_stable
    )
    if not accept_mean:
        info["reasons"].append("directional mean rejected by whole-election LOO / jackknife / windows")
    fit = free if accept_mean else zero
    info.update({
        "status": "historical_second_round",
        "directional_mean_used": accept_mean,
        "mu_ilr": float(fit.mu) if accept_mean else 0.0,
        "var_mu_ilr": float(fit.var_mu) if accept_mean else 0.0,
        "common_sd_ilr": math.sqrt(fit.tau_e ** 2 + (fit.var_mu if accept_mean else 0)),
        "tau_h_ilr": float(fit.tau_h), "tau_p_ilr": float(fit.tau_p),
        "fit": fit,
    })
    return info


def _candidate_pct(z: np.ndarray | float) -> np.ndarray | float:
    """Lula's valid-vote percentage from the PT-minus-opponent ILR coordinate."""
    t = np.asarray(z, dtype=float) * math.sqrt(2)
    val = 100.0 / (1.0 + np.exp(-np.clip(t, -700.0, 700.0)))
    return float(val) if np.ndim(t) == 0 else val


def estimate(surveys: pd.DataFrame, calibration: dict, as_of: str,
             draws: int = 30000, seed: int = 418,
             fallback_sd_pp: float = DEFAULT_EXTERNAL_SD_PP) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Separate present polling consensus from a shared-error counterfactual.

    Distinct institute effects are adjusted only from historical second-round data.
    Their posterior uncertainty, sampling error, and poll noise are not conflated
    with the shock common to *all* companies in a new election.
    """
    fit = calibration.get("fit")
    source = calibration["status"]
    mu = float(calibration["mu_ilr"])
    common_sd = float(calibration["common_sd_ilr"])
    if not math.isfinite(common_sd):
        # For p near 1/2, z = log(p/(1-p))/sqrt(2); dp/dz = 1/(2sqrt(2)).
        common_sd = (float(fallback_sd_pp) / 100.0) * 2 * math.sqrt(2)
    x = surveys.copy()
    x["house_mean_ilr"] = 0.0
    x["house_sd_ilr"] = 0.0
    x["poll_noise_sd_ilr"] = float(calibration["tau_p_ilr"])
    hvars = []
    for idx, r in x.iterrows():
        if fit is None:
            h_mean, h_var = 0.0, 0.0
        else:
            h_mean, h_var = _random_effect_posterior(fit, "pollster", r["pollster"])
        x.loc[idx, "house_mean_ilr"] = h_mean
        x.loc[idx, "house_sd_ilr"] = math.sqrt(max(h_var, 0.0))
        hvars.append(h_var)
    x["adjusted_z_ilr"] = x["z_poll_ilr"] - x["house_mean_ilr"]
    x["obs_var_ilr"] = (x["sampling_var_ilr"] + float(calibration["tau_p_ilr"]) ** 2
                        + np.asarray(hvars, dtype=float))
    # Time weighting is intentionally absent: after the first round there are
    # only three independent strictly-post polls (four with mixed-field Atlas).
    w = 1 / x["obs_var_ilr"].to_numpy(float)
    mean_z = float(w @ x["adjusted_z_ilr"].to_numpy(float) / w.sum())
    sd_poll = float(math.sqrt(1 / w.sum()))
    rng = np.random.default_rng(int(seed))
    z_poll = rng.normal(mean_z, sd_poll, size=int(draws))
    z_hypothetical_election = z_poll - rng.normal(mu, common_sd, size=int(draws))
    p_poll = _candidate_pct(z_poll)
    p_election = _candidate_pct(z_hypothetical_election)
    def interval(values: np.ndarray) -> dict:
        return {
            "median": float(np.median(values)),
            "lo80": float(np.quantile(values, 0.1)), "hi80": float(np.quantile(values, 0.9)),
            "lo95": float(np.quantile(values, 0.025)), "hi95": float(np.quantile(values, 0.975)),
        }
    polling = interval(p_poll)
    possible = interval(p_election)
    row = {
        "as_of": as_of, "scenario": "mixed_atlas_included" if x["is_mixed_field"].any() else "strict_post_first_round",
        "n_surveys": int(len(x)), "last_field_end": str(x["field_end"].max()),
        "bias_calibration_status": source,
        "directional_mean_used": bool(calibration["directional_mean_used"]),
        "polling_lula_pct": polling["median"], "polling_flavio_pct": 100 - polling["median"],
        "polling_lula_lo80": polling["lo80"], "polling_lula_hi80": polling["hi80"],
        "polling_lula_lo95": polling["lo95"], "polling_lula_hi95": polling["hi95"],
        "counterfactual_lula_pct": possible["median"],
        "counterfactual_flavio_pct": 100 - possible["median"],
        "counterfactual_lula_lo80": possible["lo80"],
        "counterfactual_lula_hi80": possible["hi80"],
        "counterfactual_lula_lo95": possible["lo95"],
        "counterfactual_lula_hi95": possible["hi95"],
        "polling_latent_sd_ilr": sd_poll, "common_error_sd_ilr": common_sd,
        "historical_mu_poll_minus_urn_ilr": mu,
        "assumption": "If election occurred today; not a 25-Oct-2026 forecast",
    }
    return pd.DataFrame([row]), x


def main() -> None:
    p = argparse.ArgumentParser(description="Audited two-candidate second-round polling nowcast")
    p.add_argument("--polls", default="data/manual_second_round_2026.csv")
    p.add_argument("--history", default="output_second_round_bias/historical_poll_errors.csv")
    p.add_argument("--results", default="data/presidential_second_round_results.csv")
    p.add_argument("--as-of", default=None, help="YYYY-MM-DD; defaults to current date")
    p.add_argument("--out", default="output_second_round")
    p.add_argument("--draws", type=int, default=30000)
    a = p.parse_args()
    as_of = a.as_of or pd.Timestamp.today().date().isoformat()
    outdir = Path(a.out)
    outdir.mkdir(parents=True, exist_ok=True)
    calib = _calibrate_historical(a.history, a.results)
    outcomes, inputs = [], []
    for mixed in (False, True):
        polls = read_current_polls(a.polls, as_of, include_mixed=mixed)
        row, used = estimate(polls, calib, as_of, draws=a.draws, seed=418)
        outcomes.append(row)
        used["scenario"] = row["scenario"].iloc[0]
        inputs.append(used)
    result = pd.concat(outcomes, ignore_index=True)
    used = pd.concat(inputs, ignore_index=True)
    result.to_csv(outdir / f"nowcast_{as_of}.csv", index=False)
    used.to_csv(outdir / f"polls_used_{as_of}.csv", index=False)
    audit = {k: v for k, v in calib.items() if k != "fit"}
    audit["as_of"] = as_of
    audit["historical_data_origin"] = "SECOND-ROUND polls only (2002-2022)"
    (outdir / f"bias_audit_{as_of}.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    lines = [
        f"# Segundo turno — retrato de {as_of}", "",
        "Comparação Lula (PT) × Flávio Bolsonaro (PL), votos válidos.", "",
        f"Calibração: **{calib['status']}**. Média direcional histórica aplicada: **{calib['directional_mean_used']}**.", "",
        "O primeiro cenário **exclui Atlas**: seu campo começou antes do 1º turno.",
        "O segundo cenário inclui Atlas apenas como sensibilidade.", "",
        "| Cenário | N | Lula — pesquisas (%) | Flávio — pesquisas (%) | Lula — correção de erro comum (80%) |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in result.itertuples(index=False):
        lines.append(f"| {r.scenario} | {r.n_surveys} | {r.polling_lula_pct:.2f} | {r.polling_flavio_pct:.2f} | {r.counterfactual_lula_pct:.2f} [{r.counterfactual_lula_lo80:.2f}, {r.counterfactual_lula_hi80:.2f}] |")
    lines.extend([
        "", "A camada de erro comum não deve ser confundida com erro amostral das pesquisas.",
        "**Não é previsão do resultado em 25/10/2026**; representa o retrato de hoje e o cenário hipotético de votação hoje.",
        "", "## Diagnósticos", "",
        f"- LOO histórico: {calib.get('n_historical_elections', 0)} eleições; {calib.get('n_historical_polls', 0)} levantamentos por instituto.",
        f"- Motivos de fallback/rejeição: {', '.join(calib['reasons']) or 'nenhum'}.",
        f"- Fontes por registro disponíveis em `polls_used_{as_of}.csv`.",
    ])
    (outdir / f"report_{as_of}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(result.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    print(json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
