from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import requests

from common import (
    coerce_canonical,
    normalize_registration,
    normalize_method,
    parse_num,
)

MURAL_2026 = "https://muraldoscandidatos.com/dados/pesquisas-registradas.csv"
NEXO_2022_1T = "https://raw.githubusercontent.com/Nexo-Dados/pesquisas-presidenciais-2022/master/pesquisas_1t.csv"
NEXO_2022_2T = "https://raw.githubusercontent.com/Nexo-Dados/pesquisas-presidenciais-2022/master/pesquisas_2t.csv"
PINDOGRAMA_P360 = "https://raw.githubusercontent.com/pindograma/pesquisas/master/data/poder360/all.csv"
TSE_CKAN = "https://dadosabertos.tse.jus.br/api/3/action/package_show?id=pesquisas-eleitorais-{year}"


def _download(url: str, timeout: int = 90) -> bytes:
    r = requests.get(url, timeout=timeout, headers={"User-Agent": "polling-bayes-br/0.1"})
    r.raise_for_status()
    return r.content


def _unwrap_tabular_archive(content: bytes) -> bytes:
    """Return the CSV/TXT payload when a provider serves it inside a ZIP.

    The TSE CKAN catalogue labels the polling resources as CSV, but the
    download URLs currently serve ZIP archives.  Reading those bytes directly
    with pandas produces misleading delimiter/quote parser errors.
    """
    if not content.startswith(b"PK"):
        return content

    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        members = [
            name for name in zf.namelist()
            if not name.endswith("/") and Path(name).suffix.lower() in {".csv", ".txt"}
        ]
        if not members:
            raise RuntimeError(f"ZIP contains no CSV/TXT file: {zf.namelist()}")

        # A TSE resource normally contains one table.  If that ever changes,
        # prefer the largest tabular member (usually the primary dataset).
        member = max(members, key=lambda name: zf.getinfo(name).file_size)
        return zf.read(member)


def _read_csv_bytes(content: bytes, **kwargs) -> pd.DataFrame:
    content = _unwrap_tabular_archive(content)
    last = None

    # If the caller supplied a separator, respect it first.  Otherwise try the
    # delimiters used by TSE and the other sources before pandas auto-detection.
    if "sep" in kwargs:
        attempts = [dict(kwargs)]
    else:
        attempts = [
            {**kwargs, "sep": ";"},
            {**kwargs, "sep": ","},
            {**kwargs, "sep": "\t"},
            {**{k: v for k, v in kwargs.items() if k != "low_memory"}, "sep": None, "engine": "python"},
        ]

    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        for opts in attempts:
            try:
                df = pd.read_csv(io.BytesIO(content), encoding=enc, **opts)
                # Reject a false-success where the whole row became one column.
                if len(df.columns) == 1 and opts.get("sep") in {";", ",", "\t"}:
                    continue
                return df
            except Exception as exc:  # pragma: no cover - fallback path
                last = exc
    raise last




def _parse_date_series(values: pd.Series) -> pd.Series:
    """Parse provider dates without ambiguous dayfirst warnings.

    TSE files mix ISO timestamps (YYYY-MM-DD HH:MM:SS) with occasional
    Brazilian day-first strings. Parse ISO explicitly and use day-first only
    for the remaining rows.
    """
    x = values.astype("string").str.strip()
    out = pd.Series(pd.NaT, index=values.index, dtype="datetime64[ns]")
    iso = x.str.match(r"^\d{4}-\d{2}-\d{2}(?:[ T].*)?$", na=False)
    if iso.any():
        out.loc[iso] = pd.to_datetime(x.loc[iso], errors="coerce", format="mixed", yearfirst=True)
    other = ~iso & x.notna() & x.ne("")
    if other.any():
        out.loc[other] = pd.to_datetime(x.loc[other], errors="coerce", format="mixed", dayfirst=True)
    return out

def fetch_tse_registry(year: int) -> pd.DataFrame:
    """Fetch TSE survey registry metadata through the CKAN API.

    This dataset contains registration/methodology/sample metadata, not the
    candidate percentages themselves. We join it by the TSE registration id.
    """
    meta = requests.get(TSE_CKAN.format(year=year), timeout=60).json()
    if not meta.get("success"):
        raise RuntimeError(f"TSE CKAN package_show failed for {year}")
    resources = meta["result"]["resources"]
    candidates = []
    for r in resources:
        name = (r.get("name") or "").lower()
        fmt = (r.get("format") or "").lower()
        if fmt == "csv" and "pesquisas eleitorais" in name and "contrat" not in name and "pagant" not in name:
            candidates.append(r)
    if not candidates:
        raise RuntimeError(f"No primary TSE polling CSV found for {year}")
    # Prefer the most recently modified resource when CKAN exposes duplicates.
    res = sorted(candidates, key=lambda r: r.get("last_modified") or "", reverse=True)[0]
    raw = _download(res["url"])
    df = _read_csv_bytes(raw, low_memory=False)
    df.columns = [str(c).strip().upper() for c in df.columns]

    def col(*needles: str):
        for c in df.columns:
            u = c.upper()
            if all(n.upper() in u for n in needles):
                return c
        return None

    reg = col("IDENTIFICACAO", "PESQUISA") or col("REGISTRO")
    ncol = col("ENTREVIST")
    mcol = col("METODOLOG")
    start = col("INICIO", "PESQUISA")
    end = col("FIM", "PESQUISA")
    moe = col("MARGEM", "ERRO")
    cnpj = "NR_CNPJ_EMPRESA" if "NR_CNPJ_EMPRESA" in df.columns else col("CNPJ", "EMPRESA")
    fantasy = "NM_EMPRESA_FANTASIA" if "NM_EMPRESA_FANTASIA" in df.columns else col("EMPRESA", "FANTASIA")
    company = "NM_EMPRESA" if "NM_EMPRESA" in df.columns else None
    if reg is None:
        raise RuntimeError(f"Could not identify TSE registration column for {year}: {list(df.columns)}")

    out = pd.DataFrame({"registro_key": df[reg].map(normalize_registration)})
    out["n_tse"] = pd.to_numeric(df[ncol], errors="coerce") if ncol else np.nan
    out["method_tse"] = df[mcol].astype(str).map(normalize_method) if mcol else "desconhecido"
    out["field_start_tse"] = _parse_date_series(df[start]) if start else pd.NaT
    out["field_end_tse"] = _parse_date_series(df[end]) if end else pd.NaT
    out["moe_tse"] = df[moe].map(parse_num) if moe else np.nan
    out["pollster_cnpj_tse"] = df[cnpj].astype(str) if cnpj else ""
    if fantasy:
        out["pollster_name_tse"] = df[fantasy].astype(str)
    elif company:
        out["pollster_name_tse"] = df[company].astype(str)
    else:
        out["pollster_name_tse"] = ""
    out = out[out["registro_key"].ne("")].drop_duplicates("registro_key")
    return out


def _attach_tse(df: pd.DataFrame, year: int) -> pd.DataFrame:
    try:
        tse = fetch_tse_registry(year)
    except Exception as exc:
        print(f"[warn] TSE metadata unavailable for {year}: {exc}")
        return df
    out = df.copy()
    if "pollster_source" not in out.columns:
        out["pollster_source"] = out.get("pollster", "")
    if "pollster_cnpj" not in out.columns:
        out["pollster_cnpj"] = ""
    out["registro_key"] = out["poll_id"].map(normalize_registration)
    out = out.merge(tse, on="registro_key", how="left")
    out["n"] = out["n"].fillna(out["n_tse"])
    out["moe"] = out["moe"].fillna(out["moe_tse"])
    out["field_start"] = pd.to_datetime(out["field_start"], errors="coerce").fillna(out["field_start_tse"])
    out["field_end"] = pd.to_datetime(out["field_end"], errors="coerce").fillna(out["field_end_tse"])
    bad_method = out["method"].isna() | out["method"].astype(str).str.lower().isin(["", "nan", "desconhecido"])
    out.loc[bad_method, "method"] = out.loc[bad_method, "method_tse"]
    cnpj_tse = out.get("pollster_cnpj_tse", pd.Series("", index=out.index)).astype(str).replace({"nan": "", "None": ""})
    out["pollster_cnpj"] = out["pollster_cnpj"].astype(str).replace({"nan": "", "None": ""})
    out.loc[cnpj_tse.str.len().gt(0), "pollster_cnpj"] = cnpj_tse[cnpj_tse.str.len().gt(0)]
    name_tse = out.get("pollster_name_tse", pd.Series("", index=out.index)).astype(str).str.strip().replace({"nan": "", "None": ""})
    if "pollster_registered_name" not in out.columns:
        out["pollster_registered_name"] = ""
    out.loc[name_tse.str.len().gt(0), "pollster_registered_name"] = name_tse[name_tse.str.len().gt(0)]
    return out.drop(columns=[c for c in ["registro_key", "n_tse", "method_tse", "field_start_tse", "field_end_tse", "moe_tse", "pollster_cnpj_tse", "pollster_name_tse"] if c in out])


def _drop_malformed_poll_groups(df: pd.DataFrame) -> pd.DataFrame:
    """Drop whole poll/scenario groups when metadata are structurally impossible.

    This guards against source rows whose columns have shifted during upstream
    scraping (observed in the 2026-10-01/02 Datafolha entry, where a candidate
    percentage landed in the margin-of-error field). We deliberately use only
    hard structural checks, never political or outcome-based judgments.
    """
    if df.empty:
        return df
    d = df.copy()
    group_cols = [
        c for c in ["pollster", "field_start", "field_end", "publish_date", "scenario", "source_url"]
        if c in d.columns
    ]
    if not group_cols:
        return d

    bad_keys = []
    for key, g in d.groupby(group_cols, dropna=False, sort=False):
        moe = pd.to_numeric(g.get("moe"), errors="coerce")
        # Presidential polling margins well above 10 p.p. are not plausible here;
        # in practice this catches column-shift corruption while leaving missing
        # margins untouched.
        impossible_moe = moe.notna().any() and (moe.dropna() > 10).any()
        if impossible_moe:
            bad_keys.append(key if isinstance(key, tuple) else (key,))

    if not bad_keys:
        return d

    bad = pd.DataFrame(bad_keys, columns=group_cols)
    marker = d.merge(bad.assign(_malformed=True), on=group_cols, how="left")["_malformed"].eq(True)
    dropped = d.loc[marker.to_numpy()].copy()
    if not dropped.empty:
        summary = dropped[[c for c in ["pollster", "publish_date", "scenario", "source_url"] if c in dropped]].drop_duplicates()
        print(f"[warn] Dropping {len(dropped)} malformed 2026 source rows:")
        print(summary.to_string(index=False))
    return d.loc[~marker.to_numpy()].reset_index(drop=True)


def fetch_2026() -> pd.DataFrame:
    raw = _read_csv_bytes(_download(MURAL_2026))
    raw.columns = [str(c).strip().lower() for c in raw.columns]
    out = pd.DataFrame({
        "election_year": 2026,
        "round": raw["cenario"].astype(str).str.extract(r"([12])\s*[ºo]?\s*turno", expand=False),
        "poll_id": raw["registro_tse"],
        "pollster": raw["instituto"],
        "field_start": raw["data_campo_inicio"],
        "field_end": raw["data_campo_fim"],
        "publish_date": raw["data_divulgacao"],
        "method": raw["metodologia"],
        "scenario": raw["cenario"],
        "candidate": raw["candidato"],
        "pct": raw["percentual"].map(parse_num),
        "n": np.nan,
        "moe": raw["margem_erro"].map(parse_num),
        "source_url": raw["url"],
        "source": "Mural dos Candidatos"
    })
    out = _drop_malformed_poll_groups(out)
    # Rejection-only and non-round rows have no percentage or no parsed round.
    out = out[out["round"].notna() & out["pct"].notna()].copy()
    out = _attach_tse(out, 2026)
    return coerce_canonical(out)


def _melt_nexo(url: str, round_no: int) -> pd.DataFrame:
    df = _read_csv_bytes(_download(url))
    id_cols = [c for c in ["Instituto", "Data", "Data divulgação", "Data Divulgação", "Registro"] if c in df.columns]
    value_cols = [c for c in df.columns if c not in id_cols and c not in {"VV13", "VV22"}]
    long = df.melt(id_vars=id_cols, value_vars=value_cols, var_name="candidate", value_name="pct")
    long["candidate"] = long["candidate"].replace({
        "Outros": "Outros candidatos",
        "BNI": "brancos/nulos/indecisos",
    })
    pub_col = "Data divulgação" if "Data divulgação" in long.columns else "Data Divulgação" if "Data Divulgação" in long.columns else None
    source_date = pd.to_datetime(long["Data"], errors="coerce")
    out = pd.DataFrame({
        "election_year": 2022,
        "round": round_no,
        "poll_id": long["Registro"],
        "pollster": long["Instituto"],
        # Let TSE metadata supply the actual field interval when available.
        "field_start": pd.NaT,
        "field_end": pd.NaT,
        "publish_date": long[pub_col] if pub_col else source_date,
        "method": "desconhecido",
        "scenario": f"{round_no}º turno",
        "candidate": long["candidate"],
        "pct": long["pct"],
        "n": np.nan,
        "moe": np.nan,
        "source_url": url,
        "source": "Nexo Dados",
        "_source_date": source_date,
    })
    out = out[out["pct"].notna()].copy()
    return out

def fetch_2022() -> pd.DataFrame:
    out = pd.concat([_melt_nexo(NEXO_2022_1T, 1), _melt_nexo(NEXO_2022_2T, 2)], ignore_index=True)
    source_date = pd.to_datetime(out.pop("_source_date"), errors="coerce")
    out = _attach_tse(out, 2022)
    out["field_start"] = pd.to_datetime(out["field_start"], errors="coerce").fillna(source_date)
    out["field_end"] = pd.to_datetime(out["field_end"], errors="coerce").fillna(source_date)
    return coerce_canonical(out)


def fetch_2018() -> pd.DataFrame:
    raw = _read_csv_bytes(_download(PINDOGRAMA_P360), sep=";", low_memory=False)
    cols = {c.lower(): c for c in raw.columns}

    def c(name: str):
        return cols.get(name.lower())

    mask = pd.Series(True, index=raw.index)
    if c("ano"):
        mask &= pd.to_numeric(raw[c("ano")], errors="coerce").eq(2018)
    elif c("data_pesquisa"):
        mask &= pd.to_datetime(raw[c("data_pesquisa")], errors="coerce").dt.year.eq(2018)
    if c("cargos_id"):
        mask &= pd.to_numeric(raw[c("cargos_id")], errors="coerce").eq(3)
    if c("ambito"):
        mask &= raw[c("ambito")].astype(str).str.upper().eq("BR")
    if c("tipo_id"):
        mask &= pd.to_numeric(raw[c("tipo_id")], errors="coerce").eq(2)  # estimulada
    # Keep every response category here.  In particular, blank/null/NS/NR rows
    # are evidence needed later to tell total-vote tables from valid-vote tables.
    # `to_valid_shares` is the sole place where non-candidate rows are excluded
    # from the modeled composition, after the vote basis has been classified.
    raw = raw[mask].copy()

    def series(name: str, default=np.nan):
        cc = c(name)
        return raw[cc] if cc else pd.Series(default, index=raw.index)

    out = pd.DataFrame({
        "election_year": 2018,
        "round": series("turno"),
        "poll_id": series("num_registro"),
        "pollster": series("instituto"),
        "field_start": pd.NaT,
        "field_end": pd.NaT,
        "publish_date": series("data_pesquisa"),
        "method": "desconhecido",
        "scenario": series("cenario_descricao", series("cenario_id", "principal")),
        "candidate": series("candidato"),
        "pct": series("percentual").map(parse_num),
        "n": pd.to_numeric(series("qtd_entrevistas"), errors="coerce"),
        "moe": series("margem_mais").map(parse_num),
        "source_url": PINDOGRAMA_P360,
        "source": "Poder360 via Pindograma"
    })
    source_date = pd.to_datetime(series("data_pesquisa"), errors="coerce")
    out = _attach_tse(out, 2018)
    out["field_start"] = pd.to_datetime(out["field_start"], errors="coerce").fillna(source_date)
    out["field_end"] = pd.to_datetime(out["field_end"], errors="coerce").fillna(source_date)
    return coerce_canonical(out)


def append_manual(auto: pd.DataFrame, manual_path: Path) -> pd.DataFrame:
    if not manual_path.exists() or manual_path.stat().st_size == 0:
        return auto
    man_raw = pd.read_csv(manual_path)
    if man_raw.empty:
        return auto
    man_raw["source"] = man_raw.get("source", "manual")
    man = coerce_canonical(man_raw)
    try:
        chunks = []
        for year, gy in man.groupby("election_year", dropna=True):
            chunks.append(_attach_tse(gy.copy(), int(year)))
        if chunks:
            man = pd.concat(chunks, ignore_index=True)
    except Exception as exc:
        print(f"[warn] TSE metadata unavailable for manual supplements: {exc}")

    # Explicit policy: automatic data normally wins, but a curated manual row can
    # declare manual_override=true when it is repairing a known malformed release.
    auto2 = auto.copy(); auto2["_dedup_rank"] = 1
    man2 = man.copy(); man2["_dedup_rank"] = np.where(man2["manual_override"].fillna(False).astype(bool), 2, 0)
    combined = pd.concat([auto2, man2], ignore_index=True)

    combined["_reg_key"] = combined["poll_id"].map(normalize_registration)
    regmask = combined["_reg_key"].ne("")
    key_reg = ["election_year", "round", "_reg_key", "scenario", "candidate"]
    registered = combined[regmask].sort_values("_dedup_rank").drop_duplicates(key_reg, keep="last")
    unregistered = combined[~regmask].copy()
    combined = pd.concat([registered, unregistered], ignore_index=True)

    combined["_field_start_key"] = pd.to_datetime(combined["field_start"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    combined["_field_end_key"] = pd.to_datetime(combined["field_end"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    key_fallback = ["election_year", "round", "pollster", "_field_start_key", "_field_end_key", "scenario", "candidate"]
    combined = combined.sort_values("_dedup_rank").drop_duplicates(key_fallback, keep="last")
    return combined.drop(columns=[
        "_dedup_rank", "_reg_key", "_field_start_key", "_field_end_key"
    ], errors="ignore").reset_index(drop=True)

def fetch_all(out_dir: str | Path, manual_2026: str | Path | None = None) -> pd.DataFrame:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    parts = []
    for year, fn in [(2018, fetch_2018), (2022, fetch_2022), (2026, fetch_2026)]:
        print(f"Fetching {year}...")
        df = fn()
        df.to_csv(out_dir / f"polls_{year}.csv", index=False)
        parts.append(df)
    all_df = pd.concat(parts, ignore_index=True)
    if manual_2026:
        all_df = append_manual(all_df, Path(manual_2026))
    all_df.to_csv(out_dir / "polls_master.csv", index=False)
    return all_df


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="data")
    p.add_argument("--manual-2026", default="data/manual_2026.csv")
    args = p.parse_args()
    fetch_all(args.out, args.manual_2026)