from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

from common import coerce_canonical, normalize_candidate, normalize_registration, response_kind, survey_key

# Ballot identities only; percentages live in backtest.py.
HISTORICAL_BALLOTS = {
    2018: {
        "Jair Bolsonaro", "Fernando Haddad", "Ciro Gomes", "Geraldo Alckmin",
        "João Amoêdo", "Cabo Daciolo", "Henrique Meirelles", "Marina Silva",
        "Álvaro Dias", "Guilherme Boulos", "Vera Lúcia", "Eymael",
        "João Goulart Filho",
    },
    # The Nexo 2022 source used by this project individualizes these four.
    2022: {"Lula", "Jair Bolsonaro", "Simone Tebet", "Ciro Gomes"},
}

HISTORICAL_MODELED = {
    2018: ["Jair Bolsonaro", "Fernando Haddad", "Ciro Gomes", "Geraldo Alckmin", "João Amoêdo"],
    2022: ["Lula", "Jair Bolsonaro", "Simone Tebet", "Ciro Gomes"],
}
OTHER_CANDIDATES = "Outros candidatos"


def apply_historical_field_date_overrides(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """Apply small audited offline TSE field-date fallbacks when available.

    The v0.7 cache already contains TSE identity/sample metadata, but its 2022
    field interval was populated from the Nexo single `Data` column before the
    TSE interval could replace it.  The v0.8 fetch fixes that at ingestion time.
    This compact fallback keeps cached/offline backtests consistent with the
    official TSE field dates as well.
    """
    out = df.copy()
    if int(year) != 2022:
        return out
    # The canonical cache may still hold these columns as strings.  Coerce the
    # target columns before assigning Timestamp values so the audited fallback
    # works with pandas' strict StringArray assignment (pandas 3+).
    out["field_start"] = pd.to_datetime(out["field_start"], errors="coerce")
    out["field_end"] = pd.to_datetime(out["field_end"], errors="coerce")
    path = Path(__file__).resolve().parent.parent / "data" / "tse_2022_field_dates.csv"
    if not path.exists():
        return out
    m = pd.read_csv(path, dtype=str).fillna("")
    if m.empty or not {"registration_id", "field_start", "field_end"}.issubset(m.columns):
        return out
    m["_reg_key"] = m["registration_id"].map(normalize_registration)
    start_map = dict(zip(m["_reg_key"], pd.to_datetime(m["field_start"], errors="coerce")))
    end_map = dict(zip(m["_reg_key"], pd.to_datetime(m["field_end"], errors="coerce")))
    keys = out["poll_id"].map(normalize_registration)
    mapped_start = keys.map(start_map)
    mapped_end = keys.map(end_map)
    use = mapped_start.notna() | mapped_end.notna()
    if use.any():
        out.loc[use & mapped_start.notna(), "field_start"] = mapped_start[use & mapped_start.notna()]
        out.loc[use & mapped_end.notna(), "field_end"] = mapped_end[use & mapped_end.notna()]
        out.loc[use, "field_date_source"] = "TSE offline fallback"
    return out


def _ascii(s: object) -> str:
    raw = "" if s is None else str(s).strip()
    return "".join(c for c in unicodedata.normalize("NFKD", raw) if not unicodedata.combining(c)).upper()


_HIST_ALIASES = {
    "BOLSONARO": "Jair Bolsonaro",
    "JAIR BOLSONARO": "Jair Bolsonaro",
    "ALVARO DIAS": "Álvaro Dias",
    "VERA": "Vera Lúcia",
    "VERA LUCIA": "Vera Lúcia",
    "JOAO GOULART FILHO": "João Goulart Filho",
    "CABO DACIOLO": "Cabo Daciolo",
    "GUILHERME BOULOS": "Guilherme Boulos",
    "HENRIQUE MEIRELLES": "Henrique Meirelles",
    "GERALDO ALCKMIN": "Geraldo Alckmin",
    "JOAO AMOEDO": "João Amoêdo",
    "MARINA SILVA": "Marina Silva",
    "FERNANDO HADDAD": "Fernando Haddad",
    "CIRO GOMES": "Ciro Gomes",
    "SIMONE TEBET": "Simone Tebet",
    "EYMAEL": "Eymael",
}


def normalize_historical_candidate(s: object, year: int) -> str:
    base = normalize_candidate(s)
    return _HIST_ALIASES.get(_ascii(base), base)


def _poll_identity(df: pd.DataFrame) -> pd.Series:
    """Survey identity without scenario; used to choose one scenario per poll."""
    pid = df["poll_id"].astype(str).replace({"nan": "", "None": "", "<NA>": ""})
    fallback = (
        df["pollster_key"].astype(str) + "|"
        + pd.to_datetime(df["field_start"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("") + "|"
        + pd.to_datetime(df["field_end"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("") + "|"
        + pd.to_datetime(df["publish_date"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    )
    year = pd.to_numeric(df["election_year"], errors="coerce").astype("Int64").astype(str)
    rnd = pd.to_numeric(df["round"], errors="coerce").astype("Int64").astype(str)
    return year + "|" + rnd + "|" + np.where(pid.str.len().gt(0), pid, fallback)


def _basis_features(g: pd.DataFrame, config: dict, allow_partial_2022: bool = False) -> dict:
    kinds = g["candidate"].map(response_kind)
    valid_mask = kinds.isin(["candidate", "other_candidate"])
    nonvalid_mask = kinds.eq("nonvalid")
    raw_valid_sum = float(pd.to_numeric(g.loc[valid_mask, "pct"], errors="coerce").sum())
    nonvalid_sum = float(pd.to_numeric(g.loc[nonvalid_mask, "pct"], errors="coerce").sum())
    all_sum = raw_valid_sum + nonvalid_sum
    scenario = " ".join(g["scenario"].dropna().astype(str).unique())
    explicit_valid = bool(re.search(r"valid", _ascii(scenario).lower()))
    manual_valid_series = pd.to_numeric(g.get("pct_valid"), errors="coerce")
    manual_valid = bool(manual_valid_series.notna().any())
    # For a curated row with published valid shares, report the sum of the actual
    # valid-share column in the audit.  The raw total-vote sum is kept separately
    # so diagnostics never claim that e.g. a 89.6% total-vote candidate mass is
    # the sum of the published valid percentages.
    if manual_valid:
        valid_sum = float(manual_valid_series.loc[valid_mask].sum())
    else:
        valid_sum = raw_valid_sum
    has_nonvalid = bool(nonvalid_mask.any())
    total_ok = float(config.get("valid_group_total_min", 95.0)) <= all_sum <= float(config.get("valid_group_total_max", 105.0))
    implicit_valid = (
        float(config.get("implicit_valid_sum_min", 97.0))
        <= valid_sum
        <= float(config.get("implicit_valid_sum_max", 103.0))
    )
    year = int(g["election_year"].iloc[0])
    # This is deliberately a historical-only fallback.  It may be used only
    # after a first-round scenario covers every coordinate we actually model
    # for that historical ballot.  It never turns a sparse contemporary poll
    # into a guessed valid-vote observation.
    candidate_names = {
        normalize_historical_candidate(x, year)
        for x in g.loc[kinds.eq("candidate"), "candidate"].dropna()
    }
    modeled_ballot = set(HISTORICAL_MODELED.get(year, []))
    covers_ballot = bool(modeled_ballot) and modeled_ballot.issubset(candidate_names)
    implicit_total = (
        year in HISTORICAL_MODELED
        and not has_nonvalid
        and covers_ballot
        and float(config.get("implicit_total_candidate_sum_min", 50.0)) <= raw_valid_sum
        < float(config.get("implicit_total_candidate_sum_max", 95.0))
    )
    partial_2022 = allow_partial_2022 and int(g["election_year"].iloc[0]) == 2022 and str(g["source"].iloc[0]) == "Nexo Dados"
    if manual_valid:
        basis, quality = "published_valid", 6
    elif explicit_valid:
        basis, quality = "published_valid", 5
    elif has_nonvalid and total_ok and valid_sum > 0:
        basis, quality = "total_with_nonvalid", 4
    elif implicit_total and valid_sum > 0:
        # Lower quality than total_with_nonvalid: the missing non-valid mass is
        # inferred from a structurally complete candidate-only table.
        basis, quality = "total_implicit_nonvalid", 2
    elif implicit_valid and valid_sum > 0:
        basis, quality = "implicit_valid", 3
    elif partial_2022 and valid_sum > 0:
        basis, quality = "partial_observed_2022", 2
    else:
        basis, quality = "ambiguous", 0
    return {
        "basis": basis,
        "quality": quality,
        "valid_sum": valid_sum,
        "raw_candidate_sum": raw_valid_sum,
        "nonvalid_sum": nonvalid_sum,
        "all_sum": all_sum,
        "has_nonvalid": has_nonvalid,
        "explicit_valid": explicit_valid,
        "manual_valid": manual_valid,
        "covers_ballot": covers_ballot,
    }


def select_primary_scenarios(df: pd.DataFrame, year: int, config: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Select one historical first-round scenario per survey before calibration.

    Selection uses identities and structural completeness only, never percentages
    from the realized election.  Using the final ballot identities is retrospective
    and is therefore confined to historical calibration/backtesting.
    """
    ballot = HISTORICAL_BALLOTS[int(year)]
    d = coerce_canonical(df)
    d = apply_historical_field_date_overrides(d, int(year))
    d = d[(d["election_year"] == int(year)) & (d["round"] == 1)].copy()
    if d.empty:
        return d, pd.DataFrame()
    d["candidate"] = d["candidate"].map(lambda x: normalize_historical_candidate(x, int(year)))
    d["_poll_identity"] = _poll_identity(d)
    rows = []
    chosen = []
    for poll_key, pg in d.groupby("_poll_identity", sort=False):
        scored = []
        for scenario, sg in pg.groupby("scenario", dropna=False, sort=False):
            kinds = sg["candidate"].map(response_kind)
            names = set(sg.loc[kinds.eq("candidate"), "candidate"].dropna())
            overlap = len(names & ballot)
            outsiders = len(names - ballot)
            feat = _basis_features(sg, config, allow_partial_2022=True)
            # Candidate coverage dominates; then prefer a structurally usable basis.
            score = (overlap, -outsiders, feat["quality"], len(names))
            scored.append((score, str(scenario), sg, feat, overlap, outsiders))
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        score, scenario, sg, feat, overlap, outsiders = scored[0]
        chosen.append(sg)
        rows.append({
            "election_year": int(year), "poll_identity": poll_key, "scenario": scenario,
            "candidate_overlap": overlap, "outsiders": outsiders,
            "vote_basis_candidate": feat["basis"], "basis_quality": feat["quality"],
            "action": "selected",
        })
    out = pd.concat(chosen, ignore_index=True).drop(columns=["_poll_identity"], errors="ignore")
    return out, pd.DataFrame(rows)


def to_valid_shares(df: pd.DataFrame, config: dict, allow_partial_2022: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Convert each survey/scenario to a common valid-vote estimand.

    Rows already published as valid shares remain valid shares (up to tiny
    normalization for rounded 97--103 totals). Total-vote surveys with explicit
    blank/null/undecided rows are divided by their observed valid mass. Ambiguous
    candidate-only groups are dropped rather than guessed, except for the
    conservative historical `total_implicit_nonvalid` fallback: all modeled
    ballot coordinates must be present and their total must be 50--<95. Legacy Nexo 2022 rows
    without `Outros`/`BNI` are explicitly treated as a four-candidate subcomposition.
    """
    d = coerce_canonical(df)
    if d.empty:
        return d, pd.DataFrame()
    d["_survey_key"] = survey_key(d)
    pieces = []
    audit = []
    for key, g in d.groupby("_survey_key", sort=False):
        feat = _basis_features(g, config, allow_partial_2022=allow_partial_2022)
        basis = feat["basis"]
        kinds = g["candidate"].map(response_kind)
        candidate_mask = kinds.eq("candidate")
        keep = g[candidate_mask].copy()
        if keep.empty or basis == "ambiguous":
            audit.append({
                "survey_key": key, "election_year": int(g["election_year"].iloc[0]),
                "pollster": str(g["pollster"].iloc[0]), "poll_id": str(g["poll_id"].iloc[0]),
                "scenario": str(g["scenario"].iloc[0]), "vote_basis": basis,
                "valid_sum": feat["valid_sum"], "raw_candidate_sum": feat.get("raw_candidate_sum"),
                "nonvalid_sum": feat["nonvalid_sum"], "all_sum": feat["all_sum"], "action": "dropped",
            })
            continue

        if basis == "published_valid" and pd.to_numeric(g.get("pct_valid"), errors="coerce").notna().any():
            valid_map = pd.to_numeric(g.loc[candidate_mask, "pct_valid"], errors="coerce")
            keep["pct_total"] = keep["pct"]
            keep["pct"] = valid_map.to_numpy()
            keep = keep[keep["pct"].notna()].copy()
        elif basis == "published_valid":
            # Explicitly labelled valid shares are kept as published; omissions are
            # missing observations, not zeros to be redistributed.
            keep["pct_total"] = np.nan
        elif basis in {"total_with_nonvalid", "total_implicit_nonvalid", "partial_observed_2022"}:
            denom = feat["valid_sum"]
            keep["pct_total"] = keep["pct"]
            keep["pct"] = 100.0 * keep["pct"] / denom
        elif basis == "implicit_valid":
            # Only a small rounding correction (97--103 by config) is allowed.
            denom = feat["valid_sum"]
            keep["pct_total"] = np.nan
            keep["pct"] = 100.0 * keep["pct"] / denom

        keep["vote_basis"] = basis
        keep["_survey_key"] = key
        pieces.append(keep)
        audit.append({
            "survey_key": key, "election_year": int(g["election_year"].iloc[0]),
            "pollster": str(g["pollster"].iloc[0]), "poll_id": str(g["poll_id"].iloc[0]),
            "scenario": str(g["scenario"].iloc[0]), "vote_basis": basis,
            "valid_sum": feat["valid_sum"], "raw_candidate_sum": feat.get("raw_candidate_sum"),
            "nonvalid_sum": feat["nonvalid_sum"], "all_sum": feat["all_sum"], "action": "kept",
        })
    if not pieces:
        return pd.DataFrame(columns=list(d.columns) + ["pct_total", "_survey_key"]), pd.DataFrame(audit)
    out = pd.concat(pieces, ignore_index=True)
    out = out[out["pct"].between(0, 100, inclusive="both")].copy()
    return out, pd.DataFrame(audit)


def choose_current_major_candidates(df: pd.DataFrame, config: dict) -> list[str]:
    """Choose a stable set of individually modeled current candidates from polls.

    This uses only observed poll shares, never election outcomes. Candidates below
    the threshold are retained through a single `Outros candidatos` residual.
    """
    if df.empty:
        return []
    med = df.groupby("candidate")["pct"].median().sort_values(ascending=False)
    threshold = float(config.get("current_major_min_median_pp", 0.5))
    min_count = int(config.get("current_major_min_count", 5))
    max_count = int(config.get("current_major_max_count", 7))
    selected = list(med[med >= threshold].index[:max_count])
    for c in med.index:
        if len(selected) >= min_count:
            break
        if c not in selected:
            selected.append(c)
    return selected[:max_count]


def make_complete_composition(
    df: pd.DataFrame,
    major_candidates: list[str],
    other_label: str = OTHER_CANDIDATES,
    include_other: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Collapse each survey to a complete major-candidates + Other composition.

    Surveys missing any major candidate are dropped instead of interpreting the
    omission as zero. The residual category absorbs every other valid candidate,
    so each retained survey sums exactly to 100 before modeling.
    """
    if df.empty or not major_candidates:
        return df.copy(), pd.DataFrame()
    d = df.copy()
    if "_survey_key" not in d.columns:
        d["_survey_key"] = survey_key(d)
    pieces, audit = [], []
    for key, g in d.groupby("_survey_key", sort=False):
        vals = g.groupby("candidate")["pct"].first()
        missing = [c for c in major_candidates if c not in vals.index or pd.isna(vals[c])]
        if missing:
            audit.append({"survey_key": key, "action": "dropped", "reason": "missing major candidates: " + ", ".join(missing)})
            continue
        major_sum = float(sum(float(vals[c]) for c in major_candidates))
        if major_sum <= 0 or major_sum > 103.0:
            audit.append({"survey_key": key, "action": "dropped", "reason": f"major-candidate sum {major_sum:.2f} outside plausible range"})
            continue
        base = g.iloc[0].copy()
        rows = []
        # With an explicit Other bucket, keep the published major shares and let
        # the residual represent all remaining valid candidates.  Without Other
        # (the deliberate 2022 top-four subcomposition), renormalize the modeled
        # candidates to 100 so the estimand matches the renormalized official truth.
        scale = (100.0 / major_sum) if (not include_other or major_sum > 100.0) else 1.0
        for c in major_candidates:
            src = g[g["candidate"].eq(c)].iloc[0].copy()
            src["pct"] = float(vals[c]) * scale
            rows.append(src)
        other = max(0.0, 100.0 - sum(float(r["pct"]) for r in rows))
        if include_other:
            base["candidate"] = other_label
            base["pct"] = other
            base["pct_valid"] = other
            base["pct_total"] = np.nan
            base["vote_basis"] = "composition_residual"
            rows.append(base)
        pieces.append(pd.DataFrame(rows))
        audit.append({"survey_key": key, "action": "kept", "reason": "complete composition", "other_pct": other if include_other else 0.0})
    out = pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame(columns=d.columns)
    return out, pd.DataFrame(audit)


def prepare_historical_valid_shares(df: pd.DataFrame, config: dict, years: list[int] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    years = [int(y) for y in (years if years is not None else config.get("history_years", [2018, 2022]))]
    pieces, audits = [], []
    for year in years:
        selected, sa = select_primary_scenarios(df, year, config)
        valid, va = to_valid_shares(selected, config, allow_partial_2022=True)
        ballot = HISTORICAL_BALLOTS[year]
        valid = valid[valid["candidate"].isin(ballot)].copy()
        valid, ca = make_complete_composition(valid, HISTORICAL_MODELED[year], include_other=(year != 2022))
        pieces.append(valid)
        if not sa.empty:
            sa["audit_type"] = "scenario_selection"
            audits.append(sa)
        if not va.empty:
            va["audit_type"] = "vote_basis"
            audits.append(va)
        if not ca.empty:
            ca["election_year"] = year
            ca["audit_type"] = "composition"
            audits.append(ca)
    return (pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame(),
            pd.concat(audits, ignore_index=True, sort=False) if audits else pd.DataFrame())


def prepare_current_valid_shares(df: pd.DataFrame, config: dict, as_of: str | pd.Timestamp | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = coerce_canonical(df)
    year = int(config.get("current_year", 2026))
    rnd = int(config.get("current_round", 1))
    ts = pd.Timestamp(as_of).normalize() if as_of else pd.Timestamp.today().normalize()
    d = d[(d["election_year"] == year) & (d["round"] == rnd) & (d["publish_date"] <= ts)].copy()
    pattern = config.get("scenario_regex")
    if pattern:
        d = d[d["scenario"].astype(str).str.contains(pattern, regex=True, na=False)].copy()
    strict = config.get("candidate_status_strict_from")
    if bool(config.get("current_use_final_ballot_only", True)) and strict and ts >= pd.Timestamp(strict):
        d = d[d["publish_date"] >= pd.Timestamp(strict)].copy()
    return to_valid_shares(d, config, allow_partial_2022=False)