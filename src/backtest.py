from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from common import survey_key
from model import fit_nowcast
from preprocess import HISTORICAL_BALLOTS, normalize_historical_candidate, prepare_historical_valid_shares


ELECTIONS = {
    2018: {
        "date": "2018-10-07",
        "results": {
            "Jair Bolsonaro": 46.03,
            "Fernando Haddad": 29.28,
            "Ciro Gomes": 12.47,
            "Geraldo Alckmin": 4.76,
            "João Amoêdo": 2.50,
            "Cabo Daciolo": 1.26,
            "Henrique Meirelles": 1.20,
            "Marina Silva": 1.00,
            "Álvaro Dias": 0.80,
            "Guilherme Boulos": 0.58,
            "Vera Lúcia": 0.05,
            "Eymael": 0.04,
            "João Goulart Filho": 0.03,
        },
    },
    2022: {
        "date": "2022-10-02",
        "results": {
            "Lula": 48.43,
            "Jair Bolsonaro": 43.20,
            "Simone Tebet": 4.16,
            "Ciro Gomes": 3.04,
            "Soraya Thronicke": 0.51,
            "Felipe d'Avila": 0.47,
            "Padre Kelmon": 0.07,
            "Léo Péricles": 0.05,
            "Sofia Manzano": 0.04,
            "Vera Lúcia": 0.02,
            "Constituinte Eymael": 0.01,
        },
    },
}

BACKTEST_SOURCE_NOTE = {
    2018: "cédula final; cenários históricos selecionados por identidade e convertidos para votos válidos",
    2022: "4 candidatos individualizados pela fonte Nexo; resultado oficial renormalizado nesses 4",
}


def result_name(s: object, year: int | None = None) -> str:
    return normalize_historical_candidate(s, int(year or 2022))


def valid_vote_posterior(latest: pd.DataFrame, *_, **__) -> pd.DataFrame:
    """Compatibility shim: the model already lives on valid-vote compositions."""
    x = latest.copy()
    if x.empty:
        return x
    x["valid_median_pct"] = x["median_pct"]
    for tag in ["80", "95"]:
        if f"lower_{tag}_pct" in x:
            x[f"valid_lower_{tag}_pct"] = x[f"lower_{tag}_pct"]
            x[f"valid_upper_{tag}_pct"] = x[f"upper_{tag}_pct"]
    x["distance_to_50_pp"] = x["median_pct"] - 50.0
    return x


def _comparison_truth(year: int) -> dict[str, float]:
    official = ELECTIONS[year]["results"]
    if year != 2022:
        return dict(official)
    observed = HISTORICAL_BALLOTS[2022]
    denom = sum(official[c] for c in observed)
    return {c: 100.0 * official[c] / denom for c in observed}


def _availability_date(hist: pd.DataFrame, year: int, config: dict) -> pd.Series:
    pub = pd.to_datetime(hist["publish_date"], errors="coerce")
    if year == 2018:
        lag = int(config.get("historical_2018_publication_lag_days", 3))
        return pub + pd.to_timedelta(lag, unit="D")
    return pub


def _simple_mean_baseline(hist: pd.DataFrame) -> dict[str, float]:
    """Deliberately simple comparator: equal weight per complete survey composition."""
    x = hist.copy()
    if "_survey_key" not in x.columns:
        x["_survey_key"] = survey_key(x)
    piv = x.pivot_table(index="_survey_key", columns="candidate", values="pct", aggfunc="first")
    return piv.mean(axis=0).to_dict()


def run_backtest(master: pd.DataFrame, config: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    cuts = [int(x) for x in config.get("backtest_days_before", [30, 21, 14, 7, 3, 1])]
    history_window = int(config.get("backtest_history_window_days", config.get("history_window_days", 120)))
    all_rows = []

    for year in [2018, 2022]:
        election_date = pd.Timestamp(ELECTIONS[year]["date"])
        hist_all, _ = prepare_historical_valid_shares(master, config, [year])
        if hist_all.empty:
            continue
        hist_all["_available_date"] = _availability_date(hist_all, year, config)
        comparison = _comparison_truth(year)
        warm_scales = None

        for days_before in cuts:
            cutoff = election_date - pd.Timedelta(days=days_before)
            start = election_date - pd.Timedelta(days=history_window)
            hist = hist_all[
                (hist_all["_available_date"] <= cutoff)
                & (pd.to_datetime(hist_all["field_end"], errors="coerce") >= start)
            ].copy()
            if hist.empty:
                continue

            cfg = dict(config)
            cfg.update({
                "current_year": year,
                "current_round": 1,
                "scenario_regex": None,
                "current_use_final_ballot_only": False,
                # Backtests run sequentially from the earliest cutoff.  A one-start
                # REML fit is warm-started from the preceding (strictly earlier) cutoff.
                "reml_multistart": 1,
                "reml_maxiter": min(int(config.get("reml_maxiter", 120)), 45),
                "posterior_draws": min(int(config.get("posterior_draws", 4000)), 1200),
            })
            if warm_scales is not None:
                cfg["reml_start_scales"] = warm_scales
            try:
                latest, _, houses_fit, _ = fit_nowcast(hist, None, None, cfg, cutoff.date().isoformat())
                if not houses_fit.empty:
                    hr = houses_fit.iloc[0]
                    warm_scales = [
                        float(hr["rw_pair_sd_ilr_sqrt_day"]), float(hr["rw_field_sd_ilr_sqrt_day"]),
                        float(hr["house_pair_sd_ilr"]), float(hr["house_field_sd_ilr"]),
                        float(hr["poll_pair_sd_ilr"]), float(hr["poll_field_sd_ilr"]),
                    ]
            except RuntimeError:
                continue

            baseline = _simple_mean_baseline(hist)
            vv = valid_vote_posterior(latest)
            vv["candidate"] = vv["candidate"].map(lambda x: result_name(x, year))
            vv["official_valid_pct"] = vv["candidate"].map(ELECTIONS[year]["results"])
            vv["official_comparison_pct"] = vv["candidate"].map(comparison)
            vv = vv[vv["official_comparison_pct"].notna()].copy()
            vv["baseline_pct"] = vv["candidate"].map({result_name(k, year): v for k, v in baseline.items()})
            vv["error_pp"] = vv["median_pct"] - vv["official_comparison_pct"]
            vv["abs_error_pp"] = vv["error_pp"].abs()
            vv["baseline_error_pp"] = vv["baseline_pct"] - vv["official_comparison_pct"]
            vv["baseline_abs_error_pp"] = vv["baseline_error_pp"].abs()
            vv["covered_80_nowcast"] = (
                (vv["official_comparison_pct"] >= vv["lower_80_pct"])
                & (vv["official_comparison_pct"] <= vv["upper_80_pct"])
            )
            if {"election_lower_80_pct", "election_upper_80_pct"}.issubset(vv.columns):
                vv["covered_80_election_prior"] = (
                    (vv["official_comparison_pct"] >= vv["election_lower_80_pct"])
                    & (vv["official_comparison_pct"] <= vv["election_upper_80_pct"])
                )
            else:
                vv["covered_80_election_prior"] = np.nan
            vv["election_year"] = year
            vv["days_before"] = days_before
            vv["cutoff_date"] = cutoff.date().isoformat()
            vv["comparison_basis"] = "official valid" if year == 2018 else "official valid renormalized to Nexo top 4"
            all_rows.append(vv)

    if not all_rows:
        return pd.DataFrame(), pd.DataFrame()
    detail = pd.concat(all_rows, ignore_index=True)

    official_rank = {
        (year, cand): rank
        for year, meta in ELECTIONS.items()
        for rank, (cand, _) in enumerate(sorted(meta["results"].items(), key=lambda kv: kv[1], reverse=True), start=1)
    }
    detail["official_rank"] = [official_rank.get((int(y), c), 999) for y, c in zip(detail["election_year"], detail["candidate"])]
    public_detail = detail[detail["official_rank"] <= 5].copy()

    metrics = (
        public_detail.groupby(["election_year", "days_before", "cutoff_date"], as_index=False)
        .agg(
            mae_pp=("abs_error_pp", "mean"),
            rmse_pp=("error_pp", lambda x: float(np.sqrt(np.mean(np.square(x))))),
            baseline_mae_pp=("baseline_abs_error_pp", "mean"),
            baseline_rmse_pp=("baseline_error_pp", lambda x: float(np.sqrt(np.mean(np.square(x))))),
            coverage_80_nowcast=("covered_80_nowcast", "mean"),
            coverage_80_election_prior=("covered_80_election_prior", "mean"),
            n_candidates=("candidate", "nunique"),
        )
        .sort_values(["election_year", "days_before"], ascending=[True, False])
    )
    metrics["coverage_80"] = metrics["coverage_80_nowcast"]
    metrics["source_coverage"] = metrics["election_year"].map(BACKTEST_SOURCE_NOTE)
    metrics["electoral_interval_note"] = (
        "external prior only; its scale is not estimated from the 2018/2022 backtest"
    )

    external = pd.DataFrame([{
        "status": "external_prior" if bool(config.get("external_election_error_enabled", False)) else "disabled",
        "candidate_sd_pp": float(config.get("external_election_error_sd_pp", 0.0)),
        "basis": config.get("external_election_error_basis", ""),
        "usage": "reported separately from the latent polling-nowcast interval; never fitted to 2018/2022",
    }])
    metrics.attrs["external_error_prior"] = external
    # Legacy key retained so older callers do not break.
    metrics.attrs["horizon_calibration"] = external
    return public_detail.sort_values(["election_year", "days_before", "official_rank"]), metrics


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/polls_master.csv")
    p.add_argument("--config", default="config.json")
    p.add_argument("--out", default="output")
    args = p.parse_args()
    cfg = json.load(open(args.config, encoding="utf-8"))
    df = pd.read_csv(args.data)
    detail, metrics = run_backtest(df, cfg)
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    external = metrics.attrs.get("external_error_prior", pd.DataFrame())
    detail.to_csv(out / "backtest_temporal.csv", index=False)
    metrics.to_csv(out / "backtest_metrics.csv", index=False)
    external.to_csv(out / "external_error_prior.csv", index=False)
    print(metrics.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    print("\nExternal election-error prior:")
    print(external.to_string(index=False))


if __name__ == "__main__":
    main()