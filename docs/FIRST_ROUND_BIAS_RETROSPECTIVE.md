# Primeiro turno de 2026: contrafactual histórico preservado

ATENÇÃO: experimento retrospectivo, não previsão arquivada, não equivalente à versão v0.8 e sem efeitos sobre o modelo de SEGUNDO TURNO.

A v0.8 de qualidade por instituto calculava consistência relativa a pesquisas concorrentes; o experimento v1-historical-error é distinto e estima o erro médio direcional de pesquisas contra a urna, usando apenas PRIMEIROS turnos anteriores a 2026. A variante experimental pode ficar mais próxima do resultado de 2026, mas isso NÃO substitui a validação por eleição inteira deixada de fora (LOO).

O script independente src/first_round_counterfactual.py registra duas alternativas: a saída original da v0.9.1 e uma correção exploratória usando a média histórica livre do primeiro turno, sem fazer qualquer mistura com dados do segundo turno.

## Cálculo

Definimos a coordenada ILR z = log(p_Lula/p_Flavio)/sqrt(2). Em seguida, para o contrafactual, z_corrigido = z_original - mu_historico_primeiro_turno. Conservamos a soma Lula+Flávio e os demais candidatos; portanto não refazemos a posterior conjunta inteira.

## Reprodução

É necessário preservar o nowcast v0.9.1 pré-eleitoral de 03/10 e o respectivo run_manifest.json. Para reconstruir esse estado a partir das fontes hoje disponíveis (o que não garante que seja idêntico à previsão efetivamente divulgada em 03/10):

    python src/run.py --as-of 2026-10-03 --no-backtest --out output_first_round_2026_10_03

Gerar a calibração independente de PRIMEIRO turno usando eleições anteriores (2002–2022):

    python src/historical_calibration.py --round 1 --windows 1:3,1:7,1:14 --out output_history_round_1

Comparar as duas versões:

    python src/first_round_counterfactual.py --nowcast output_first_round_2026_10_03/nowcast_all_candidates.csv --manifest output_first_round_2026_10_03/run_manifest.json --history-dir output_history_round_1 --as-of 2026-10-03 --window 1:7 --out output_first_round_counterfactual

O programa grava os arquivos comparison_2026-10-03.csv, report_2026-10-03.md e audit_2026-10-03.json. Há verificação de turno, período histórico e data do nowcast. O relatório sempre destaca que a comparação é retrospectiva e registra os logscores LOO de média livre, média zero e referência externa.

## Limites

O script não reivindica reproduzir os pesos individuais da v0.8. Esses pesos dependiam da dispersão dos institutos em relação às outras pesquisas, não necessariamente da proximidade das urnas. A correção experimental utiliza a estimativa livre da média histórica e NÃO foi aceita em produção: um acerto retrospectivo do primeiro turno de 2026 não resolve a questão da validação.

O script src/runoff_nowcast.py continua restrito ao histórico de SEGUNDOS turnos. Não alterá-lo para receber nenhum arquivo output_history_round_1.
