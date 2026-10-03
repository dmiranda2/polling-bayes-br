from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from backtest import run_backtest
from candidate_status import apply_current_candidate_filter
from common import coerce_canonical, pollster_cnpj_conflicts
from fetch_data import fetch_all
from model import fit_nowcast
from plot import generate_plots
from preprocess import (
    choose_current_major_candidates,
    make_complete_composition,
    prepare_current_valid_shares,
    prepare_historical_valid_shares,
)
from report import top_candidates, write_report


def main():
    p = argparse.ArgumentParser(description="Brazil presidential polling joint compositional nowcast")
    p.add_argument("--config", default="config.json")
    p.add_argument("--data-dir", default="data")
    p.add_argument("--out", default="output")
    p.add_argument("--as-of", default=None, help="YYYY-MM-DD; defaults to today")
    p.add_argument("--no-fetch", action="store_true", help="Reuse data/polls_master.csv")
    p.add_argument("--scenario-regex", default=None, help="Override config scenario regex")
    p.add_argument("--no-backtest", action="store_true", help="Skip temporal backtest")
    args = p.parse_args()

    config_path = Path(args.config).resolve()
    cfg = json.load(open(config_path, encoding="utf-8"))
    if args.scenario_regex is not None:
        cfg["scenario_regex"] = args.scenario_regex
    data_dir = Path(args.data_dir)
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    master_path = data_dir / "polls_master.csv"

    if args.no_fetch:
        df = pd.read_csv(master_path)
    else:
        df = fetch_all(data_dir, data_dir / "manual_2026.csv")

    # Identity diagnostics on raw data: unchanged from v0.8.
    cnpj_conflicts = pollster_cnpj_conflicts(df)
    cnpj_conflicts.to_csv(out / "pollster_cnpj_conflicts.csv", index=False)
    identity_df = coerce_canonical(df)
    identity_df["source_pollster_label"] = identity_df["pollster_source"].fillna(identity_df["pollster"])
    identity_df["registered_pollster_label"] = identity_df["pollster_registered_name"].replace({"": pd.NA}).fillna(identity_df["pollster"])
    identity_df["canonical_pollster"] = identity_df["pollster"]
    pollster_identity_audit = (
        identity_df.groupby([
            "source_pollster_label", "registered_pollster_label", "canonical_pollster",
            "pollster_cnpj", "pollster_key",
        ], dropna=False)
        .agg(rows=("election_year", "size"), first_year=("election_year", "min"), last_year=("election_year", "max"))
        .reset_index()
        .sort_values(["canonical_pollster", "pollster_key", "source_pollster_label"])
    )
    pollster_identity_audit.to_csv(out / "pollster_identity_audit.csv", index=False)

    # Historical data are retained for audit/backtest only.  v0.9 does not transfer
    # candidate bias or institute-quality constants from 2018/2022 into the live fit.
    _, hist_audit = prepare_historical_valid_shares(df, cfg)
    hist_audit.to_csv(out / "historical_preprocess_audit.csv", index=False)

    current_valid, vote_basis_audit = prepare_current_valid_shares(df, cfg, args.as_of)
    vote_basis_audit.to_csv(out / "vote_basis_audit.csv", index=False)
    if current_valid.empty:
        raise RuntimeError("No current surveys survived valid-vote preprocessing")

    filtered_df, candidate_audit = apply_current_candidate_filter(
        current_valid, cfg, args.as_of, base_dir=config_path.parent
    )
    candidate_audit.to_csv(out / "candidate_filter_audit.csv", index=False)

    major_candidates = choose_current_major_candidates(filtered_df, cfg)
    current_composition, composition_audit = make_complete_composition(filtered_df, major_candidates)
    composition_audit.to_csv(out / "current_composition_audit.csv", index=False)
    if current_composition.empty:
        raise RuntimeError("No complete current survey compositions after major-candidate selection")

    # Fail closed on NAME/CNPJ identity splits in the actual current model input.
    current_identity = coerce_canonical(current_composition)
    unresolved = []
    for pollster, g in current_identity.groupby("pollster"):
        keys = sorted(set(g["pollster_key"].dropna().astype(str)))
        if len(keys) > 1 and any(k.startswith("NAME:") for k in keys) and any(k.startswith("CNPJ:") for k in keys):
            unresolved.append((pollster, keys))
    if unresolved:
        detail = "; ".join(f"{p}: {', '.join(keys)}" for p, keys in unresolved)
        raise RuntimeError("Unresolved current pollster identity split: " + detail)

    latest_all, trajectory_all, houses_all, used_all = fit_nowcast(
        current_identity, None, None, cfg, args.as_of
    )

    top5, vv_all = top_candidates(latest_all, int(cfg.get("output_top_n", 5)))
    top_names = set(top5["candidate"])
    trajectory = trajectory_all[trajectory_all["candidate"].isin(top_names)].copy()
    houses = houses_all[houses_all["candidate"].isin(top_names)].copy()

    top5.to_csv(out / "nowcast_latest.csv", index=False)
    vv_all.sort_values("median_pct", ascending=False).to_csv(out / "nowcast_all_candidates.csv", index=False)
    trajectory.to_csv(out / "nowcast_trajectory.csv", index=False)
    houses.to_csv(out / "house_effects.csv", index=False)
    houses_all.to_csv(out / "house_effects_all.csv", index=False)
    used_all.to_csv(out / "polls_used_2026.csv", index=False)

    threshold_cols = [c for c in [
        "candidate", "valid_median_pct", "valid_lower_80_pct", "valid_upper_80_pct",
        "election_lower_80_pct", "election_upper_80_pct", "distance_to_50_pp",
    ] if c in top5]
    threshold = top5[threshold_cols].copy().rename(
        columns={"distance_to_50_pp": "latent_mean_distance_to_50_pp"}
    )
    threshold.to_csv(out / "first_round_threshold.csv", index=False)

    hyper_cols = [c for c in [
        "rw_pair_sd_ilr_sqrt_day", "rw_field_sd_ilr_sqrt_day",
        "house_pair_sd_ilr", "house_field_sd_ilr",
        "poll_pair_sd_ilr", "poll_field_sd_ilr", "reml_nll",
    ] if c in houses_all]
    model_hyperparameters = houses_all[hyper_cols].drop_duplicates().reset_index(drop=True) if hyper_cols else pd.DataFrame()
    model_hyperparameters.to_csv(out / "model_hyperparameters.csv", index=False)

    pollster_effect_audit = pd.DataFrame()
    if not houses_all.empty:
        pollster_effect_audit = (
            houses_all.groupby(["pollster_key", "pollster"], as_index=False)
            .agg(
                n_current_polls=("n_current_polls", "max"),
                median_abs_house_effect_pp=("mean_house_effect_pp", lambda x: float(pd.Series(x).abs().median())),
                max_abs_house_effect_pp=("mean_house_effect_pp", lambda x: float(pd.Series(x).abs().max())),
                house_effect_ilr_norm=("house_effect_ilr_norm", "max"),
            )
            .sort_values(["n_current_polls", "pollster"], ascending=[False, True])
        )
    pollster_effect_audit.to_csv(out / "pollster_effect_audit.csv", index=False)

    backtest_detail = pd.DataFrame()
    backtest_metrics = pd.DataFrame()
    external_error_prior = pd.DataFrame()
    if not args.no_backtest:
        backtest_detail, backtest_metrics = run_backtest(df, cfg)
        external_error_prior = backtest_metrics.attrs.get("external_error_prior", pd.DataFrame())
        backtest_detail.to_csv(out / "backtest_temporal.csv", index=False)
        backtest_metrics.to_csv(out / "backtest_metrics.csv", index=False)
        external_error_prior.to_csv(out / "external_error_prior.csv", index=False)

    as_of = args.as_of or str(pd.Timestamp.today().normalize().date())
    manifest = {
        "version": str(cfg.get("version", "")),
        "as_of": as_of,
        "data_mode": "cached polls_master.csv" if args.no_fetch else "fresh fetch",
        "model": "joint_ilr_gaussian_reml_structured",
        "current_surveys_used": int(used_all["_survey_key"].nunique()) if "_survey_key" in used_all else None,
        "current_model_rows": int(len(used_all)),
        "major_candidates": major_candidates,
        "modeled_candidates": list(vv_all.sort_values("median_pct", ascending=False)["candidate"]),
        "historical_bias_transfer": False,
        "manual_pollster_novelty_penalty": False,
        "posthoc_simplex_projection": False,
        "external_election_error_enabled": bool(cfg.get("external_election_error_enabled", False)),
        "external_election_error_sd_pp": float(cfg.get("external_election_error_sd_pp", 0.0)),
        "tse_2022_offline_field_date_fallback": str((config_path.parent / "data" / "tse_2022_field_dates.csv").exists()).lower(),
    }
    (out / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    pair_current = vv_all[
        vv_all["candidate"].eq("Lula")
        | vv_all["candidate"].astype(str).str.contains("Bolsonaro", case=False, na=False)
    ].copy().sort_values("median_pct", ascending=False)

    write_report(
        out / "report.md", top5, as_of, backtest_metrics, pair_current,
        candidate_audit, pollster_effect_audit, external_error_prior, model_hyperparameters,
    )
    generate_plots(trajectory_all, top5, out, as_of, backtest_metrics, pair_current)

    print("\nNowcast — cinco candidatos (média latente das pesquisas, votos válidos):")
    cols = [c for c in [
        "candidate", "median_pct", "lower_80_pct", "upper_80_pct",
        "election_lower_80_pct", "election_upper_80_pct", "n_polls", "last_poll_date",
    ] if c in top5]
    print(top5[cols].to_string(index=False, float_format=lambda x: f"{x:.2f}"))
    if not model_hyperparameters.empty:
        print("\nREML variance components:")
        print(model_hyperparameters.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    if not backtest_metrics.empty:
        print("\nBacktest temporal:")
        print(backtest_metrics.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    print(f"\nWrote outputs to {out.resolve()}")


if __name__ == "__main__":
    main()