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

from historical_calibration import parse_window_range, window_label
from runoff_calendar import audit_calendar
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


def _calibrate_historical(error_path: str | Path, results_path: str | Path,
                          window_range: str = "1:7") -> dict:
    """Gate directional historical bias on election-level validation, not poll LOO."""
    near, far = parse_window_range(window_range)
    selected_window = window_label((near, far))
    info: dict = {
        "historical_round": 2,
        "historical_window_range": selected_window,
        "status": "external_fallback", "directional_mean_used": False,
        "mu_ilr": 0.0, "var_mu_ilr": 0.0,
        "common_sd_ilr": DEFAULT_EXTERNAL_SD_PP / 100.0 * 2 * math.sqrt(2), "tau_h_ilr": 0.0, "tau_p_ilr": 0.0,
        "reasons": [], "fit": None,
    }
    if not Path(error_path).exists():
        info["reasons"].append("historical second-round calibration file absent")
        return info
    e = pd.read_csv(error_path)
    required = {"election_round", "window_min_days", "window_days", "election_year"}
    missing = required - set(e.columns)
    if missing:
        info["reasons"].append("unauditable history; missing " + ", ".join(sorted(missing)))
        return info
    if not e["election_round"].eq(2).all():
        info["reasons"].append("historical file contains first-round or mixed-round polls")
        return info
    x = e[e["window_days"].eq(far) & e["window_min_days"].eq(near)].copy()
    if x["election_year"].nunique() < 4 or len(x) < 12:
        info["reasons"].append(
            "insufficient history for window " + selected_window +
            " (requires four elections and twelve independent polls)"
        )
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
    # Require consistency with two different periods, not just one cherry-picked slice.
    comparators = [(1, 3), (1, 14)] if (near, far) == (1, 7) else [(1, 7), (1, 14)]
    for other_near, other_far in comparators:
        if (other_near, other_far) == (near, far):
            continue
        ww = e[e["window_days"].eq(other_far) & e["window_min_days"].eq(other_near)]
        other = window_label((other_near, other_far))
        if ww["election_year"].nunique() < 4 or len(ww) < 12:
            window_sign_stable = False
            info["reasons"].append(f"comparison window {other} has insufficient historical coverage")
            continue
        fw = fit_historical_model(ww, free_mean=True)
        if fw.mu * free.mu <= 0:
            window_sign_stable = False
            info["reasons"].append(f"bias direction differs between {selected_window} and {other}")
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
             fallback_sd_pp: float = DEFAULT_EXTERNAL_SD_PP,
             bias_mode: str = 'second_round_history') -> tuple[pd.DataFrame, pd.DataFrame]:
    """Separate present polling consensus from a shared-error counterfactual.

    Distinct institute effects are adjusted only from historical second-round data.
    Their posterior uncertainty, sampling error, and poll noise are not conflated
    with the shock common to *all* companies in a new election.
    """
    if bias_mode not in {"none", "second_round_history"}:
        raise ValueError(f"Invalid second-round correction mode: {bias_mode}")
    if calibration.get("historical_round", 2) != 2:
        raise ValueError("Cannot apply first-round history to a second-round nowcast")
    fit = calibration.get("fit")
    source = calibration["status"]
    apply_house = bias_mode == "second_round_history"
    mu = float(calibration["mu_ilr"]) if apply_house and calibration.get("directional_mean_used", False) else 0.0
    common_sd = float(calibration["common_sd_ilr"])
    if not math.isfinite(common_sd):
        # For p near 1/2, z = log(p/(1-p))/sqrt(2); dp/dz = 1/(2sqrt(2)).
        common_sd = (float(fallback_sd_pp) / 100.0) * 2 * math.sqrt(2)
    x = surveys.copy()
    x["house_mean_ilr"] = 0.0
    x["house_mean_applied_ilr"] = 0.0
    x["historical_second_round_house_match"] = False
    x["house_sd_ilr"] = 0.0
    x["poll_noise_sd_ilr"] = float(calibration["tau_p_ilr"])
    hvars = []
    for idx, r in x.iterrows():
        if fit is None:
            h_mean, h_var = 0.0, 0.0
        else:
            h_mean, h_var = _random_effect_posterior(fit, "pollster", r["pollster"])
        x.loc[idx, "house_mean_ilr"] = h_mean
        x.loc[idx, "house_mean_applied_ilr"] = h_mean if apply_house else 0.0
        x.loc[idx, "historical_second_round_house_match"] = bool(fit is not None and (_norm_text(r["pollster"]) == fit.pollsters).any())
        x.loc[idx, "house_sd_ilr"] = math.sqrt(max(h_var, 0.0))
        hvars.append(h_var)
    x["adjusted_z_ilr"] = x["z_poll_ilr"] - x["house_mean_applied_ilr"]
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
    house_mask = x["historical_second_round_house_match"].to_numpy(bool)
    coverage = 100.0 * float(w @ house_mask.astype(float) / w.sum())
    row = {
        "bias_mode": bias_mode,
        "bias_source": "second_round_history_only" if apply_house else "none",
        "n_house_effects_matched": int(house_mask.sum()),
        "n_house_effects_applied": int(house_mask.sum()) if apply_house else 0,
        "house_weight_covered_pct": coverage,
        "mean_house_shift_applied_ilr": float(w @ x["house_mean_applied_ilr"].to_numpy(float) / w.sum()),
        "mean_common_shift_applied_ilr": mu,
        "as_of": as_of, "scenario": "mixed_atlas_included" if x["is_mixed_field"].any() else "strict_post_first_round",
        "n_surveys": int(len(x)), "last_field_end": str(x["field_end"].max()),
        "bias_calibration_status": source,
        "directional_mean_used": bool(apply_house and calibration["directional_mean_used"]),
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
    x["bias_mode"] = bias_mode
    return pd.DataFrame([row]), x


def _format_result_table(result: pd.DataFrame) -> list[str]:
    lines = [
        "| Cenário | N | Lula consenso (%) | Flávio consenso (%) | Lula, urna hipotética hoje [IC80%] | Institutos ajustados (2T) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in result.itertuples(index=False):
        lines.append(
            f"| {r.scenario} | {r.n_surveys} | {r.polling_lula_pct:.2f} | "
            f"{r.polling_flavio_pct:.2f} | {r.counterfactual_lula_pct:.2f} "
            f"[{r.counterfactual_lula_lo80:.2f}, {r.counterfactual_lula_hi80:.2f}] | "
            f"{r.n_house_effects_applied} |"
        )
    return lines


def _separate_report(part: pd.DataFrame, mode: str, calib: dict,
                     as_of: str, used: pd.DataFrame, calendar: pd.DataFrame) -> str:
    corrected = mode == "second_round_history"
    lines = [
        f"# Segundo turno — {'com correção histórica 2T' if corrected else 'sem correção'} — {as_of}",
        "",
        "Nowcast Lula × Flávio Bolsonaro (votos válidos). Não é previsão de 25/10.",
        "Histórico do viés: SOMENTE pesquisas e urnas de segundo turno.",
        f"Status: {calib['status']}; janela histórica {calib['historical_window_range']}.",
        f"Média direcional comum aplicada: {corrected and calib['directional_mean_used']}.",
        "",
    ]
    lines += _format_result_table(part)
    lines += [
        "", "As duas versões usam as MESMAS pesquisas e as MESMAS variâncias; "
        "somente a estimativa de efeito histórico de instituto (e a média comum "
        "se passar pelo LOO) pode mudar o centro.", "",
    ]
    for r in part.itertuples(index=False):
        g = used[(used["scenario"] == r.scenario) & (used["bias_mode"] == mode)]
        unknown = sorted(g.loc[~g["historical_second_round_house_match"], "pollster"].unique().tolist())
        lines.append(
            f"- {r.scenario}: {r.n_house_effects_matched}/{r.n_surveys} institutos identificáveis "
            f"no histórico de 2T; peso {r.house_weight_covered_pct:.1f}%; "
            f"sem histórico: {', '.join(unknown) if unknown else 'nenhum'}."
        )
    lines += [
        "", "O erro comum histórico só ajusta direção quando validado por eleição inteira.",
        "Os ajustes de instituto são estimativas regularizadas; estabilidade não é garantida.",
        f"Calendário: {len(calendar)} registros programados, "
        f"{int(calendar['date_conflict'].sum())} conflitos de datas.",
        "Nenhum registro agendado ou dado de primeiro turno entra no nowcast.",
        "Atlas, cuja coleta iniciou antes de 04/10, entra apenas na sensibilidade.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser(description="Second-round-only corrected and uncorrected nowcasts")
    p.add_argument("--polls", default="data/manual_second_round_2026.csv")
    p.add_argument("--history", default="output_second_round_bias/historical_poll_errors.csv")
    p.add_argument("--results", default="data/presidential_second_round_results.csv")
    p.add_argument("--historical-window", default="1:7")
    p.add_argument("--as-of", default=None)
    p.add_argument("--out", default="output_second_round")
    p.add_argument("--draws", type=int, default=30000)
    p.add_argument("--calendar", default="data/scheduled_polls_2026_10_10.csv")
    p.add_argument("--bias-modes", choices=["both", "none", "second_round_history"], default="both")
    a = p.parse_args()
    as_of = a.as_of or pd.Timestamp.today().date().isoformat()
    outdir = Path(a.out)
    outdir.mkdir(parents=True, exist_ok=True)
    calib = _calibrate_historical(a.history, a.results, a.historical_window)
    calendar = audit_calendar(a.calendar)
    calendar.to_csv(outdir / f"calendar_audit_{as_of}.csv", index=False)
    modes = ["none", "second_round_history"] if a.bias_modes == "both" else [a.bias_modes]
    outcomes, inputs = [], []
    for mixed in (False, True):
        surveys = read_current_polls(a.polls, as_of, include_mixed=mixed)
        for mode in modes:
            row, used = estimate(surveys, calib, as_of, draws=a.draws, seed=418,
                                 bias_mode=mode)
            outcomes.append(row)
            used["scenario"] = row["scenario"].iloc[0]
            inputs.append(used)
    result = pd.concat(outcomes, ignore_index=True)
    used = pd.concat(inputs, ignore_index=True)
    result.to_csv(outdir / f"nowcast_{as_of}.csv", index=False)
    used.to_csv(outdir / f"polls_used_{as_of}.csv", index=False)
    for mode in modes:
        label = "uncorrected" if mode == "none" else "second_round_corrected"
        part = result[result["bias_mode"] == mode]
        part.to_csv(outdir / f"nowcast_{label}_{as_of}.csv", index=False)
        (outdir / f"report_{label}_{as_of}.md").write_text(
            _separate_report(part, mode, calib, as_of, used, calendar), encoding="utf-8"
        )
    audit = {k: v for k, v in calib.items() if k != "fit"}
    audit["as_of"] = as_of
    audit["bias_modes"] = modes
    audit["historical_data_origin"] = "SECOND ROUND ONLY"
    audit["first_round_bias_transfer"] = "DISABLED"
    audit["calendar_date_conflicts"] = calendar.loc[calendar["date_conflict"], "poll_id"].tolist()
    (outdir / f"bias_audit_{as_of}.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    lines = [
        f"# Segundo turno — duas versões — {as_of}", "",
        "Somente pesquisas de segundo turno; nenhuma correção de primeiro turno.",
        "Sem correção mantém o consenso publicado; com correção usa exclusivamente "
        "os efeitos aprendidos de segundos turnos históricos.", "",
    ]
    for mode in modes:
        lines += ["## " + ("Sem correção" if mode == "none" else "Com histórico 2T"), ""]
        lines += _format_result_table(result[result["bias_mode"] == mode])
        lines += [""]
    lines += [
        f"Média histórica comum direcional validada: {calib['directional_mean_used']}.",
        "Atlas aparece apenas como sensibilidade por campo misto.",
        "**Não é previsão do resultado de 25/10/2026.**", "",
    ]
    (outdir / f"report_{as_of}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(result.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    print(json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
