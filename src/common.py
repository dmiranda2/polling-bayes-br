from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

CANONICAL_COLUMNS = [
    "election_year", "round", "poll_id", "pollster", "pollster_source",
    "pollster_cnpj", "pollster_registered_name", "pollster_key", "field_start", "field_end", "publish_date",
    "method", "scenario", "candidate", "pct", "pct_valid", "manual_override", "vote_basis",
    "n", "moe", "source_url", "source"
]


def _ascii(s: object) -> str:
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return ""
    s = str(s).strip()
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normalize_registration(s: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", _ascii(s).upper())


def _pollster_alias_table() -> dict[str, str]:
    """Load the auditable raw-label -> canonical pollster identity table.

    Only exact aliases, documented rebrands/successions and publisher/fieldwork
    partner labels belong here. Similar-looking institute names are deliberately
    *not* merged without evidence (e.g. Ipespe and Ibespe; Ibope and Ipec).
    """
    path = Path(__file__).resolve().parent.parent / "data" / "pollster_aliases.csv"
    if not path.exists():
        return {}
    tab = pd.read_csv(path, dtype=str).fillna("")
    return {_ascii(a).upper(): c.strip() for a, c in zip(tab["alias"], tab["canonical"]) if str(c).strip()}


_POLLSTER_ALIASES = _pollster_alias_table()


def normalize_pollster(s: object) -> str:
    raw = str(s).strip() if s is not None else ""
    key = _ascii(raw).upper()
    return _POLLSTER_ALIASES.get(key, raw)


def is_primary_pollster(s: object) -> bool:
    """False for aggregators/derived series that would double-count polls."""
    x = _ascii(s).upper()
    return not (x.startswith("AGREGADOR ") or x in {"AGREGADOR", "MEDIA DE PESQUISAS"})


def normalize_candidate(s: object) -> str:
    raw = str(s).strip() if s is not None else ""
    x = _ascii(raw).upper()
    # Deliberately conservative: people are never merged merely because they
    # share a surname or political family.
    patterns = [
        (r"^LULA(?:\b| \()|LUIZ INACIO LULA", "Lula"),
        (r"JAIR .*BOLSONARO|^JAIR BOLSONARO", "Jair Bolsonaro"),
        (r"FLAVIO .*BOLSONARO|^FLAVIO BOLSONARO", "Flávio Bolsonaro"),
        (r"FERNANDO .*HADDAD|^HADDAD", "Fernando Haddad"),
        (r"CIRO .*GOMES|^CIRO", "Ciro Gomes"),
        (r"SIMONE .*TEBET|^TEBET", "Simone Tebet"),
        (r"GERALDO .*ALCKMIN|^ALCKMIN", "Geraldo Alckmin"),
        (r"JOAO .*AMOEDO|^AMOEDO", "João Amoêdo"),
        (r"MARINA .*SILVA|^MARINA", "Marina Silva"),
        (r"HENRIQUE .*MEIRELLES|^MEIRELLES", "Henrique Meirelles"),
        (r"RONALDO .*CAIADO|^RONALDO CAIADO|^CAIADO", "Ronaldo Caiado"),
        (r"ROMEU .*ZEMA|^ROMEU ZEMA|^ZEMA", "Romeu Zema"),
        (r"RENAN .*SANTOS|^RENAN SANTOS", "Renan Santos"),
        (r"AUGUSTO .*CURY|^AUGUSTO CURY", "Augusto Cury"),
        (r"RUI COSTA PIMENTA|^RUI PIMENTA", "Rui Costa Pimenta"),
        (r"SAMARA .*MARTINS|^SAMARA", "Samara Martins"),
        (r"HERTZ .*DIAS|^HERTZ", "Hertz Dias"),
        (r"EDMILSON .*COSTA|^EDMILSON COSTA", "Edmilson Costa"),
        (r"WILSON .*GRASSI|^WILSON GRASSI", "Wilson Grassi"),
        (r"CLARIANA .*BARAO|^CLARIANA", "Clariana Barão"),
    ]
    for pat, val in patterns:
        if re.search(pat, x):
            return val
    # Remove party suffixes such as " (PT)" but preserve the person's name.
    return re.sub(r"\s*\([^)]{1,12}\)\s*$", "", raw).strip()


def normalize_method(s: object) -> str:
    x = _ascii(s).lower()
    flags = []
    if any(k in x for k in ["internet", "online", "web"]):
        flags.append("online")
    if any(k in x for k in ["telefone", "telefon", "catI".lower(), "ivr"]):
        flags.append("telefone")
    if any(k in x for k in ["presencial", "face a face", "domiciliar", "ponto de fluxo", "fluxo"]):
        flags.append("presencial")
    flags = list(dict.fromkeys(flags))
    if len(flags) > 1:
        return "misto"
    if flags:
        return flags[0]
    return "desconhecido"


def normalize_cnpj(s: object) -> str:
    """Normalize a Brazilian CNPJ without manufacturing identities from junk.

    CSV readers may turn a 14-digit identifier into an integral float, and a
    leading-zero CNPJ may arrive with 12 or 13 digits.  We restore at most two
    lost leading zeros; shorter numeric strings are rejected instead of being
    padded into a plausible-looking CNPJ.
    """
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return ""
    raw = str(s).strip()
    if not raw or raw.lower() in {"nan", "none", "#nulo#", "null"}:
        return ""
    try:
        if isinstance(s, (int, np.integer)):
            digits = str(int(s))
        elif isinstance(s, (float, np.floating)) and np.isfinite(s) and float(s).is_integer():
            digits = str(int(round(float(s))))
        elif re.fullmatch(r"[0-9]+(?:\.0+)?", raw):
            digits = raw.split(".", 1)[0]
        elif re.fullmatch(r"[0-9]+(?:\.[0-9]+)?[eE][+-]?[0-9]+", raw):
            digits = str(int(round(float(raw))))
        else:
            digits = re.sub(r"[^0-9]", "", _ascii(raw))
    except (ValueError, OverflowError):
        digits = re.sub(r"[^0-9]", "", _ascii(raw))
    if len(digits) < 12 or len(digits) > 14:
        return ""
    return digits.zfill(14)

def _unique_cnpj_map(keys: pd.Series, cnpjs: pd.Series) -> dict[str, str]:
    """Return key -> CNPJ only where the observed mapping is unambiguous."""
    tmp = pd.DataFrame({"key": keys.astype(str), "cnpj": cnpjs.astype(str)})
    tmp = tmp[tmp["cnpj"].str.len().eq(14) & tmp["key"].ne("")]
    if tmp.empty:
        return {}
    grouped = tmp.groupby("key")["cnpj"].agg(lambda x: sorted(set(x)))
    return {k: vals[0] for k, vals in grouped.items() if len(vals) == 1}



def _survey_identity_key(df: pd.DataFrame) -> pd.Series:
    pid = df["poll_id"].astype(str).replace({"nan": "", "None": ""})
    fallback = (
        df["pollster_source"].astype(str) + "|"
        + pd.to_datetime(df["publish_date"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("") + "|"
        + pd.to_datetime(df["field_end"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    )
    year = pd.to_numeric(df["election_year"], errors="coerce").astype("Int64").astype(str)
    return year + "|" + np.where(pid.str.len().gt(0), pid, fallback)


def pollster_cnpj_conflicts(
    df: pd.DataFrame,
    min_dominant_polls: int = 3,
    min_dominant_share: float = 0.80,
) -> pd.DataFrame:
    """Find suspicious CNPJ↔pollster associations from internal consistency.

    A CNPJ is treated as having a dominant owner only when it appears in at
    least ``min_dominant_polls`` distinct surveys and at least
    ``min_dominant_share`` of its observed surveys use the same canonical
    institute label.  Isolated contradictory labels are then reported.

    This catches bad TSE-registration numbers supplied by secondary sources
    without requiring a hand-written blacklist.
    """
    if df.empty:
        return pd.DataFrame()
    d = df.copy()
    if "pollster_source" not in d.columns:
        d["pollster_source"] = d.get("pollster", "")
    for c in ["poll_id", "publish_date", "field_end", "election_year", "source_url"]:
        if c not in d.columns:
            d[c] = np.nan
    d["pollster"] = d["pollster"].map(normalize_pollster)
    d["pollster_cnpj"] = d.get("pollster_cnpj", "").map(normalize_cnpj)
    d["_survey_key"] = _survey_identity_key(d)

    known = d[d["pollster_cnpj"].str.len().eq(14)].copy()
    if known.empty:
        return pd.DataFrame()
    u = known[["pollster_cnpj", "pollster", "_survey_key"]].drop_duplicates()
    counts = (
        u.groupby(["pollster_cnpj", "pollster"])["_survey_key"].nunique()
        .reset_index(name="n_polls")
    )
    owners: dict[str, str] = {}
    for cnpj, g in counts.groupby("pollster_cnpj"):
        g = g.sort_values("n_polls", ascending=False)
        total = int(g["n_polls"].sum())
        top = g.iloc[0]
        if int(top["n_polls"]) >= min_dominant_polls and float(top["n_polls"]) / max(total, 1) >= min_dominant_share:
            owners[str(cnpj)] = str(top["pollster"])
    if not owners:
        return pd.DataFrame()

    d["dominant_pollster_for_cnpj"] = d["pollster_cnpj"].map(owners)
    bad = d[
        d["dominant_pollster_for_cnpj"].notna()
        & d["pollster"].ne(d["dominant_pollster_for_cnpj"])
    ].copy()
    if bad.empty:
        return pd.DataFrame()
    keep = [c for c in [
        "election_year", "poll_id", "pollster_source", "pollster", "pollster_cnpj",
        "dominant_pollster_for_cnpj", "pollster_registered_name", "publish_date", "source_url"
    ] if c in bad.columns]
    return bad[keep].drop_duplicates().sort_values(["pollster_cnpj", "election_year", "pollster"])

def resolve_pollster_cnpjs(df: pd.DataFrame) -> pd.DataFrame:
    """Fill missing pollster CNPJs only from unambiguous evidence in *df*.

    Resolution is deliberately conservative.  We prefer within-cycle evidence
    before cross-cycle evidence because a polling brand can change legal entity
    between elections.  The stages are:

    1. (election year, exact source label)
    2. (election year, canonical institute label)
    3. exact source label across all years
    4. canonical institute label across all years

    At every stage a value is filled only when the observed mapping is unique.
    Known CNPJs are never overwritten.
    """
    out = df.copy()
    out["pollster_cnpj"] = out["pollster_cnpj"].map(normalize_cnpj)

    # Remove internally inconsistent CNPJ assignments before using them as
    # identity evidence.  Secondary sources occasionally publish an incorrect
    # TSE registration number; blindly enriching that row would otherwise make
    # one institute inherit another institute's legal identity and history.
    conflicts = pollster_cnpj_conflicts(out)
    if not conflicts.empty:
        bad_pairs = set(zip(conflicts["pollster_cnpj"].astype(str), conflicts["pollster"].astype(str)))
        bad_mask = [
            (str(c), str(p)) in bad_pairs
            for c, p in zip(out["pollster_cnpj"], out["pollster"])
        ]
        out.loc[bad_mask, "pollster_cnpj"] = ""

    source_key = out["pollster_source"].map(lambda x: _ascii(x).upper())
    canonical_key = out["pollster"].map(lambda x: _ascii(x).upper())
    year_key = pd.to_numeric(out["election_year"], errors="coerce").astype("Int64").astype(str)

    stages = [
        year_key + "|" + source_key,
        year_key + "|" + canonical_key,
        source_key,
        canonical_key,
    ]
    for keys in stages:
        mapping = _unique_cnpj_map(keys, out["pollster_cnpj"])
        missing = out["pollster_cnpj"].eq("")
        inferred = keys.map(mapping).fillna("")
        use = missing & inferred.ne("")
        out.loc[use, "pollster_cnpj"] = inferred[use]

    return out


def pollster_identity_key(pollster: object, cnpj: object = "") -> str:
    cid = normalize_cnpj(cnpj)
    if len(cid) == 14:
        return f"CNPJ:{cid}"
    return f"NAME:{_ascii(normalize_pollster(pollster)).upper()}"


def parse_num(x: object) -> float:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return np.nan
    s = str(x).strip().replace("%", "").replace(" ", "")
    if not s or s.lower() in {"nan", "none", "na", "#nulo#"}:
        return np.nan
    if "," in s and "." in s:
        # Brazilian thousands + decimal separator, e.g. 1.234,5.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return np.nan


def response_kind(candidate: object) -> str:
    """Classify poll rows without confusing 'Outros candidatos' with invalid votes."""
    x = _ascii(candidate).lower().strip()
    if re.search(r"branco|nulo|indecis|nao sabe|nao respondeu|ns/nr|absten|nenhum", x):
        return "nonvalid"
    if x in {"outros", "outro", "outros candidatos", "demais candidatos"}:
        return "other_candidate"
    return "candidate"


def survey_key(df: pd.DataFrame) -> pd.Series:
    """Stable survey identity, including unregistered polls."""
    pid = df.get("poll_id", pd.Series("", index=df.index)).astype(str).replace({"nan": "", "None": "", "<NA>": ""})
    pollster = df.get("pollster_key", df.get("pollster", pd.Series("", index=df.index))).astype(str)
    start = pd.to_datetime(df.get("field_start"), errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    end = pd.to_datetime(df.get("field_end"), errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    pub = pd.to_datetime(df.get("publish_date"), errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    scenario = df.get("scenario", pd.Series("", index=df.index)).fillna("").astype(str)
    fallback = pollster + "|" + start + "|" + end + "|" + pub + "|" + scenario
    year = pd.to_numeric(df.get("election_year"), errors="coerce").astype("Int64").astype(str)
    rnd = pd.to_numeric(df.get("round"), errors="coerce").astype("Int64").astype(str)
    return year + "|" + rnd + "|" + np.where(pid.str.len().gt(0), pid, fallback)

def coerce_canonical(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "pollster_source" not in out.columns:
        out["pollster_source"] = out.get("pollster", pd.Series(index=out.index, dtype=object))
    for c in CANONICAL_COLUMNS:
        if c not in out.columns:
            out[c] = np.nan
    out = out[CANONICAL_COLUMNS]
    for c in ["field_start", "field_end", "publish_date"]:
        out[c] = pd.to_datetime(out[c], errors="coerce", format="mixed")
    out["pct"] = pd.to_numeric(out["pct"], errors="coerce")
    out["pct_valid"] = pd.to_numeric(out["pct_valid"], errors="coerce")
    out["manual_override"] = out["manual_override"].astype("string").fillna("").str.lower().isin(["1", "true", "yes", "y"])
    out["n"] = pd.to_numeric(out["n"], errors="coerce")
    out["moe"] = pd.to_numeric(out["moe"], errors="coerce")
    out["round"] = pd.to_numeric(out["round"], errors="coerce").astype("Int64")
    out["election_year"] = pd.to_numeric(out["election_year"], errors="coerce").astype("Int64")
    # Aggregators are derived from underlying surveys and must never be treated
    # as independent field polls; doing so would double-count the same evidence.
    out = out[out["pollster_source"].map(is_primary_pollster)].copy()
    out["pollster"] = out["pollster"].map(normalize_pollster)
    out = resolve_pollster_cnpjs(out)
    out["pollster_key"] = [pollster_identity_key(p, c) for p, c in zip(out["pollster"], out["pollster_cnpj"])]
    out["candidate"] = out["candidate"].map(normalize_candidate)
    out["method"] = out["method"].map(normalize_method)
    # Midpoint is preferable to publication day as the measurement time.
    out["field_start"] = out["field_start"].fillna(out["field_end"])
    out["field_end"] = out["field_end"].fillna(out["field_start"])
    out["publish_date"] = out["publish_date"].fillna(out["field_end"])
    out = out[(out["pct"].between(0, 100, inclusive="both")) & out["candidate"].ne("")]
    return out.reset_index(drop=True)


def midpoint_date(start: pd.Series, end: pd.Series) -> pd.Series:
    start = pd.to_datetime(start)
    end = pd.to_datetime(end)
    return (start + (end - start) / 2).dt.normalize()


def ensure_dir(p: str | Path) -> Path:
    p = Path(p)
    p.mkdir(parents=True, exist_ok=True)
    return p