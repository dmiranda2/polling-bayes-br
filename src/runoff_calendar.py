"""Calendar audit only; not a source of vote estimates or historical bias."""
from pathlib import Path
import pandas as pd


def audit_calendar(path: str | Path) -> pd.DataFrame:
    c = pd.read_csv(path, keep_default_na=False)
    needed = {"poll_id", "pollster", "scope", "uf", "expected_publish_date",
              "field_start", "field_end", "n", "source_basis"}
    if needed - set(c):
        raise ValueError("Incomplete calendar: " + str(sorted(needed - set(c))))
    if c["poll_id"].duplicated().any():
        raise ValueError("Duplicate registration")
    forbidden = {"pct_valid", "bias_flavio_minus_lula_pp",
                 "prior_first_round_lula_pct", "prior_first_round_flavio_pct"}
    if forbidden & set(c):
        raise ValueError("Calendar cannot include vote shares or first-round bias")
    for key in ("expected_publish_date", "field_start", "field_end"):
        c[key] = pd.to_datetime(c[key], errors="raise", format="%Y-%m-%d").dt.date.astype(str)
    flags = []
    for r in c.itertuples(index=False):
        reasons = []
        if r.field_start > r.field_end:
            reasons.append("field_start_after_end")
        if r.expected_publish_date < r.field_end:
            reasons.append("scheduled_publication_before_field_end")
        if r.scope not in {"national", "regional"}:
            reasons.append("invalid_scope")
        if not str(r.n).isdigit() or int(r.n) <= 0:
            reasons.append("invalid_sample")
        flags.append(";".join(reasons))
    c["calendar_audit"] = flags
    c["date_conflict"] = c["calendar_audit"] != ""
    c["data_status"] = "scheduled_only_no_results"
    return c
