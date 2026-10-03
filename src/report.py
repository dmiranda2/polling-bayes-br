from __future__ import annotations

from pathlib import Path

import pandas as pd


def top_candidates(latest: pd.DataFrame, n: int = 5) -> tuple[pd.DataFrame, pd.DataFrame]:
    vv_all = latest.copy().sort_values("median_pct", ascending=False).reset_index(drop=True)
    ranked = vv_all[~vv_all["candidate"].eq("Outros candidatos")].copy()
    top = ranked.head(n).copy()
    top["position"] = range(1, len(top) + 1)
    return top, vv_all


def _fmt(x, digits=1):
    return "—" if pd.isna(x) else f"{float(x):.{digits}f}"


def _table(df: pd.DataFrame, columns: list[tuple[str, str, callable | None]]) -> str:
    headers = [label for _, label, _ in columns]
    rows = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for _, r in df.iterrows():
        vals = []
        for key, _, formatter in columns:
            v = r.get(key)
            vals.append(formatter(v) if formatter else str(v))
        rows.append("| " + " | ".join(vals) + " |")
    return "\n".join(rows)


def write_report(
    path: str | Path,
    top5: pd.DataFrame,
    as_of: str,
    backtest_metrics: pd.DataFrame | None = None,
    pair_current: pd.DataFrame | None = None,
    candidate_audit: pd.DataFrame | None = None,
    pollster_effect_audit: pd.DataFrame | None = None,
    external_error_prior: pd.DataFrame | None = None,
    model_hyperparameters: pd.DataFrame | None = None,
) -> None:
    path = Path(path)
    lines = [
        "# Pesquisas presidenciais — nowcast composicional",
        "",
        f"**Atualização:** {as_of}",
        "",
        "## Estimativa atual — cinco candidatos",
        "",
        "A tabela mostra a intenção de voto válida latente estimada diretamente pelo modelo conjunto. "
        "Pesquisas em votos totais são convertidas para a base válida antes do ajuste; "
        "o IC 80% é da média latente das pesquisas, não um intervalo do resultado eleitoral. "
        "A coluna final é apenas a distância dessa média latente ao limiar de 50%, não uma probabilidade de vitória nem uma projeção eleitoral.",
        "",
    ]
    columns = [
        ("candidate", "Candidato", None),
        ("median_pct", "Votos válidos estimados", lambda x: _fmt(x) + "%"),
        ("lower_80_pct", "IC 80% média latente inf.", lambda x: _fmt(x) + "%"),
        ("upper_80_pct", "IC 80% média latente sup.", lambda x: _fmt(x) + "%"),
        ("distance_to_50_pp", "Distância da média latente a 50%", lambda x: ("+" if float(x) >= 0 else "") + _fmt(x) + " p.p."),
        ("n_polls", "Pesquisas", lambda x: str(int(x)) if pd.notna(x) else "—"),
    ]
    lines.append(_table(top5, columns))

    pair_source = pair_current if pair_current is not None and not pair_current.empty else top5
    bol = pair_source[pair_source["candidate"].astype(str).str.contains("Bolsonaro", case=False, na=False)]
    lula = pair_source[pair_source["candidate"].astype(str).eq("Lula")]
    if not lula.empty or not bol.empty:
        lines += ["", "## Lula × Bolsonaro", ""]
        subset = pd.concat([lula, bol.head(1)], ignore_index=True).drop_duplicates("candidate")
        pair_cols = [
            ("candidate", "Candidato", None),
            ("median_pct", "Apoio estimado", lambda x: _fmt(x) + "%"),
            ("lower_80_pct", "IC 80% média latente inf.", lambda x: _fmt(x) + "%"),
            ("upper_80_pct", "IC 80% média latente sup.", lambda x: _fmt(x) + "%"),
        ]
        lines.append(_table(subset, pair_cols))

    if {"election_lower_80_pct", "election_upper_80_pct"}.issubset(top5.columns):
        lines += [
            "",
            "## Intervalo eleitoral sob hipótese externa",
            "",
            "Este segundo intervalo adiciona um termo de erro sistemático comum à indústria. "
            "Sua escala não é aprendida com 2018/2022: é um **prior externo**, mantido separado do IC da média latente. "
            "Portanto ele deve ser lido como análise de sensibilidade para o resultado eleitoral, não como calibração brasileira já identificada pelos dados.",
            "",
        ]
        lines.append(_table(top5, [
            ("candidate", "Candidato", None),
            ("median_pct", "Nowcast", lambda x: _fmt(x) + "%"),
            ("election_lower_80_pct", "Intervalo eleitoral 80% inf.", lambda x: _fmt(x) + "%"),
            ("election_upper_80_pct", "Intervalo eleitoral 80% sup.", lambda x: _fmt(x) + "%"),
        ]))
        if external_error_prior is not None and not external_error_prior.empty:
            r = external_error_prior.iloc[0]
            lines += [
                "",
                f"Escala externa configurada: **{_fmt(r.get('candidate_sd_pp'), 2)} p.p. de desvio-padrão marginal nos dois líderes**. "
                "A forma conjunta é induzida no simplex e não altera a média do nowcast.",
            ]

    if candidate_audit is not None and not candidate_audit.empty:
        excluded = candidate_audit[candidate_audit["action"].eq("excluded")].copy()
        if not excluded.empty:
            excluded = excluded.sort_values(["unique_polls", "candidate"], ascending=[False, True])
            lines += [
                "", "## Filtro da cédula", "",
                "Nomes fora da cédula presidencial vigente são excluídos depois que cada levantamento "
                "é convertido para a base de votos válidos; eles não viram zeros nem entram no nowcast atual.", "",
            ]
            lines.append(_table(excluded, [
                ("candidate", "Nome excluído", None),
                ("unique_polls", "Pesquisas", lambda x: str(int(x))),
                ("last_publish_date", "Última aparição", lambda x: str(pd.Timestamp(x).date()) if pd.notna(x) else "—"),
                ("reason", "Motivo", None),
            ]))

    if model_hyperparameters is not None and not model_hyperparameters.empty:
        lines += [
            "", "## Hiperparâmetros estimados", "",
            "A v0.9 elimina a transferência histórica e as penalidades manuais de novidade/overlap. "
            "As seis escalas abaixo são estimadas por verossimilhança marginal restrita (REML) em cada ajuste. "
            "O primeiro balanço ILR compara os dois líderes; os demais balanços compartilham uma segunda escala para evitar sobreparametrização.", "",
        ]
        lines.append(_table(model_hyperparameters, [
            ("rw_pair_sd_ilr_sqrt_day", "RW líderes", lambda x: _fmt(x, 4)),
            ("rw_field_sd_ilr_sqrt_day", "RW campo", lambda x: _fmt(x, 4)),
            ("house_pair_sd_ilr", "House líderes", lambda x: _fmt(x, 4)),
            ("house_field_sd_ilr", "House campo", lambda x: _fmt(x, 4)),
            ("poll_pair_sd_ilr", "Ruído líderes", lambda x: _fmt(x, 4)),
            ("poll_field_sd_ilr", "Ruído campo", lambda x: _fmt(x, 4)),
        ]))

    if pollster_effect_audit is not None and not pollster_effect_audit.empty:
        p = pollster_effect_audit.sort_values(["n_current_polls", "pollster"], ascending=[False, True]).head(20)
        lines += [
            "", "## Efeitos de instituto", "",
            "Todo instituto recebe o mesmo prior hierárquico de média zero, cuja dispersão é estimada. "
            "Casas novas não recebem penalidade ad hoc: com pouca informação, o próprio posterior as contrai mais fortemente para zero.", "",
        ]
        lines.append(_table(p, [
            ("pollster", "Instituto", None),
            ("n_current_polls", "Pesquisas", lambda x: str(int(x))),
            ("median_abs_house_effect_pp", "|efeito| mediano", lambda x: _fmt(x, 2) + " p.p."),
            ("max_abs_house_effect_pp", "|efeito| máx.", lambda x: _fmt(x, 2) + " p.p."),
        ]))

    if backtest_metrics is not None and not backtest_metrics.empty:
        lines += [
            "", "## Backtest temporal — 2018 e 2022", "",
            "Em cada corte o modelo vê apenas pesquisas consideradas disponíveis naquela data. Em 2018, "
            "onde a fonte histórica não preserva uma data de publicação confiável separada do campo, usamos "
            "um atraso conservador de três dias. Em 2022, a comparação oficial é renormalizada nos quatro "
            "candidatos individualizados pela fonte Nexo. A média simples usa exatamente a mesma janela de pesquisas e serve como baseline deliberadamente pouco sofisticado.", "",
        ]
        bm = backtest_metrics.sort_values(["election_year", "days_before"], ascending=[True, False])
        cols = [
            ("election_year", "Ano", lambda x: str(int(x))),
            ("days_before", "Dias antes", lambda x: str(int(x))),
            ("mae_pp", "MAE modelo", lambda x: _fmt(x, 2) + " p.p."),
            ("baseline_mae_pp", "MAE média simples", lambda x: _fmt(x, 2) + " p.p."),
            ("rmse_pp", "RMSE modelo", lambda x: _fmt(x, 2) + " p.p."),
            ("coverage_80_nowcast", "Cob. IC latente 80%", lambda x: _fmt(100 * float(x), 0) + "%"),
        ]
        if "coverage_80_election_prior" in bm.columns:
            cols.append(("coverage_80_election_prior", "Cob. prior eleitoral 80%", lambda x: _fmt(100 * float(x), 0) + "%"))
        cols.append(("n_candidates", "n", lambda x: str(int(x))))
        lines.append(_table(bm, cols))

    lines += [
        "", "## Notas", "",
        "- O estado é uma composição única em coordenadas ILR; não há ajuste candidato a candidato seguido de projeção.",
        "- Zeros são tratados por uma correção de meia contagem dependente do tamanho efetivo da amostra, não por piso percentual fixo.",
        "- A covariância amostral multinomial entra conjuntamente no espaço ILR.",
        "- O passeio aleatório, a dispersão de instituto e o ruído extra de levantamento são estimados por REML; não há `transfer=0.35`, `k=12`, shrinkage 0,5, penalidade de novidade ou inflação manual de tracking no núcleo v0.9.",
        "- A incerteza do resultado eleitoral não é confundida com a precisão do consenso das pesquisas. Em vez de um sigma_0 arbitrário calibrado em dois ciclos, a v0.9 permite um prior externo explícito e reportado separadamente.",
        "- As medianas marginais não precisam somar exatamente 100%, embora cada draw posterior seja uma composição que soma 100%.",
        "- Após a finalização da cédula, nomes fora da lista oficial são excluídos do nowcast corrente em modo fail-closed.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")