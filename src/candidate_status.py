from __future__ import annotations

from pathlib import Path

import pandas as pd

from common import normalize_candidate, survey_key


STATUS_COLUMNS = [
    "election_year", "candidate", "status", "valid_from", "valid_until",
    "source_url", "note",
]


def load_candidate_status(path: str | Path) -> pd.DataFrame:
    """Load the curated ballot-status snapshot used by the current nowcast.

    The file is intentionally small and auditable.  It is not a poll source: it
    only answers whether a name may participate in the current ballot-level
    nowcast once the ballot has been finalized.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Candidate status file not found: {path}")
    d = pd.read_csv(path)
    missing = [c for c in STATUS_COLUMNS if c not in d.columns]
    if missing:
        raise ValueError(f"Candidate status file is missing columns: {missing}")
    d = d[STATUS_COLUMNS].copy()
    d["election_year"] = pd.to_numeric(d["election_year"], errors="coerce").astype("Int64")
    d["candidate"] = d["candidate"].map(normalize_candidate)
    d["status"] = d["status"].astype(str).str.strip().str.lower()
    d["valid_from"] = pd.to_datetime(d["valid_from"], errors="coerce")
    d["valid_until"] = pd.to_datetime(d["valid_until"], errors="coerce")
    return d


def eligible_candidates(status: pd.DataFrame, year: int, as_of: str | pd.Timestamp) -> set[str]:
    """Return candidates marked eligible on the given date, inclusive."""
    ts = pd.Timestamp(as_of).normalize()
    d = status[(status["election_year"] == int(year)) & status["status"].eq("eligible")].copy()
    if d.empty:
        return set()
    ok_from = d["valid_from"].isna() | (d["valid_from"] <= ts)
    ok_until = d["valid_until"].isna() | (d["valid_until"] >= ts)
    return set(d.loc[ok_from & ok_until, "candidate"].dropna())


def apply_current_candidate_filter(
    df: pd.DataFrame,
    config: dict,
    as_of: str | pd.Timestamp | None = None,
    base_dir: str | Path = ".",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Filter current-election rows to the finalized presidential ballot.

    Before ``candidate_status_strict_from`` the function is deliberately
    permissive, because exploratory/hypothetical polling scenarios may still
    be informative before the ballot is finalized.  On and after that date it
    is fail-closed: a missing/empty official allow-list raises instead of
    silently allowing obsolete candidates into the current valid-vote
    denominator.
    """
    out = df.copy()
    year = int(config.get("current_year", 2026))
    round_no = int(config.get("current_round", 1))
    ts = pd.Timestamp(as_of).normalize() if as_of else pd.Timestamp.today().normalize()
    strict_from_raw = config.get("candidate_status_strict_from")
    strict_from = pd.Timestamp(strict_from_raw).normalize() if strict_from_raw else None

    year_values = pd.to_numeric(out["election_year"], errors="coerce")
    round_values = pd.to_numeric(out["round"], errors="coerce")
    mask_current = year_values.eq(year) & round_values.eq(round_no)
    out.loc[mask_current, "candidate"] = out.loc[mask_current, "candidate"].map(normalize_candidate)
    cur = out[mask_current].copy()
    if cur.empty:
        return out, pd.DataFrame(columns=[
            "candidate", "rows", "unique_polls", "last_publish_date",
            "eligible_on_as_of", "action", "reason",
        ])

    # Audit every candidate seen in the current-cycle source.  Count surveys
    # with the same stable fallback key used by the model so polls without a
    # TSE registration are not reported as zero.
    cur["_candidate_filter_survey_key"] = survey_key(cur)
    audit = (
        cur.groupby("candidate", dropna=False)
        .agg(
            rows=("candidate", "size"),
            unique_polls=("_candidate_filter_survey_key", "nunique"),
            last_publish_date=("publish_date", "max"),
        )
        .reset_index()
    )

    if strict_from is not None and ts < strict_from:
        audit["eligible_on_as_of"] = pd.NA
        audit["action"] = "kept"
        audit["reason"] = f"ballot filter not strict before {strict_from.date().isoformat()}"
        return out, audit

    status_path = Path(config.get("candidate_status_file", "data/candidate_status_2026.csv"))
    if not status_path.is_absolute():
        status_path = Path(base_dir) / status_path
    status = load_candidate_status(status_path)
    allowed = eligible_candidates(status, year, ts)
    if not allowed:
        raise RuntimeError(
            f"No eligible presidential candidates found for {year} on {ts.date()} in {status_path}. "
            "Refusing to produce a current nowcast without a ballot allow-list."
        )

    audit["eligible_on_as_of"] = audit["candidate"].isin(allowed)
    audit["action"] = audit["eligible_on_as_of"].map({True: "kept", False: "excluded"})
    audit["reason"] = audit["eligible_on_as_of"].map({
        True: "na cédula presidencial final",
        False: "fora da cédula presidencial final",
    })

    # For surveys that contain a now-ineligible/withdrawn candidate, take the
    # coherent subcomposition on the current ballot: remove that coordinate and
    # renormalize only that survey.  Surveys that already contain only current
    # candidates are left untouched because an omitted minor candidate should
    # remain missing/residual rather than being silently redistributed.
    out["_candidate_filter_survey_key"] = survey_key(out)
    current_keys_with_excluded = set(
        out.loc[mask_current & ~out["candidate"].isin(allowed), "_candidate_filter_survey_key"].astype(str)
    )
    keep_current = (~mask_current) | out["candidate"].isin(allowed)
    filtered = out[keep_current].copy()
    filtered["pct"] = pd.to_numeric(filtered["pct"], errors="coerce").astype(float)
    if "vote_basis" not in filtered.columns:
        filtered["vote_basis"] = ""
    else:
        filtered["vote_basis"] = filtered["vote_basis"].fillna("").astype(str)
    if bool(config.get("renormalize_removed_candidates", True)) and current_keys_with_excluded:
        for key in current_keys_with_excluded:
            idx = filtered.index[
                filtered["_candidate_filter_survey_key"].astype(str).eq(key)
                & pd.to_numeric(filtered["election_year"], errors="coerce").eq(year)
                & pd.to_numeric(filtered["round"], errors="coerce").eq(round_no)
            ]
            if len(idx) == 0:
                continue
            total = float(pd.to_numeric(filtered.loc[idx, "pct"], errors="coerce").sum())
            if 0 < total <= 103.0:
                filtered.loc[idx, "pct"] = 100.0 * pd.to_numeric(filtered.loc[idx, "pct"], errors="coerce") / total
                filtered.loc[idx, "vote_basis"] = filtered.loc[idx, "vote_basis"].astype(str).str.rstrip("+") + "+current_ballot_subcomposition"

    filtered = filtered.drop(columns=["_candidate_filter_survey_key"], errors="ignore").reset_index(drop=True)
    return filtered, audit.sort_values(["action", "candidate"], ascending=[True, True]).reset_index(drop=True)