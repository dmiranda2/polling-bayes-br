from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from common import coerce_canonical, midpoint_date
from preprocess import prepare_historical_valid_shares


def robust_scale(x: pd.Series | np.ndarray) -> float:
    x = np.asarray(pd.Series(x).dropna(), dtype=float)
    if len(x) < 2:
        return np.nan
    med = np.median(x)
    mad = np.median(np.abs(x - med))
    if mad > 1e-9:
        return float(1.4826 * mad)
    return float(np.std(x, ddof=1)) if len(x) > 1 else np.nan


def peer_residuals(df: pd.DataFrame, window_days: int = 7) -> pd.DataFrame:
    """Residual to a leave-one-pollster-out local median.

    This is not an election forecast. It measures how a pollster differs from
    nearby polls of the same candidate/round, which is useful for estimating
    persistent house effects and extra dispersion.
    """
    d = coerce_canonical(df)
    d["measure_date"] = midpoint_date(d["field_start"], d["field_end"])
    rows = []
    group_cols = ["election_year", "round", "candidate"]
    for _, g in d.groupby(group_cols, dropna=False):
        g = g.sort_values("measure_date")
        for idx, r in g.iterrows():
            if pd.isna(r["measure_date"]):
                continue
            lo = r["measure_date"] - pd.Timedelta(days=window_days)
            hi = r["measure_date"] + pd.Timedelta(days=window_days)
            peers = g[(g["measure_date"].between(lo, hi)) & (g["pollster_key"] != r["pollster_key"])]
            if len(peers) < 2:
                continue
            center = float(peers["pct"].median())
            rr = r.to_dict()
            rr["peer_center_pct"] = center
            rr["residual_pp"] = float(r["pct"] - center)
            rows.append(rr)
    return pd.DataFrame(rows)


def calibrate(history: pd.DataFrame, config: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    # v0.8 calibrates only after selecting one historical first-round scenario
    # per survey and converting every retained observation to the same valid-vote
    # estimand. This prevents valid/total and hypothetical-scenario differences
    # from masquerading as pollster quality.
    h, _ = prepare_historical_valid_shares(history, config, config.get("history_years", [2018, 2022]))
    if h.empty:
        raise RuntimeError("No usable historical first-round polls after valid-vote preprocessing")
    h["field_end"] = pd.to_datetime(h["field_end"])

    # Concentrate calibration near each election, where candidate sets are most
    # comparable and the data are densest.
    keep = []
    days = int(config.get("history_window_days", 120))
    for (yr, rnd), g in h.groupby(["election_year", "round"], dropna=True):
        end = g["field_end"].max()
        keep.append(g[g["field_end"] >= end - pd.Timedelta(days=days)])
    h = pd.concat(keep, ignore_index=True) if keep else h

    resid = peer_residuals(h, int(config.get("calibration_peer_window_days", 7)))
    if resid.empty:
        raise RuntimeError("No overlapping historical polls available for calibration")

    # Candidate-specific historical bias: only transferred to the same named
    # candidate, and strongly shrunk toward zero.
    k = float(config.get("calibration_shrinkage_k", 12.0))
    bias_rows = []
    for (pollster_key, candidate), g in resid.groupby(["pollster_key", "candidate"]):
        n = len(g)
        raw = float(g["residual_pp"].mean())
        shrunk = (n / (n + k)) * raw
        label = g["pollster"].mode().iloc[0] if not g["pollster"].mode().empty else str(g["pollster"].iloc[0])
        bias_rows.append({
            "pollster_key": pollster_key, "pollster": label, "candidate": candidate, "n_history": n,
            "bias_raw_pp": raw, "bias_shrunk_pp": shrunk
        })
    bias = pd.DataFrame(bias_rows).sort_values(["candidate", "pollster", "pollster_key"])

    # Extra pollster dispersion after removing pollster×candidate mean residual.
    keymean = resid.groupby(["pollster_key", "candidate"])["residual_pp"].transform("mean")
    resid["centered_residual_pp"] = resid["residual_pp"] - keymean
    global_sd = robust_scale(resid["centered_residual_pp"])
    if not np.isfinite(global_sd) or global_sd < 0.25:
        global_sd = 2.0
    qrows = []
    for pollster_key, g in resid.groupby("pollster_key"):
        n = len(g)
        sd = robust_scale(g["centered_residual_pp"])
        if not np.isfinite(sd):
            sd = global_sd
        var = (n * sd * sd + k * global_sd * global_sd) / (n + k)
        shrunk_sd = float(np.sqrt(var))
        shrunk_sd = float(np.clip(
            shrunk_sd,
            config.get("min_quality_sd_pp", 0.75),
            config.get("max_quality_sd_pp", 6.0),
        ))
        label = g["pollster"].mode().iloc[0] if not g["pollster"].mode().empty else str(g["pollster"].iloc[0])
        qrows.append({
            "pollster_key": pollster_key,
            "pollster": label,
            "n_history": n,
            "raw_extra_sd_pp": sd,
            "extra_sd_pp": shrunk_sd,
            "global_extra_sd_pp": global_sd,
        })
    quality = pd.DataFrame(qrows).sort_values(["pollster", "pollster_key"])
    return quality, bias, resid


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/polls_master.csv")
    p.add_argument("--config", default="config.json")
    p.add_argument("--out", default="output")
    args = p.parse_args()
    cfg = json.load(open(args.config, encoding="utf-8"))
    df = pd.read_csv(args.data)
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    q, b, r = calibrate(df, cfg)
    q.to_csv(out / "pollster_quality.csv", index=False)
    b.to_csv(out / "historical_bias.csv", index=False)
    r.to_csv(out / "historical_peer_residuals.csv", index=False)