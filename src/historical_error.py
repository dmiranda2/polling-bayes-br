from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd
from scipy.linalg import cho_factor, cho_solve
from scipy.optimize import minimize
from scipy.stats import norm, t as student_t

BASE_DOS_DADOS_URL = (
    "https://storage.googleapis.com/basedosdados-public/"
    "one-click-download/br_poder360_pesquisas/microdados/microdados.csv.gz"
)

WINDOWS_DEFAULT = (3, 7, 14)


def _norm_text(value: object) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    s = unicodedata.normalize("NFKD", str(value))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^A-Za-z0-9]+", " ", s).strip().upper()
    return re.sub(r"\s+", " ", s)


def _alias_match(name: object, aliases: str) -> bool:
    n = _norm_text(name)
    if not n:
        return False
    return n in {_norm_text(x) for x in str(aliases).split("|") if str(x).strip()}


def _numeric(s: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(s):
        return pd.to_numeric(s, errors="coerce")
    return pd.to_numeric(s.astype(str).str.replace(",", ".", regex=False), errors="coerce")


def _effective_n(n: float, moe_pp: float, default_n: float = 1200.0, design_effect: float = 1.5) -> float:
    vals: list[float] = []
    if np.isfinite(n) and n > 20:
        vals.append(float(n) / max(float(design_effect), 1.0))
    if np.isfinite(moe_pp) and 0.2 < moe_pp < 20:
        m = float(moe_pp) / 100.0
        vals.append(1.96**2 * 0.25 / (m * m))
    return max(50.0, min(vals) if vals else float(default_n) / max(float(design_effect), 1.0))


def pair_ilr(p_ref: float, p_opp: float) -> float:
    """Leading Helmert ILR coordinate: (log p_ref - log p_opp)/sqrt(2)."""
    p_ref = float(p_ref)
    p_opp = float(p_opp)
    if not (p_ref > 0 and p_opp > 0):
        raise ValueError("pair shares must be strictly positive")
    return float((math.log(p_ref) - math.log(p_opp)) / math.sqrt(2.0))


def pair_ilr_sampling_var(p_ref: float, p_opp: float, n_eff: float) -> float:
    """Delta-method variance for the leading pair ILR coordinate.

    For a multinomial composition and z=(log p1-log p2)/sqrt(2),
    Var(z) ~= (1/p1 + 1/p2)/(2 n_eff).
    The formula is invariant to whether the published values are later
    renormalized to valid votes only, as long as p1 and p2 are the shares
    actually sampled in the reported composition.
    """
    p_ref = float(p_ref)
    p_opp = float(p_opp)
    n_eff = max(float(n_eff), 1.0)
    if not (p_ref > 0 and p_opp > 0):
        raise ValueError("pair shares must be strictly positive")
    return float((1.0 / p_ref + 1.0 / p_opp) / (2.0 * n_eff))


def load_results(path: str | Path) -> pd.DataFrame:
    d = pd.read_csv(path)
    required = {
        "election_year", "election_date", "reference_candidate", "opponent_candidate",
        "reference_votes", "opponent_votes", "total_valid_votes",
        "reference_aliases", "opponent_aliases",
    }
    missing = required - set(d.columns)
    if missing:
        raise ValueError(f"results file missing columns: {sorted(missing)}")
    d["election_year"] = pd.to_numeric(d["election_year"], errors="raise").astype(int)
    d["election_date"] = pd.to_datetime(d["election_date"], errors="raise").dt.normalize()
    for c in ["reference_votes", "opponent_votes", "total_valid_votes"]:
        d[c] = pd.to_numeric(d[c], errors="raise").astype(float)
    if (d[["reference_votes", "opponent_votes", "total_valid_votes"]] <= 0).any().any():
        raise ValueError("results counts must be positive")
    if ((d["reference_votes"] + d["opponent_votes"]) > d["total_valid_votes"]).any():
        raise ValueError("pair votes exceed total valid votes")
    d["result_ref_share"] = d["reference_votes"] / d["total_valid_votes"]
    d["result_opp_share"] = d["opponent_votes"] / d["total_valid_votes"]
    d["result_pair_ilr"] = [pair_ilr(a, b) for a, b in zip(d["result_ref_share"], d["result_opp_share"])]
    return d.sort_values("election_year").reset_index(drop=True)


def download_snapshot(url: str, dest: str | Path) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    req = Request(url, headers={"User-Agent": "polling-bayes-br/1.0 historical calibration"})
    with urlopen(req, timeout=180) as r, open(dest, "wb") as f:  # noqa: S310 - fixed public data URL
        while True:
            chunk = r.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
    if dest.stat().st_size == 0:
        raise RuntimeError("downloaded historical poll snapshot is empty")
    return dest


def read_poll_snapshot(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    compression = "gzip" if path.suffix == ".gz" else "infer"
    d = pd.read_csv(path, compression=compression, low_memory=False)
    # Normalize a few historical aliases if an older snapshot is supplied.
    ren = {
        "pesquisa_id": "id_pesquisa",
        "cenario_id": "id_cenario",
        "voto_tipo": "tipo_voto",
        "candidato": "nome_candidato",
        "qtd_entrevistas": "quantidade_entrevistas",
        "data_pesquisa": "data",
    }
    d = d.rename(columns={k: v for k, v in ren.items() if k in d.columns and v not in d.columns})
    return d


def append_poll_supplement(polls: pd.DataFrame, path: str | Path | None) -> pd.DataFrame:
    """Append a small audited historical supplement when the public snapshot has a gap.

    The supplement must already use the Poder360-like columns consumed by this
    module. It is deliberately additive and is used only to fill documented
    source gaps; duplicate rows are removed on the natural poll/scenario/candidate key.
    """
    if path is None:
        return polls.copy()
    path = Path(path)
    if not path.exists():
        return polls.copy()
    extra = pd.read_csv(path, low_memory=False)
    if extra.empty:
        return polls.copy()
    out = pd.concat([polls, extra], ignore_index=True, sort=False)
    key = [c for c in ["ano", "turno", "id_pesquisa", "id_cenario", "instituto", "nome_candidato"] if c in out.columns]
    if key:
        out = out.drop_duplicates(key, keep="last")
    return out.reset_index(drop=True)


def _candidate_rows(g: pd.DataFrame) -> pd.DataFrame:
    if "condicao" not in g.columns:
        return g
    cond = _numeric(g["condicao"])
    # Poder360 documents candidate rows as condicao=0. If the field is entirely
    # missing/unparseable, do not silently discard everything.
    if cond.notna().any():
        return g[cond.eq(0)].copy()
    return g


def _scenario_candidates(g: pd.DataFrame) -> int:
    gg = _candidate_rows(g)
    return int(gg["nome_candidato"].astype(str).nunique())



def source_filter_diagnostics(polls: pd.DataFrame, results: pd.DataFrame) -> pd.DataFrame:
    """Audit source values before the fail-closed historical extraction.

    This is intentionally verbose enough to explain a missing election without
    relaxing filters merely to make the model run.
    """
    d = polls.copy()
    if "ano" not in d or "turno" not in d or "data" not in d:
        return pd.DataFrame()
    d["ano"] = pd.to_numeric(d["ano"], errors="coerce").astype("Int64")
    d["turno"] = pd.to_numeric(d["turno"], errors="coerce").astype("Int64")
    d["data"] = pd.to_datetime(d["data"], errors="coerce").dt.normalize()
    rows: list[dict] = []

    def add(year: int, stage: str, field: str, value: object, count: int) -> None:
        rows.append({"election_year": year, "stage": stage, "field": field,
                     "value": str(value), "count": int(count)})

    for res in results.itertuples(index=False):
        year = int(res.election_year)
        y0 = d[d["ano"].eq(year)].copy()
        add(year, "year", "rows", "all", len(y0))
        if y0.empty:
            continue
        cargo = y0.get("cargo", pd.Series("", index=y0.index)).map(_norm_text)
        y1 = y0[cargo.eq("PRESIDENTE") & y0["turno"].eq(1)].copy()
        add(year, "president_round1", "rows", "all", len(y1))
        for val, cnt in y0.get("cargo", pd.Series("", index=y0.index)).astype(str).value_counts().head(8).items():
            add(year, "year", "cargo", val, cnt)
        if y1.empty:
            continue
        if "sigla_uf" in y1:
            for val, cnt in y1["sigla_uf"].fillna("<NA>").astype(str).value_counts().head(12).items():
                add(year, "president_round1", "sigla_uf", val, cnt)
            uf = y1["sigla_uf"].fillna("").map(_norm_text)
            yn = y1[uf.isin(["", "BR", "BRASIL"])].copy()
        else:
            yn = y1
        add(year, "national", "rows", "all", len(yn))
        if "tipo" in yn:
            for val, cnt in yn["tipo"].fillna("<NA>").astype(str).value_counts().head(12).items():
                add(year, "national", "tipo", val, cnt)
            tipo = yn["tipo"].fillna("").map(_norm_text)
            has_stim = tipo.str.contains("ESTIMUL", regex=False)
            ys = yn[has_stim].copy() if has_stim.any() else yn.copy()
        else:
            ys = yn
        add(year, "stimulated_or_fallback", "rows", "all", len(ys))
        if not ys.empty and ys["data"].notna().any():
            add(year, "stimulated_or_fallback", "date_min", ys["data"].min().date().isoformat(), 1)
            add(year, "stimulated_or_fallback", "date_max", ys["data"].max().date().isoformat(), 1)
            for val, cnt in ys["data"].dropna().dt.strftime("%Y-%m-%d").value_counts().sort_index().tail(12).items():
                add(year, "stimulated_or_fallback", "recent_date", val, cnt)
        lo = pd.Timestamp(res.election_date) - pd.Timedelta(days=14)
        hi = pd.Timestamp(res.election_date)
        yw = ys[ys["data"].between(lo, hi, inclusive="both")].copy()
        add(year, "window14", "rows", "all", len(yw))
        if "nome_candidato" in yw:
            for val, cnt in yw["nome_candidato"].fillna("<NA>").astype(str).value_counts().head(30).items():
                add(year, "window14", "nome_candidato", val, cnt)
        if "tipo_voto" in yw:
            for val, cnt in yw["tipo_voto"].fillna("<NA>").astype(str).value_counts().head(10).items():
                add(year, "window14", "tipo_voto", val, cnt)
    return pd.DataFrame(rows)


def extract_window_errors(
    polls: pd.DataFrame,
    results: pd.DataFrame,
    window_days: int,
    default_n: float = 1200.0,
    design_effect: float = 1.5,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build one latest national first-round poll per institute/election.

    The target quantity is the leading pair log-ratio. This ratio is unchanged
    by converting total-vote shares to valid-vote shares, which removes one
    otherwise fragile historical harmonization step.
    """
    d = polls.copy()
    needed = {"ano", "cargo", "data", "instituto", "turno", "nome_candidato", "percentual"}
    missing = needed - set(d.columns)
    if missing:
        raise ValueError(f"poll snapshot missing columns: {sorted(missing)}")

    d["ano"] = pd.to_numeric(d["ano"], errors="coerce").astype("Int64")
    d["turno"] = pd.to_numeric(d["turno"], errors="coerce").astype("Int64")
    d["data"] = pd.to_datetime(d["data"], errors="coerce").dt.normalize()
    d["percentual"] = _numeric(d["percentual"])
    d["instituto"] = d["instituto"].astype(str).str.strip()

    cargo = d["cargo"].map(_norm_text)
    d = d[cargo.eq("PRESIDENTE") & d["turno"].eq(1)].copy()

    if "sigla_uf" in d.columns:
        uf = d["sigla_uf"].fillna("").map(_norm_text)
        d = d[uf.isin(["", "BR", "BRASIL"])].copy()

    if "tipo" in d.columns:
        tipo = d["tipo"].fillna("").map(_norm_text)
        has_stim = tipo.str.contains("ESTIMUL", regex=False)
        # If the source actually distinguishes stimulated polls, use them.
        if has_stim.any():
            d = d[has_stim].copy()

    d = d[d["data"].notna() & d["percentual"].gt(0) & d["instituto"].ne("")].copy()
    if d.empty:
        raise RuntimeError("no national first-round presidential polls after base filters")

    if "id_pesquisa" not in d.columns:
        d["id_pesquisa"] = np.arange(len(d)).astype(str)
    if "id_cenario" not in d.columns:
        d["id_cenario"] = ""
    if "tipo_voto" not in d.columns:
        d["tipo_voto"] = ""
    if "quantidade_entrevistas" not in d.columns:
        d["quantidade_entrevistas"] = np.nan
    if "margem_mais" not in d.columns:
        d["margem_mais"] = np.nan

    d["quantidade_entrevistas"] = _numeric(d["quantidade_entrevistas"])
    d["margem_mais"] = _numeric(d["margem_mais"])

    rows: list[dict] = []
    audit: list[dict] = []

    for res in results.itertuples(index=False):
        year = int(res.election_year)
        lo = pd.Timestamp(res.election_date) - pd.Timedelta(days=int(window_days))
        hi = pd.Timestamp(res.election_date)
        y = d[d["ano"].eq(year) & d["data"].between(lo, hi, inclusive="both")].copy()
        initial_rows = len(y)
        initial_polls = int(y["id_pesquisa"].astype(str).nunique()) if not y.empty else 0

        if y.empty:
            audit.append({
                "election_year": year, "window_days": int(window_days),
                "rows_in_window": 0, "polls_in_window": 0,
                "pair_scenarios": 0, "institutes_retained": 0,
            })
            continue

        y["is_ref"] = y["nome_candidato"].map(lambda x: _alias_match(x, res.reference_aliases))
        y["is_opp"] = y["nome_candidato"].map(lambda x: _alias_match(x, res.opponent_aliases))

        scenario_cols = ["id_pesquisa", "id_cenario"]
        candidates: list[dict] = []
        for (poll_id, scen_id), g in y.groupby(scenario_cols, dropna=False, sort=False):
            ref = g[g["is_ref"]]
            opp = g[g["is_opp"]]
            if len(ref) != 1 or len(opp) != 1:
                continue
            ref_pct = float(ref["percentual"].iloc[0])
            opp_pct = float(opp["percentual"].iloc[0])
            if not (0 < ref_pct <= 100 and 0 < opp_pct <= 100):
                continue
            candidate_rows = _candidate_rows(g)
            candidate_mass = float(candidate_rows["percentual"].sum())
            n_cand = _scenario_candidates(g)
            valid = _norm_text(g["tipo_voto"].iloc[0]).find("VALID") >= 0
            n_rep = float(pd.to_numeric(g["quantidade_entrevistas"], errors="coerce").median())
            moe = float(pd.to_numeric(g["margem_mais"], errors="coerce").median())
            institute = str(g["instituto"].iloc[0]).strip()
            date = pd.Timestamp(g["data"].iloc[0]).normalize()
            neff = _effective_n(n_rep, moe, default_n, design_effect)
            p_ref = ref_pct / 100.0
            p_opp = opp_pct / 100.0
            z_poll = pair_ilr(p_ref, p_opp)
            s2 = pair_ilr_sampling_var(p_ref, p_opp, neff)
            candidates.append({
                "election_year": year,
                "window_days": int(window_days),
                "election_date": pd.Timestamp(res.election_date).date().isoformat(),
                "poll_date": date.date().isoformat(),
                "days_before": int((pd.Timestamp(res.election_date) - date).days),
                "poll_id": str(poll_id),
                "scenario_id": str(scen_id),
                "pollster": institute,
                "vote_basis": str(g["tipo_voto"].iloc[0]),
                "n_reported": n_rep,
                "moe_pp": moe,
                "n_eff": neff,
                "n_candidate_rows": n_cand,
                "candidate_mass_pct": candidate_mass,
                "ref_candidate": str(res.reference_candidate),
                "opp_candidate": str(res.opponent_candidate),
                "ref_poll_pct": ref_pct,
                "opp_poll_pct": opp_pct,
                "ref_result_pct": 100.0 * float(res.result_ref_share),
                "opp_result_pct": 100.0 * float(res.result_opp_share),
                "poll_pair_ilr": z_poll,
                "result_pair_ilr": float(res.result_pair_ilr),
                "pair_error_ilr": z_poll - float(res.result_pair_ilr),
                "sampling_var_ilr": s2,
                "sampling_sd_ilr": math.sqrt(s2),
                "prefer_valid": int(valid),
            })

        cand = pd.DataFrame(candidates)
        if cand.empty:
            audit.append({
                "election_year": year, "window_days": int(window_days),
                "rows_in_window": initial_rows, "polls_in_window": initial_polls,
                "pair_scenarios": 0, "institutes_retained": 0,
            })
            continue

        # Deterministic scenario selection per poll: prefer published valid-vote
        # scenario, then the scenario with the broadest candidate support and
        # greatest coherent candidate mass; tie-break by scenario id.
        cand = cand.sort_values(
            ["poll_id", "prefer_valid", "n_candidate_rows", "candidate_mass_pct", "scenario_id"],
            ascending=[True, False, False, False, True],
            kind="stable",
        ).drop_duplicates("poll_id", keep="first")

        # One latest poll per institute avoids treating tracking releases as
        # independent evidence for a common election-level error.
        cand = cand.sort_values(
            ["pollster", "poll_date", "n_eff", "poll_id"],
            ascending=[True, False, False, True],
            kind="stable",
        ).drop_duplicates("pollster", keep="first")

        rows.extend(cand.to_dict("records"))
        audit.append({
            "election_year": year, "window_days": int(window_days),
            "rows_in_window": initial_rows, "polls_in_window": initial_polls,
            "pair_scenarios": int(len(candidates)),
            "institutes_retained": int(cand["pollster"].nunique()),
        })

    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.drop(columns=["prefer_valid"], errors="ignore").sort_values(
            ["window_days", "election_year", "pollster"]
        ).reset_index(drop=True)
    return out, pd.DataFrame(audit)


@dataclass
class HistoricalFit:
    free_mean: bool
    mu: float
    var_mu: float
    tau_e: float
    tau_h: float
    tau_p: float
    nll: float
    years: np.ndarray
    pollsters: np.ndarray
    y: np.ndarray
    sampling_var: np.ndarray
    V: np.ndarray
    chol: tuple[np.ndarray, bool]
    residual: np.ndarray
    Vinv_ones: np.ndarray | None


def _covariance(years: np.ndarray, pollsters: np.ndarray, sampling_var: np.ndarray,
                tau_e: float, tau_h: float, tau_p: float) -> np.ndarray:
    n = len(years)
    V = np.diag(np.asarray(sampling_var, float) + float(tau_p) ** 2)
    V += (years[:, None] == years[None, :]).astype(float) * float(tau_e) ** 2
    V += (pollsters[:, None] == pollsters[None, :]).astype(float) * float(tau_h) ** 2
    V = (V + V.T) / 2.0
    V.flat[:: n + 1] += 1e-10
    return V


def _profile_nll(log_scales: np.ndarray, y: np.ndarray, years: np.ndarray, pollsters: np.ndarray,
                 sampling_var: np.ndarray, free_mean: bool, details: bool = False):
    tau_e, tau_h, tau_p = np.exp(np.asarray(log_scales, float))
    try:
        V = _covariance(years, pollsters, sampling_var, tau_e, tau_h, tau_p)
        cf = cho_factor(V, lower=True, check_finite=False)
        Vinv_y = cho_solve(cf, y, check_finite=False)
        logdetV = 2.0 * float(np.log(np.diag(cf[0])).sum())
        if free_mean:
            one = np.ones(len(y), float)
            Vinv_one = cho_solve(cf, one, check_finite=False)
            B = float(one @ Vinv_one)
            if not (B > 0):
                raise FloatingPointError
            mu = float((one @ Vinv_y) / B)
            residual = y - mu
            quad = float(residual @ cho_solve(cf, residual, check_finite=False))
            nll = 0.5 * (logdetV + math.log(B) + quad + (len(y) - 1) * math.log(2 * math.pi))
            var_mu = 1.0 / B
        else:
            Vinv_one = None
            mu = 0.0
            var_mu = 0.0
            residual = y
            quad = float(y @ Vinv_y)
            nll = 0.5 * (logdetV + quad + len(y) * math.log(2 * math.pi))
        if not np.isfinite(nll):
            raise FloatingPointError
        if details:
            return nll, V, cf, mu, var_mu, residual, Vinv_one, tau_e, tau_h, tau_p
        return nll
    except (np.linalg.LinAlgError, FloatingPointError, ValueError):
        return None if details else 1e100


def fit_historical_model(df: pd.DataFrame, free_mean: bool = True) -> HistoricalFit:
    if len(df) < 6 or df["election_year"].nunique() < 2:
        raise ValueError("historical model needs at least two elections and six polls")
    y = pd.to_numeric(df["pair_error_ilr"], errors="raise").to_numpy(float)
    years = pd.to_numeric(df["election_year"], errors="raise").to_numpy(int)
    pollsters = df["pollster"].astype(str).map(_norm_text).to_numpy()
    sampling_var = pd.to_numeric(df["sampling_var_ilr"], errors="raise").to_numpy(float)
    if np.any(~np.isfinite(y)) or np.any(~np.isfinite(sampling_var)) or np.any(sampling_var <= 0):
        raise ValueError("invalid historical errors or sampling variances")

    starts = np.array([
        [0.03, 0.03, 0.03],
        [0.08, 0.05, 0.05],
        [0.15, 0.08, 0.08],
        [0.30, 0.05, 0.10],
    ])
    bounds = [(-8.0, 0.5)] * 3
    best = None
    for st in starts:
        res = minimize(
            _profile_nll, np.log(st),
            args=(y, years, pollsters, sampling_var, free_mean, False),
            method="L-BFGS-B", bounds=bounds,
            options={"maxiter": 500, "ftol": 1e-11},
        )
        if np.isfinite(res.fun) and (best is None or res.fun < best.fun):
            best = res
    if best is None:
        raise RuntimeError("historical variance-component optimization failed")
    det = _profile_nll(best.x, y, years, pollsters, sampling_var, free_mean, True)
    if det is None:
        raise RuntimeError("could not reconstruct historical fit")
    nll, V, cf, mu, var_mu, residual, Vinv_one, tau_e, tau_h, tau_p = det
    return HistoricalFit(
        free_mean=free_mean, mu=float(mu), var_mu=float(var_mu), tau_e=float(tau_e),
        tau_h=float(tau_h), tau_p=float(tau_p), nll=float(nll), years=years,
        pollsters=pollsters, y=y, sampling_var=sampling_var, V=V, chol=cf,
        residual=residual, Vinv_ones=Vinv_one,
    )


def _random_effect_posterior(fit: HistoricalFit, group: str, value: object) -> tuple[float, float]:
    if group == "election":
        mask = fit.years == int(value)
        tau2 = fit.tau_e ** 2
    elif group == "pollster":
        mask = fit.pollsters == _norm_text(value)
        tau2 = fit.tau_h ** 2
    else:
        raise ValueError(group)
    if not mask.any():
        return 0.0, tau2
    k = tau2 * mask.astype(float)
    Vinv_r = cho_solve(fit.chol, fit.residual, check_finite=False)
    mean = float(k @ Vinv_r)
    Vinv_k = cho_solve(fit.chol, k, check_finite=False)
    var = float(tau2 - k @ Vinv_k)
    if fit.free_mean and fit.Vinv_ones is not None:
        # Uncertainty in the fixed intercept propagates into random-effect prediction.
        one = np.ones(len(k), float)
        d = float(0.0 - k @ fit.Vinv_ones)
        var += d * d * fit.var_mu
    return mean, max(var, 1e-12)


def election_effects(fit: HistoricalFit) -> pd.DataFrame:
    """BLUPs for election-level common error with universal-kriging uncertainty."""
    rows = []
    one = np.ones(len(fit.y), float)
    Vinv_one = fit.Vinv_ones
    if fit.free_mean and Vinv_one is None:
        Vinv_one = cho_solve(fit.chol, one, check_finite=False)
    Vinv_r = cho_solve(fit.chol, fit.residual, check_finite=False)
    for year in sorted(set(fit.years)):
        mask = (fit.years == int(year)).astype(float)
        k = fit.tau_e ** 2 * mask
        b = float(k @ Vinv_r)
        Vinv_k = cho_solve(fit.chol, k, check_finite=False)
        base = max(float(fit.tau_e ** 2 - k @ Vinv_k), 0.0)
        if fit.free_mean:
            a = float(k @ Vinv_one)
            var_common = base + (1.0 - a) ** 2 * fit.var_mu
        else:
            var_common = base
        rows.append({
            "election_year": int(year),
            "mu_ilr": fit.mu,
            "election_re_ilr": b,
            "common_error_ilr": fit.mu + b,
            "common_error_sd_ilr": math.sqrt(max(var_common, 1e-12)),
        })
    return pd.DataFrame(rows)


def _fit_fixed_tau_e(df: pd.DataFrame, tau_e: float) -> HistoricalFit:
    """Fit nuisance pollster/poll scales with a fixed zero-mean election prior.

    This is used only for the current external-prior baseline in LOO, so the
    baseline is the same comparison target for the free- and zero-mean models.
    """
    if len(df) < 6 or df["election_year"].nunique() < 2:
        raise ValueError("historical baseline needs at least two elections and six polls")
    y = pd.to_numeric(df["pair_error_ilr"], errors="raise").to_numpy(float)
    years = pd.to_numeric(df["election_year"], errors="raise").to_numpy(int)
    pollsters = df["pollster"].astype(str).map(_norm_text).to_numpy()
    sampling_var = pd.to_numeric(df["sampling_var_ilr"], errors="raise").to_numpy(float)
    tau_e = max(float(tau_e), 1e-8)

    def nll(log_scales: np.ndarray, details: bool = False):
        tau_h, tau_p = np.exp(np.asarray(log_scales, float))
        try:
            V = _covariance(years, pollsters, sampling_var, tau_e, tau_h, tau_p)
            cf = cho_factor(V, lower=True, check_finite=False)
            Vinv_y = cho_solve(cf, y, check_finite=False)
            logdetV = 2.0 * float(np.log(np.diag(cf[0])).sum())
            val = 0.5 * (logdetV + float(y @ Vinv_y) + len(y) * math.log(2 * math.pi))
            if not np.isfinite(val):
                raise FloatingPointError
            if details:
                return val, V, cf, tau_h, tau_p
            return val
        except (np.linalg.LinAlgError, FloatingPointError, ValueError):
            return None if details else 1e100

    best = None
    for st in ([0.03, 0.03], [0.08, 0.05], [0.15, 0.10]):
        res = minimize(lambda z: nll(z, False), np.log(st), method="L-BFGS-B",
                       bounds=[(-8.0, 0.5)] * 2, options={"maxiter": 500, "ftol": 1e-11})
        if np.isfinite(res.fun) and (best is None or res.fun < best.fun):
            best = res
    if best is None:
        raise RuntimeError("fixed-tau baseline optimization failed")
    det = nll(best.x, True)
    if det is None:
        raise RuntimeError("could not reconstruct fixed-tau baseline fit")
    val, V, cf, tau_h, tau_p = det
    return HistoricalFit(
        free_mean=False, mu=0.0, var_mu=0.0, tau_e=tau_e, tau_h=float(tau_h),
        tau_p=float(tau_p), nll=float(val), years=years, pollsters=pollsters, y=y,
        sampling_var=sampling_var, V=V, chol=cf, residual=y.copy(), Vinv_ones=None,
    )


def _predict_holdout_vector(train: pd.DataFrame, hold: pd.DataFrame,
                            fit: HistoricalFit) -> tuple[np.ndarray, np.ndarray]:
    """Exact Gaussian plug-in predictive distribution for an omitted election.

    The held-out election has no election-level covariance with training rows,
    but institutes appearing in both sets share their pollster random effect.
    For a free intercept, the universal-kriging correction propagates uncertainty
    in the GLS estimate of ``mu``.
    """
    yt = fit.y
    yh_years = pd.to_numeric(hold["election_year"], errors="raise").to_numpy(int)
    yh_pollsters = hold["pollster"].astype(str).map(_norm_text).to_numpy()
    yh_sampling = pd.to_numeric(hold["sampling_var_ilr"], errors="raise").to_numpy(float)
    nh = len(hold)
    nt = len(train)

    # Held-out covariance: one common election shock plus pollster and poll noise.
    Vhh = np.diag(yh_sampling + fit.tau_p ** 2)
    Vhh += np.ones((nh, nh), float) * fit.tau_e ** 2
    Vhh += (yh_pollsters[:, None] == yh_pollsters[None, :]).astype(float) * fit.tau_h ** 2

    # Cross-covariance is only through recurring pollsters: the election is new.
    Vht = (yh_pollsters[:, None] == fit.pollsters[None, :]).astype(float) * fit.tau_h ** 2
    Vinv_r = cho_solve(fit.chol, fit.residual, check_finite=False)
    mean = np.full(nh, fit.mu, float) + Vht @ Vinv_r
    Vinv_Vth = cho_solve(fit.chol, Vht.T, check_finite=False)
    cov = Vhh - Vht @ Vinv_Vth

    if fit.free_mean:
        one_t = np.ones(nt, float)
        one_h = np.ones(nh, float)
        Vinv_one = fit.Vinv_ones
        if Vinv_one is None:
            Vinv_one = cho_solve(fit.chol, one_t, check_finite=False)
        d = one_h - Vht @ Vinv_one
        cov = cov + np.outer(d, d) * fit.var_mu

    cov = (cov + cov.T) / 2.0
    vals, vecs = np.linalg.eigh(cov)
    vals = np.clip(vals, 1e-12, None)
    cov = (vecs * vals) @ vecs.T
    return mean, cov


def _fixed_consensus_weights(hold: pd.DataFrame) -> np.ndarray:
    """Model-independent holdout consensus weights based only on sampling variance."""
    s2 = pd.to_numeric(hold["sampling_var_ilr"], errors="raise").to_numpy(float)
    w = 1.0 / np.maximum(s2, 1e-12)
    return w / w.sum()


def _baseline_ilr_sd_from_result(row: pd.Series, target_pp: float = 2.5) -> float:
    """Approximate current external-prior scale in the first ILR coordinate.

    Use a three-part composition (reference, opponent, all other valid votes) and
    the same isotropic-ILR calibration principle as the production model.
    """
    p1 = float(row["result_ref_share"])
    p2 = float(row["result_opp_share"])
    p3 = max(1.0 - p1 - p2, 1e-9)
    p = np.array([p1, p2, p3], float)
    p /= p.sum()
    H = np.array([
        [1 / math.sqrt(2), 1 / math.sqrt(6)],
        [-1 / math.sqrt(2), 1 / math.sqrt(6)],
        [0.0, -2 / math.sqrt(6)],
    ])
    J = (np.diag(p) - np.outer(p, p)) @ H
    rms = float(np.sqrt(np.mean(np.sum(J[:2, :] ** 2, axis=1))))
    return (float(target_pp) / 100.0) / max(rms, 1e-9)


def loo_by_election(df: pd.DataFrame, results: pd.DataFrame, free_mean: bool,
                    baseline_pp: float = 2.5) -> pd.DataFrame:
    """Whole-election leave-one-out validation on one fixed observable.

    The observable is a sampling-variance-weighted consensus of the held-out
    poll-minus-result ILR errors. Its weights and realized value do not depend on
    which model is being evaluated, making free-mean, zero-mean, and the current
    2.5 p.p. baseline directly comparable.
    """
    rows = []
    for year in sorted(df["election_year"].unique()):
        train = df[df["election_year"].ne(year)].copy().reset_index(drop=True)
        hold = df[df["election_year"].eq(year)].copy().reset_index(drop=True)
        if train["election_year"].nunique() < 2 or hold.empty:
            continue
        w = _fixed_consensus_weights(hold)
        yhold = pd.to_numeric(hold["pair_error_ilr"], errors="raise").to_numpy(float)
        observed = float(w @ yhold)
        observed_sampling_sd = math.sqrt(float(w @ np.diag(
            pd.to_numeric(hold["sampling_var_ilr"], errors="raise").to_numpy(float)
        ) @ w))

        fit = fit_historical_model(train, free_mean=free_mean)
        m, C = _predict_holdout_vector(train, hold, fit)
        pred_mean = float(w @ m)
        pred_var = float(w @ C @ w)
        pred_sd = math.sqrt(max(pred_var, 1e-12))
        z = (observed - pred_mean) / pred_sd
        logscore = float(norm.logpdf(observed, loc=pred_mean, scale=pred_sd))

        # Current production comparator: zero-centered common election error with
        # 2.5 p.p. marginal candidate scale, while nuisance house/poll dispersion
        # is estimated from training data under that fixed common-error scale.
        rr = results[results["election_year"].eq(year)].iloc[0]
        base_tau = _baseline_ilr_sd_from_result(rr, baseline_pp)
        base_fit = _fit_fixed_tau_e(train, base_tau)
        bm, BC = _predict_holdout_vector(train, hold, base_fit)
        base_mean = float(w @ bm)
        base_var = float(w @ BC @ w)
        base_sd = math.sqrt(max(base_var, 1e-12))
        base_logscore = float(norm.logpdf(observed, loc=base_mean, scale=base_sd))

        rows.append({
            "heldout_year": int(year),
            "model": "free_mean" if free_mean else "zero_mean",
            "n_holdout_pollsters": int(len(hold)),
            "observed_consensus_ilr": observed,
            "observed_sampling_sd_ilr": observed_sampling_sd,
            "pred_mean_ilr": pred_mean,
            "pred_sd_ilr": pred_sd,
            "z_error": z,
            "covered_80": abs(z) <= norm.ppf(0.90),
            "covered_95": abs(z) <= norm.ppf(0.975),
            "log_score": logscore,
            "baseline_2p5_pred_mean_ilr": base_mean,
            "baseline_2p5_pred_sd_ilr": base_sd,
            "baseline_2p5_log_score": base_logscore,
            "delta_log_score_vs_2p5": logscore - base_logscore,
            "train_tau_e_ilr": fit.tau_e,
            "train_tau_h_ilr": fit.tau_h,
            "train_tau_p_ilr": fit.tau_p,
            "train_mu_ilr": fit.mu,
        })
    return pd.DataFrame(rows)


def jackknife(df: pd.DataFrame, free_mean: bool = True) -> pd.DataFrame:
    rows = []
    for year in sorted(df["election_year"].unique()):
        train = df[df["election_year"].ne(year)].copy()
        fit = fit_historical_model(train, free_mean=free_mean)
        rows.append({
            "excluded_year": int(year),
            "model": "free_mean" if free_mean else "zero_mean",
            "mu_ilr": fit.mu,
            "mu_sd_ilr": math.sqrt(fit.var_mu),
            "tau_e_ilr": fit.tau_e,
            "tau_h_ilr": fit.tau_h,
            "tau_p_ilr": fit.tau_p,
        })
    return pd.DataFrame(rows)


def robust_location_sensitivity(effects: pd.DataFrame) -> pd.DataFrame:
    """Approximate robust second-stage sensitivity across election effects.

    This is deliberately diagnostic: six elections do not justify wiring a
    Student-t random-effect distribution into production. Measurement SDs are
    folded into the scale as sqrt(tau^2 + se_e^2).
    """
    x = effects["common_error_ilr"].to_numpy(float)
    se = effects["common_error_sd_ilr"].to_numpy(float)
    rows = []
    for dfree in [3, 4, 5, np.inf]:
        def nll(par):
            mu = float(par[0])
            tau = math.exp(float(par[1]))
            scale = np.sqrt(tau * tau + se * se)
            z = (x - mu) / scale
            if np.isinf(dfree):
                ll = norm.logpdf(z) - np.log(scale)
            else:
                ll = student_t.logpdf(z, df=dfree) - np.log(scale)
            return -float(np.sum(ll))
        x0 = np.array([float(np.median(x)), math.log(max(float(np.std(x)), 0.03))])
        res = minimize(nll, x0, method="L-BFGS-B", bounds=[(-1.5, 1.5), (-8.0, 0.5)])
        mu = float(res.x[0])
        tau = math.exp(float(res.x[1]))
        rows.append({
            "distribution": "Normal" if np.isinf(dfree) else f"Student-t({int(dfree)})",
            "df": None if np.isinf(dfree) else int(dfree),
            "mu_ilr": mu,
            "tau_ilr": tau,
            "nll": float(res.fun),
        })
    return pd.DataFrame(rows)


def _pair_margin_pp_from_ilr_shift(row: pd.Series, delta_z: float) -> float:
    """Translate a small first-balance ILR error into error in p_ref-p_opp (p.p.)."""
    p1 = float(row["result_ref_share"])
    p2 = float(row["result_opp_share"])
    # Shift only the first Helmert coordinate while holding the aggregate rest fixed.
    z0 = pair_ilr(p1, p2)
    ratio = math.exp(math.sqrt(2.0) * (z0 + float(delta_z)))
    pair_mass = p1 + p2
    q2 = pair_mass / (1.0 + ratio)
    q1 = pair_mass - q2
    return 100.0 * ((q1 - q2) - (p1 - p2))


def summarize_window(df: pd.DataFrame, results: pd.DataFrame, window_days: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    x = df[df["window_days"].eq(window_days)].copy()
    free = fit_historical_model(x, free_mean=True)
    zero = fit_historical_model(x, free_mean=False)

    fits = []
    rr_last = results.iloc[-1]
    for label, fit in [("free_mean", free), ("zero_mean", zero)]:
        fits.append({
            "window_days": int(window_days), "model": label, "n_polls": len(x),
            "n_elections": x["election_year"].nunique(), "n_pollsters": x["pollster"].nunique(),
            "mu_ilr": fit.mu, "mu_sd_ilr": math.sqrt(fit.var_mu),
            "tau_e_ilr": fit.tau_e, "tau_h_ilr": fit.tau_h, "tau_p_ilr": fit.tau_p,
            "reml_nll": fit.nll,
            "approx_mu_margin_pp_at_2022": _pair_margin_pp_from_ilr_shift(rr_last, fit.mu),
            "approx_tau_e_margin_pp_at_2022": abs(_pair_margin_pp_from_ilr_shift(rr_last, fit.tau_e)),
        })
    fits_df = pd.DataFrame(fits)

    eff = election_effects(free)
    eff["window_days"] = int(window_days)
    eff = eff.merge(results[["election_year", "result_ref_share", "result_opp_share"]], on="election_year", how="left")
    eff["common_error_margin_pp"] = eff.apply(lambda r: _pair_margin_pp_from_ilr_shift(r, r.common_error_ilr), axis=1)

    loo = pd.concat([
        loo_by_election(x, results, free_mean=True),
        loo_by_election(x, results, free_mean=False),
    ], ignore_index=True)
    loo["window_days"] = int(window_days)

    jk = jackknife(x, free_mean=True)
    jk["window_days"] = int(window_days)
    return fits_df, eff, loo, jk


def write_report(out: Path, fits: pd.DataFrame, effects: pd.DataFrame, loo: pd.DataFrame,
                 jack: pd.DataFrame, robust: pd.DataFrame, audit: pd.DataFrame) -> None:
    def md(df: pd.DataFrame, cols: list[str]) -> str:
        y = df[cols].copy()
        for c in y.select_dtypes(include=["float"]).columns:
            y[c] = y[c].map(lambda v: f"{v:.4f}" if pd.notna(v) else "")
        return y.to_markdown(index=False)

    primary = fits[fits["window_days"].eq(7)]
    loo7 = loo[loo["window_days"].eq(7)]
    jk7 = jack[jack["window_days"].eq(7)]
    eff7 = effects[effects["window_days"].eq(7)]
    lines = [
        "# Historical common polling error — experimental results", "",
        "> Experimental branch only. These numbers are not wired into the published nowcast.", "",
        "## Variance-component fits", "",
        md(fits, ["window_days", "model", "n_polls", "n_elections", "n_pollsters", "mu_ilr", "tau_e_ilr", "tau_h_ilr", "tau_p_ilr", "approx_mu_margin_pp_at_2022", "approx_tau_e_margin_pp_at_2022"]), "",
        "## 7-day election effects", "",
        md(eff7, ["election_year", "common_error_ilr", "common_error_sd_ilr", "common_error_margin_pp"]), "",
        "## 7-day leave-one-election-out", "",
        md(loo7, ["heldout_year", "model", "observed_consensus_ilr", "pred_mean_ilr", "pred_sd_ilr", "z_error", "covered_80", "covered_95", "delta_log_score_vs_2p5"]), "",
        "## 7-day jackknife of the free mean", "",
        md(jk7, ["excluded_year", "mu_ilr", "mu_sd_ilr", "tau_e_ilr", "tau_h_ilr", "tau_p_ilr"]), "",
        "## Robust second-stage sensitivity (7-day effects)", "",
        md(robust, ["distribution", "mu_ilr", "tau_ilr", "nll"]), "",
        "## Extraction audit", "",
        md(audit, ["window_days", "election_year", "rows_in_window", "polls_in_window", "pair_scenarios", "institutes_retained"]), "",
        "## Interpretation guardrails", "",
        "- A non-zero historical mean is not accepted merely because it fits all six elections.",
        "- 2022 influence is assessed by the `excluded_year=2022` jackknife row and the robust sensitivity table.",
        "- No time decay is used in this experiment, so 2022 does not receive extra weight for recency.",
        "- The current 2.5 p.p. prior remains production behavior until whole-election LOO supports a replacement.",
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="data/presidential_first_round_results.csv")
    ap.add_argument("--polls", default="data/cache/br_poder360_pesquisas_microdados.csv.gz")
    ap.add_argument("--polls-url", default=BASE_DOS_DADOS_URL)
    ap.add_argument("--supplement-2018", default="data/historical_2018_final_window.csv")
    ap.add_argument("--out", default="output_historical_error")
    ap.add_argument("--windows", default="3,7,14")
    ap.add_argument("--no-download", action="store_true")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    results = load_results(args.results)
    poll_path = Path(args.polls)
    if not poll_path.exists():
        if args.no_download:
            raise FileNotFoundError(poll_path)
        download_snapshot(args.polls_url, poll_path)
    polls = read_poll_snapshot(poll_path)
    polls = append_poll_supplement(polls, args.supplement_2018)
    source_diag = source_filter_diagnostics(polls, results)
    source_diag.to_csv(out / "historical_source_diagnostics.csv", index=False)

    windows = tuple(int(x.strip()) for x in args.windows.split(",") if x.strip())
    all_errors, audits = [], []
    for w in windows:
        e, a = extract_window_errors(polls, results, w)
        all_errors.append(e)
        audits.append(a)
    errors = pd.concat(all_errors, ignore_index=True)
    audit = pd.concat(audits, ignore_index=True)
    if errors.empty:
        raise RuntimeError("historical extraction produced no usable polls")

    errors.to_csv(out / "historical_poll_errors.csv", index=False)
    audit.to_csv(out / "historical_extraction_audit.csv", index=False)

    fit_tables, eff_tables, loo_tables, jk_tables = [], [], [], []
    for w in windows:
        fw, ew, lw, jw = summarize_window(errors, results, w)
        fit_tables.append(fw); eff_tables.append(ew); loo_tables.append(lw); jk_tables.append(jw)
    fits = pd.concat(fit_tables, ignore_index=True)
    effects = pd.concat(eff_tables, ignore_index=True)
    loo = pd.concat(loo_tables, ignore_index=True)
    jack = pd.concat(jk_tables, ignore_index=True)

    robust = robust_location_sensitivity(effects[effects["window_days"].eq(7)])
    robust["window_days"] = 7

    fits.to_csv(out / "historical_fit_summary.csv", index=False)
    effects.to_csv(out / "historical_election_effects.csv", index=False)
    loo.to_csv(out / "historical_loo.csv", index=False)
    jack.to_csv(out / "historical_jackknife.csv", index=False)
    robust.to_csv(out / "historical_robust_sensitivity.csv", index=False)
    write_report(out / "historical_error_report.md", fits, effects, loo, jack, robust, audit)

    manifest = {
        "source": args.polls_url,
        "supplement_2018": args.supplement_2018 if Path(args.supplement_2018).exists() else None,
        "windows": list(windows),
        "years": sorted(int(x) for x in errors["election_year"].unique()),
        "primary_window_days": 7,
        "production_nowcast_modified": False,
        "time_decay": False,
        "robust_student_t": "diagnostic only",
    }
    (out / "historical_error_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(fits.to_string(index=False))
    print("\n7-day election effects:")
    print(effects[effects["window_days"].eq(7)].to_string(index=False))
    print("\n7-day LOO:")
    print(loo[loo["window_days"].eq(7)].to_string(index=False))


if __name__ == "__main__":
    main()