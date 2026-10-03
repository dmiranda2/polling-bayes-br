from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def _finish(ax, title: str, subtitle: str, ylabel: str, legend=True):
    ax.set_ylabel(ylabel)
    ax.set_xlabel("Data")
    ax.set_title(title, loc="left", fontsize=15, fontweight="bold", pad=25)
    ax.text(0.0, 1.015, subtitle, transform=ax.transAxes, fontsize=9, va="bottom")
    ax.grid(axis="y", alpha=0.18)
    if legend:
        ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1.0), frameon=False, fontsize=9)


def plot_trajectory(df: pd.DataFrame, candidates: list[str], out: str | Path, title: str, subtitle: str):
    gdf = df[df["candidate"].isin(candidates)].copy()
    if gdf.empty:
        return
    fig, ax = plt.subplots(figsize=(11, 6))
    for cand in candidates:
        g = gdf[gdf["candidate"] == cand].sort_values("date")
        if g.empty:
            continue
        ax.plot(g["date"], g["median_pct"], label=cand, linewidth=2)
        if {"lower_80_pct", "upper_80_pct"}.issubset(g.columns):
            ax.fill_between(g["date"], g["lower_80_pct"], g["upper_80_pct"], alpha=0.10)
    _finish(ax, title, subtitle, "Votos válidos estimados (%)")
    fig.tight_layout(rect=[0, 0, 0.80, 1])
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=190, bbox_inches="tight")
    plt.close(fig)


def plot_backtest(metrics: pd.DataFrame, out: str | Path):
    if metrics.empty:
        return
    fig, ax = plt.subplots(figsize=(9, 5.5))
    for year, g in metrics.groupby("election_year"):
        g = g.sort_values("days_before", ascending=False)
        ax.plot(g["days_before"], g["mae_pp"], marker="o", linewidth=2, label=str(int(year)))
    ax.invert_xaxis()
    ax.set_xlabel("Dias antes do 1º turno")
    ax.set_ylabel("Erro absoluto médio (p.p.)")
    ax.set_title("Backtest temporal — erro do nowcast antes da votação", loc="left", fontsize=15, fontweight="bold", pad=25)
    ax.text(0.0, 1.015, "Cortes históricos sem acesso a pesquisas futuras • cinco candidatos mais votados", transform=ax.transAxes, fontsize=9, va="bottom")
    ax.grid(axis="y", alpha=0.18)
    ax.legend(title="Eleição", loc="upper left", bbox_to_anchor=(1.02, 1.0), frameon=False)
    fig.tight_layout(rect=[0, 0, 0.82, 1])
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=190, bbox_inches="tight")
    plt.close(fig)


def generate_plots(trajectory: pd.DataFrame, top5: pd.DataFrame, out_dir: str | Path, as_of: str, backtest_metrics: pd.DataFrame | None = None, pair_current: pd.DataFrame | None = None):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    t = trajectory.copy()
    t["date"] = pd.to_datetime(t["date"])
    names = list(top5["candidate"])
    plot_trajectory(
        t, names, out / "nowcast_top5.png",
        "Votos válidos estimados — 1º turno",
        f"Nowcast bayesiano em votos válidos • atualização {as_of} • faixa sombreada: IC 80% da média latente das pesquisas",
    )

    pair_source = pair_current if pair_current is not None and not pair_current.empty else top5
    pair_names = list(pair_source["candidate"])
    lula = "Lula" if "Lula" in pair_names else None
    bol_rows = pair_source[pair_source["candidate"].astype(str).str.contains("Bolsonaro", case=False, na=False)].sort_values("median_pct", ascending=False)
    bolsonaro = bol_rows.iloc[0]["candidate"] if not bol_rows.empty else None
    pair = [x for x in [lula, bolsonaro] if x]
    if pair:
        label = " × ".join(pair)
        plot_trajectory(
            t, pair, out / "nowcast_lula_bolsonaro.png",
            f"{label} — trajetória em votos válidos",
            f"Nowcast bayesiano em votos válidos • atualização {as_of} • faixa sombreada: IC 80% da média latente das pesquisas",
        )

    if backtest_metrics is not None and not backtest_metrics.empty:
        plot_backtest(backtest_metrics, out / "backtest_temporal.png")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--trajectory", default="output/nowcast_trajectory.csv")
    p.add_argument("--latest", default="output/nowcast_latest.csv")
    p.add_argument("--out-dir", default="output")
    p.add_argument("--as-of", default=None)
    p.add_argument("--backtest", default="output/backtest_metrics.csv")
    args = p.parse_args()
    tr = pd.read_csv(args.trajectory, parse_dates=["date"])
    latest = pd.read_csv(args.latest)
    bt_path = Path(args.backtest)
    bt = pd.read_csv(bt_path) if bt_path.exists() else pd.DataFrame()
    as_of = args.as_of or str(pd.to_datetime(tr["date"]).max().date())
    generate_plots(tr, latest, args.out_dir, as_of, bt, latest)


if __name__ == "__main__":
    main()