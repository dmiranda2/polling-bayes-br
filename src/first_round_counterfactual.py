"""A posteriori first-round historical directional bias experiment.

Uses only pre-2026 FIRST-ROUND historical polling and elections, and a dated
v0.9.1 first-round nowcast. Never called by the second-round pipeline.
NOT a reimplementation of the v0.8 quality-weighting model.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from historical_calibration import parse_window_range, window_label

VOTE_DATE = pd.Timestamp("2026-10-04")
PAIR = ("Lula", "Flávio Bolsonaro")


def load_history(directory: str | Path, window: str = "1:7", target_year: int = 2026) -> dict:
    folder = Path(directory)
    fit = pd.read_csv(folder / "historical_fit_summary.csv")
    loo = pd.read_csv(folder / "historical_loo.csv")
    err = pd.read_csv(folder / "historical_poll_errors.csv")
    for name, frame, cols in (
        ("fit", fit, {"election_round", "window_label", "model", "mu_ilr", "n_elections", "n_polls"}),
        ("LOO", loo, {"election_round", "window_label", "model", "heldout_year",
                      "log_score", "baseline_2p5_log_score"}),
        ("errors", err, {"election_round", "window_label", "election_year"}),
    ):
        if not cols <= set(frame.columns):
            raise ValueError(f"{name}: missing audit columns {sorted(cols - set(frame.columns))}")
        if not frame["election_round"].eq(1).all():
            raise ValueError(f"{name}: contains second-round or mixed-round data")
    if err["election_year"].ge(target_year).any():
        raise ValueError("Historical errors contain target/future election: look-ahead leakage")
    if loo["heldout_year"].ge(target_year).any():
        raise ValueError("Historical LOO contains target/future election: look-ahead leakage")
    selected = window_label(parse_window_range(window))
    f = fit[fit["window_label"].eq(selected)]
    l = loo[loo["window_label"].eq(selected)]
    e = err[err["window_label"].eq(selected)]
    if e.empty or len(f) != 2 or set(f["model"]) != {"free_mean", "zero_mean"}:
        raise ValueError("Historical fit for selected window is incomplete")
    free_fit = f.set_index("model").loc["free_mean"]
    if int(free_fit["n_elections"]) < 4 or int(free_fit["n_polls"]) < 12:
        raise ValueError("Not enough historical first-round observations")
    lf, l0 = l[l["model"].eq("free_mean")], l[l["model"].eq("zero_mean")]
    if (len(lf) < 4 or len(lf) != len(l0)
            or lf["heldout_year"].duplicated().any()
            or l0["heldout_year"].duplicated().any()
            or set(lf["heldout_year"]) != set(l0["heldout_year"])):
        raise ValueError("Historical LOO comparisons are not paired by election")
    mu = float(free_fit["mu_ilr"])
    if not math.isfinite(mu):
        raise ValueError("Historical mu is invalid")
    scores = {
        "free_mean": float(lf["log_score"].sum()),
        "zero_mean": float(l0["log_score"].sum()),
        "external_prior_2p5": float(lf["baseline_2p5_log_score"].sum()),
    }
    return {
        "mu_ilr": mu,
        "window": selected,
        "historical_years": sorted(int(y) for y in e["election_year"].unique()),
        "n_elections": int(free_fit["n_elections"]),
        "n_polls": int(free_fit["n_polls"]),
        "loo_log_scores": scores,
        "free_mean_wins_loo": bool(scores["free_mean"] > max(
            scores["zero_mean"], scores["external_prior_2p5"])),
    }


def load_nowcast(nowcast: str | Path, manifest: str | Path, as_of: str) -> pd.DataFrame:
    ts = pd.Timestamp(as_of).normalize()
    if ts >= VOTE_DATE:
        raise ValueError("PRE-ELECTION as-of date required, before 2026-10-04")
    info = json.loads(Path(manifest).read_text(encoding="utf-8"))
    if info.get("as_of") != ts.date().isoformat():
        raise ValueError("Nowcast manifest date differs from selected as-of")
    if info.get("historical_bias_transfer") is not False:
        raise ValueError("Baseline already bias-adjusted; refusing to double-correct")
    if info.get("model") != "joint_ilr_gaussian_reml_structured":
        raise ValueError("Baseline is not the documented v0.9.1 joint ILR model")
    d = pd.read_csv(nowcast)
    if not {"candidate", "median_pct"} <= set(d.columns):
        raise ValueError("Nowcast columns missing")
    if d["candidate"].duplicated().any() or not set(PAIR) <= set(d["candidate"]):
        raise ValueError("Exactly one Lula and one Flávio required in first-round nowcast")
    if "last_poll_date" in d:
        dates = pd.to_datetime(d["last_poll_date"], errors="coerce").dropna()
        if (dates > ts).any():
            raise ValueError("Nowcast includes a poll fielded after its as-of date")
    vals = pd.to_numeric(d["median_pct"], errors="raise")
    if not np.isfinite(vals.to_numpy(float)).all() or not vals.between(0, 100).all():
        raise ValueError("Invalid median percentages")
    d["median_pct"] = vals
    return d


def correct_pair(lula: float, flavio: float, mu_ilr: float) -> tuple[float, float]:
    mass = float(lula + flavio)
    if not (lula > 0 and flavio > 0 and mass <= 100.01):
        raise ValueError("Invalid Lula/Flávio pair shares")
    log_odds = math.log(lula / flavio) - math.sqrt(2) * mu_ilr
    share_l = 1 / (1 + math.exp(-log_odds))
    return mass * share_l, mass * (1 - share_l)


def compare(nowcast: str | Path, manifest: str | Path,
            history_dir: str | Path, as_of: str,
            window: str = "1:7") -> tuple[pd.DataFrame, dict]:
    base = load_nowcast(nowcast, manifest, as_of)
    hist = load_history(history_dir, window, int(as_of[:4]))
    v = base.set_index("candidate")["median_pct"]
    l, f = correct_pair(float(v.loc[PAIR[0]]), float(v.loc[PAIR[1]]), hist["mu_ilr"])
    out = base[["candidate", "median_pct"]].copy().rename(
        columns={"median_pct": "uncorrected_pct"})
    out["experimental_corrected_pct"] = out["uncorrected_pct"]
    out.loc[out["candidate"].eq(PAIR[0]), "experimental_corrected_pct"] = l
    out.loc[out["candidate"].eq(PAIR[1]), "experimental_corrected_pct"] = f
    out["delta_pp"] = out["experimental_corrected_pct"] - out["uncorrected_pct"]
    hist.update({
        "as_of": as_of, "round": 1,
        "status": "POST_ELECTION_EXPERIMENT_NOT_APPROVED_FOR_PRODUCTION",
        "base_model": "v0.9.1", "experimental": "v1_historical_error_free_mean",
        "is_v08_quality_weighted_model": False,
        "second_round_pipeline_modified": False,
        "caveat": "Retrospective reconstruction; improvement on 2026 alone cannot validate model.",
    })
    return out, hist


def write_report(table: pd.DataFrame, audit: dict, directory: str | Path) -> None:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = audit["as_of"]
    table.to_csv(directory / f"comparison_{stamp}.csv", index=False)
    (directory / f"audit_{stamp}.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8")
    ll = [
        f"# Primeiro turno de 2026 — contrafactual retrospectivo em {stamp}",
        "",
        "**EXPERIMENTO RECONSTRUÍDO DEPOIS DA ELEIÇÃO: NÃO É PREVISÃO ARQUIVADA.**",
        "",
        "A versão sem correção reproduz as medianas da v0.9.1. A versão corrigida",
        "transfere experimentalmente a média do erro de PRIMEIROS turnos históricos",
        "para a razão entre Lula e Flávio, mantendo a soma dos dois e todos os demais",
        "candidatos fixos. Não é a implementação exata da v0.8 (qualidade por instituto).",
        "**Nada deste experimento afeta o modelo de segundo turno.**",
        "",
        "| Candidato | Sem correção | Correção histórica experimental | Δ (p.p.) |",
        "|---|---:|---:|---:|",
    ]
    for name in PAIR:
        r = table[table["candidate"].eq(name)].iloc[0]
        ll.append(f"| {name} | {r.uncorrected_pct:.2f}% | "
                  f"{r.experimental_corrected_pct:.2f}% | {r.delta_pp:+.2f} |")
    s = audit["loo_log_scores"]
    ll += [
        "",
        f"Janela histórica: {audit['window']}; {audit['n_elections']} eleições e "
        f"{audit['n_polls']} pesquisas pré-2026. Média ILR: {audit['mu_ilr']:+.6f}.",
        "",
        "## Backtest por eleição inteira — somas dos logscores (maior é melhor)",
        "",
        "| Modelo histórico | Soma |",
        "|---|---:|",
        f"| Média livre experimental | {s['free_mean']:.3f} |",
        f"| Média zero | {s['zero_mean']:.3f} |",
        f"| Prior externo de 2,5 p.p. | {s['external_prior_2p5']:.3f} |",
        "",
        f"**A média livre superou ambos os controles? {'Sim' if audit['free_mean_wins_loo'] else 'Não'}.**",
        "",
        "A melhoria aparente no primeiro turno de 2026, observada a posteriori,",
        "não autoriza adotar esse viés em novas eleições. A reconstrução usa",
        "histórico anterior a 2026 e um nowcast datado, mas foi produzida após a urna.",
        "As medianas marginais do modelo composicional podem não somar exatamente 100%.",
        "Os dados dos demais candidatos permanecem disponíveis no CSV.",
    ]
    (directory / f"report_{stamp}.md").write_text(
        "\n".join(ll) + "\n", encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description="Experimental first-round bias counterfactual")
    p.add_argument("--nowcast", required=True)
    p.add_argument("--manifest", required=True)
    p.add_argument("--history-dir", required=True)
    p.add_argument("--as-of", required=True)
    p.add_argument("--window", default="1:7")
    p.add_argument("--out", default="output_first_round_counterfactual")
    a = p.parse_args()
    table, audit = compare(a.nowcast, a.manifest, a.history_dir, a.as_of, a.window)
    write_report(table, audit, a.out)
    print(table.to_string(index=False))
    print("Experimental only; historical free-mean passed LOO:", audit["free_mean_wins_loo"])


if __name__ == "__main__":
    main()
