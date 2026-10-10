"""Optional *within-2026 first-round* pollster-bias sensitivity for the runoff.

The correction is a mechanical transfer of each pollster's observed *margin*
error in the first round. This is NOT a calibrated election forecast or an
estimate learned from earlier second rounds. Missing institute biases are
left untouched and explicitly audited.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from historical_second_round import _norm_text, pair_ilr


def alias_map(path: str | Path) -> dict[str, str]:
    aliases = pd.read_csv(path)
    if {"alias", "canonical"} - set(aliases):
        raise ValueError("Pollster alias file must have alias and canonical columns")
    mapping: dict[str, str] = {}
    for row in aliases.itertuples(index=False):
        key = _norm_text(row.alias)
        target = _norm_text(row.canonical)
        if not key or not target:
            raise ValueError("Blank pollster alias/canonical")
        if key in mapping and mapping[key] != target:
            raise ValueError(f"Ambiguous pollster alias: {row.alias}")
        mapping[key] = target
    return mapping


def read_first_round_bias(
    path: str | Path,
    aliases_path: str | Path = "data/pollster_aliases.csv",
) -> pd.DataFrame:
    """Read audited-by-consistency, user-supplied polling errors.

    Sign: error_pp = (Flavio - Lula)_poll,1T - (Flavio - Lula)_result,1T.
    A positive error overstates Flavio; *subtract* it from the 2T margin.
    The common 1.8 pp reference is IMPLIED by the supplied numbers; the
    file is not independently verified against official election results.
    """
    d = pd.read_csv(path)
    required = {
        "pollster", "first_round_poll_date", "first_round_lula_pct",
        "first_round_flavio_pct", "bias_flavio_minus_lula_pp",
        "reference_actual_margin_flavio_minus_lula_pp", "source_basis",
    }
    if required - set(d):
        raise ValueError("Incomplete first-round bias table: " + str(sorted(required - set(d))))
    if d.empty:
        raise ValueError("Empty first-round bias file: cannot build corrected scenario")
    names = alias_map(aliases_path)
    d["canonical_pollster"] = [names.get(_norm_text(x), _norm_text(x)) for x in d["pollster"]]
    if (d["canonical_pollster"] == "").any() or d["canonical_pollster"].duplicated().any():
        raise ValueError("Blank or duplicated canonical pollster in 1T bias file")
    for key in ("first_round_lula_pct", "first_round_flavio_pct",
                "bias_flavio_minus_lula_pp", "reference_actual_margin_flavio_minus_lula_pp"):
        d[key] = pd.to_numeric(d[key], errors="raise")
        if not np.isfinite(d[key].to_numpy(float)).all():
            raise ValueError(f"Nonfinite first-round bias input in {key}")
    for key in ("first_round_lula_pct", "first_round_flavio_pct"):
        if not d[key].between(0, 100).all():
            raise ValueError(f"Invalid reported first-round percentage in {key}")
    pd.to_datetime(d["first_round_poll_date"], errors="raise")
    implied = (d["first_round_flavio_pct"] - d["first_round_lula_pct"]
               - d["bias_flavio_minus_lula_pp"])
    if not np.allclose(implied, d["reference_actual_margin_flavio_minus_lula_pp"], atol=0.011):
        raise ValueError("First-round error sign/value inconsistent with the reported first-round margin")
    if d["reference_actual_margin_flavio_minus_lula_pp"].max() - d["reference_actual_margin_flavio_minus_lula_pp"].min() > 0.011:
        raise ValueError("First-round entries imply different election margins")
    return d


def apply_first_round_bias(
    surveys: pd.DataFrame,
    biases: pd.DataFrame | None = None,
    mode: str = "none",
    aliases_path: str | Path = "data/pollster_aliases.csv",
) -> pd.DataFrame:
    """Return adjusted paired shares, retaining the SAME poll sampling variance.

    By construction:
      margin_F-L_corrected = margin_F-L_published - error_1T_F-L
      Lula_corrected = Lula_published + error_1T_F-L / 2.
    There is no adjustment when bias is unknown: this is flagged, not
    interpreted as an observed zero error. The polling uncertainty intervals
    are conditional on the imposed shifts, NOT calibrated for transfer risk.
    """
    if mode not in {"none", "first_round_2026"}:
        raise ValueError(f"Unknown bias mode: {mode}")
    if mode == "first_round_2026" and (biases is None or biases.empty):
        raise ValueError("Corrected mode requires a nonempty 2026 first-round bias file")
    x = surveys.copy()
    names = alias_map(aliases_path)
    x["canonical_pollster"] = [names.get(_norm_text(z), _norm_text(z)) for z in x["pollster"]]
    if biases is None:
        known: dict[str, float] = {}
    else:
        if biases["canonical_pollster"].duplicated().any():
            raise ValueError("Duplicate canonical pollster biases")
        known = dict(zip(biases["canonical_pollster"], biases["bias_flavio_minus_lula_pp"]))
    x["bias_observed_first_round_pp"] = x["canonical_pollster"].map(known)
    x["first_round_bias_available"] = x["bias_observed_first_round_pp"].notna()
    x["first_round_bias_applied"] = x["first_round_bias_available"] & (mode == "first_round_2026")
    x["bias_shift_applied_pp"] = np.where(
        x["first_round_bias_applied"],
        x["bias_observed_first_round_pp"].fillna(0.0), 0.0,
    )
    x["lula_valid_pct_before_bias"] = x["lula_valid_pct"]
    x["flavio_valid_pct_before_bias"] = x["flavio_valid_pct"]
    x["lula_valid_pct_after_bias"] = x["lula_valid_pct"] + x["bias_shift_applied_pp"] / 2.0
    x["flavio_valid_pct_after_bias"] = x["flavio_valid_pct"] - x["bias_shift_applied_pp"] / 2.0
    if not (x["lula_valid_pct_after_bias"].between(0.001, 99.999).all()
            and x["flavio_valid_pct_after_bias"].between(0.001, 99.999).all()):
        raise ValueError("Bias correction made a two-candidate share invalid; review the data")
    if not np.allclose(x["lula_valid_pct_after_bias"] + x["flavio_valid_pct_after_bias"], 100, atol=0.01):
        raise ValueError("Bias correction broke valid-vote sum")
    x["z_for_model_ilr"] = [
        pair_ilr(l, f) for l, f in
        zip(x["lula_valid_pct_after_bias"], x["flavio_valid_pct_after_bias"])
    ]
    x["bias_mode"] = mode
    return x


def audit_calendar(path: str | Path) -> pd.DataFrame:
    """Audit scheduled registrations only; this is NEVER an observed poll feed."""
    c = pd.read_csv(path, keep_default_na=False)
    required = {
        "poll_id", "pollster", "scope", "uf", "expected_publish_date",
        "field_start", "field_end", "n", "source_basis",
    }
    if required - set(c):
        raise ValueError("Incomplete registration calendar: " + str(sorted(required - set(c))))
    if c["poll_id"].duplicated().any():
        raise ValueError("Duplicate registration ID in calendar")
    for key in ("expected_publish_date", "field_start", "field_end"):
        c[key] = pd.to_datetime(c[key], format="%Y-%m-%d", errors="raise").dt.date.astype(str)
    reason = []
    for r in c.itertuples(index=False):
        problems = []
        if r.field_start > r.field_end:
            problems.append("field_start_after_end")
        if r.expected_publish_date < r.field_end:
            problems.append("scheduled_publication_before_field_end")
        if str(r.scope) not in {"national", "regional"}:
            problems.append("unrecognized_scope")
        if not str(r.n).isdigit() or int(r.n) <= 0:
            problems.append("invalid_sample")
        reason.append(";".join(problems))
    c["calendar_audit"] = reason
    c["date_conflict"] = c["calendar_audit"] != ""
    c["data_status"] = "scheduled_only_no_2026_second_round_result"
    return c
