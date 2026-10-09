"""Run a historical polling-error study for either presidential election round.

Each round is calibrated separately against the *same round's* election
result. Windows are inclusive day-offset intervals before polling day.
"""
from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

DEFAULT_WINDOWS = ("1:3", "1:7", "1:14", "14:21")
RESULT_PATHS = {
    1: "data/presidential_first_round_results.csv",
    2: "data/presidential_second_round_results.csv",
}
DEFAULT_OUTPUTS = {1: "output_historical_error", 2: "output_second_round_bias"}
SNAPSHOT_DEFAULT = "data/cache/br_poder360_pesquisas_microdados.csv.gz"


def parse_window_range(text: str) -> tuple[int, int]:
    """'1:7' includes days 1..7; '14:21' includes days 14..21 before election.

    Bare N is a backward-compatible shorthand for 1:N. Day 0 is forbidden.
    """
    raw = str(text).strip()
    parts = raw.split(":")
    try:
        if len(parts) == 1:
            near, far = 1, int(parts[0])
        elif len(parts) == 2:
            near, far = int(parts[0]), int(parts[1])
        else:
            raise ValueError
    except ValueError as exc:
        raise ValueError(f"Invalid window {text!r}; use e.g. 1:7 or 14:21") from exc
    if not (1 <= near <= far <= 120):
        raise ValueError(f"Historical window must satisfy 1 <= near <= far <= 120: {text!r}")
    return near, far


def parse_windows(text: str) -> list[tuple[int, int]]:
    windows = [parse_window_range(x) for x in str(text).split(",") if x.strip()]
    if not windows:
        raise ValueError("At least one historical window is required")
    return list(dict.fromkeys(windows))


def window_label(window: tuple[int, int]) -> str:
    return f"{window[0]}:{window[1]}"


def module_for_round(round_no: int):
    if round_no not in (1, 2):
        raise ValueError("Election round must be 1 or 2")
    return importlib.import_module("historical_error" if round_no == 1 else "historical_second_round")


def _mark_window(frame: pd.DataFrame, round_no: int, near: int, far: int) -> pd.DataFrame:
    out = frame.copy()
    out["election_round"] = int(round_no)
    out["window_min_days"] = int(near)
    out["window_days"] = int(far)
    out["window_label"] = f"{near}:{far}"
    return out


def calibrate_round(
    round_no: int,
    polls: pd.DataFrame,
    results: pd.DataFrame,
    windows: list[tuple[int, int]],
    out: str | Path,
    *,
    primary_window: tuple[int, int] | None = None,
) -> dict:
    """Save extraction audits even for windows without sufficient historical data."""
    module = module_for_round(round_no)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if round_no == 2:
        pair_votes = results["reference_votes"] + results["opponent_votes"]
        if not np.allclose(pair_votes, results["total_valid_votes"], rtol=0, atol=1):
            raise ValueError("Second-round results must contain exactly the two finalists")

    diag = module.source_filter_diagnostics(polls, results)
    diag.to_csv(out / "historical_source_diagnostics.csv", index=False)
    extracted, audits = [], []
    for near, far in windows:
        frame, audit = module.extract_window_errors(
            polls, results, far, min_days_before=near
        )
        extracted.append(_mark_window(frame, round_no, near, far))
        audits.append(_mark_window(audit, round_no, near, far))
    audit = pd.concat(audits, ignore_index=True)
    audit.to_csv(out / "historical_extraction_audit.csv", index=False)
    errors = pd.concat(extracted, ignore_index=True)
    errors.to_csv(out / "historical_poll_errors.csv", index=False)

    fitted: list[tuple[int, int]] = []
    skipped: list[str] = []
    fitted_tables: list[pd.DataFrame] = []
    effects_tables: list[pd.DataFrame] = []
    loo_tables: list[pd.DataFrame] = []
    jackknife_tables: list[pd.DataFrame] = []
    for near, far in windows:
        subset = errors[errors["window_label"].eq(f"{near}:{far}")]
        n_years = int(subset["election_year"].nunique()) if "election_year" in subset else 0
        if len(subset) < 6 or n_years < 3:
            skipped.append(f"{near}:{far}: {len(subset)} polls from {n_years} elections; cannot validate")
            continue
        # Passing only one window avoids accidentally pooling two windows with
        # the same end-day (e.g. 1:21 and 14:21) inside the legacy fit function.
        fw, ew, lw, jw = module.summarize_window(subset, results, far)
        for table in [fw, ew, lw, jw]:
            table["window_min_days"] = near
            table["window_days"] = far
            table["window_label"] = f"{near}:{far}"
            table["election_round"] = round_no
        fitted_tables.append(fw); effects_tables.append(ew)
        loo_tables.append(lw); jackknife_tables.append(jw)
        fitted.append((near, far))

    manifest = {
        "historical_round": round_no,
        "window_ranges_requested": [window_label(w) for w in windows],
        "window_ranges_fitted": [window_label(w) for w in fitted],
        "skipped_windows": skipped,
        "source": "Poder360/Base dos Dados snapshot plus audited first-round supplement if selected",
        "uses_election_day_polls": False,
        "rounds_pooled": False,
        "baseline_uses_holdout_result": False,
    }
    if not fitted:
        manifest["status"] = "no_fittable_window"
        (out / "historical_error_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        raise RuntimeError(
            f"No windows contain enough round-{round_no} historical observations. "
            f"See {out / 'historical_extraction_audit.csv'}"
        )

    if primary_window is None:
        primary_window = (1, 7) if (1, 7) in fitted else fitted[0]
    if primary_window not in fitted:
        raise ValueError(f"Primary window {window_label(primary_window)} has no estimable history")
    primary = window_label(primary_window)
    manifest["status"] = "completed"
    manifest["primary_window_range"] = primary

    fits = pd.concat(fitted_tables, ignore_index=True)
    effects = pd.concat(effects_tables, ignore_index=True)
    loo = pd.concat(loo_tables, ignore_index=True)
    jack = pd.concat(jackknife_tables, ignore_index=True)
    robust = module.robust_location_sensitivity(effects[effects["window_label"].eq(primary)])
    robust = _mark_window(robust, round_no, *primary_window)
    for name, table in [
        ("historical_fit_summary.csv", fits),
        ("historical_election_effects.csv", effects),
        ("historical_loo.csv", loo),
        ("historical_jackknife.csv", jack),
        ("historical_robust_sensitivity.csv", robust),
    ]:
        table.to_csv(out / name, index=False)
    (out / "historical_error_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    def md(table: pd.DataFrame, columns: list[str]) -> str:
        if table.empty:
            return "(sem observações)"
        return table[columns].to_markdown(index=False, floatfmt=".4f")

    primary_fits = fits[fits["window_label"].eq(primary)]
    primary_loo = loo[loo["window_label"].eq(primary)]
    lines = [
        f"# Erro histórico de pesquisas — {round_no}º turno", "",
        f"Janela principal: **{primary} dias antes da votação** (intervalo inclusivo).",
        "Primeiro e segundo turnos jamais são combinados no mesmo ajuste.", "",
        "## Variâncias e viés por janela", "",
        md(fits, ["window_label", "model", "n_polls", "n_elections", "mu_ilr",
                  "tau_e_ilr", "tau_h_ilr", "tau_p_ilr"]), "",
        f"## Validação leave-one-election-out — janela {primary}", "",
        md(primary_loo, ["heldout_year", "model", "pred_mean_ilr", "pred_sd_ilr",
                         "z_error", "covered_80", "covered_95", "delta_log_score_vs_2p5"]), "",
        f"## Viés e escala — janela {primary}", "",
        md(primary_fits, ["model", "mu_ilr", "mu_sd_ilr", "tau_e_ilr"]), "",
        "## Auditoria de disponibilidade", "",
        md(audit, ["window_label", "election_year", "rows_in_window",
                   "polls_in_window", "institutes_retained"]), "",
        "## Restrições", "",
        "- O dia da eleição é excluído (risco de exit polls).",
        "- As janelas não selecionadas para o ajuste principal são análises separadas.",
        "- O baseline LOO usa escala externa fixa, independente da eleição omitida.",
    ]
    if skipped:
        lines.extend(["", "Janelas sem ajuste:"] + [f"- {s}" for s in skipped])
    (out / "historical_error_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    p = argparse.ArgumentParser(description="Historical bias by election round and relative-date windows")
    p.add_argument("--round", "--turno", dest="turno", choices=("1", "2", "both"),
                   default="2", help="1, 2 or both (separate fits)")
    p.add_argument("--windows", "--window-ranges", dest="windows",
                   default=",".join(DEFAULT_WINDOWS),
                   help="e.g. 1:7,14:21 (near:far days BEFORE election; inclusive)")
    p.add_argument("--primary-window", default=None,
                   help="Primary historical window; default 1:7 if available")
    p.add_argument("--polls", default=SNAPSHOT_DEFAULT)
    p.add_argument("--polls-url", default=None)
    p.add_argument("--results", default=None,
                   help="Custom official results for a single round only")
    p.add_argument("--supplement-2018", default="data/historical_2018_final_window.csv")
    p.add_argument("--no-download", action="store_true")
    p.add_argument("--out", default=None)
    args = p.parse_args()

    windows = parse_windows(args.windows)
    primary = parse_window_range(args.primary_window) if args.primary_window else None
    turns = (1, 2) if args.turno == "both" else (int(args.turno),)
    if len(turns) > 1 and args.results:
        p.error("--results cannot be shared between round 1 and 2")

    source_module = module_for_round(1)
    poll_path = Path(args.polls)
    if not poll_path.exists():
        if args.no_download:
            raise FileNotFoundError(poll_path)
        source_module.download_snapshot(
            args.polls_url or source_module.BASE_DOS_DADOS_URL, poll_path
        )
    source_polls = source_module.read_poll_snapshot(poll_path)
    for turn in turns:
        module = module_for_round(turn)
        result_path = args.results or RESULT_PATHS[turn]
        if args.results:
            name = Path(args.results).name.lower()
            if (turn == 1 and "second_round" in name) or (turn == 2 and "first_round" in name):
                p.error("Official result CSV does not match selected round")
        results = module.load_results(result_path)
        polls = source_polls
        if turn == 1:
            polls = module.append_poll_supplement(source_polls, args.supplement_2018)
        target = (Path(args.out) / f"round_{turn}") if args.out and len(turns) > 1 else (
            Path(args.out) if args.out else Path(DEFAULT_OUTPUTS[turn])
        )
        manifest = calibrate_round(turn, polls, results, windows, target, primary_window=primary)
        print(f"Turno {turn}: {manifest['status']}; fitted {manifest['window_ranges_fitted']}; "
              f"primary {manifest['primary_window_range']}; output {target}")


if __name__ == "__main__":
    main()
