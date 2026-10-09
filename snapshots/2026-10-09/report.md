# Nowcast do segundo turno — 09/10/2026

Resultados reproduzidos na branch `main`, com 35 testes aprovados:
https://github.com/dmiranda2/polling-bayes-br/actions/runs/38003877268

| Cenário | Pesquisas | Lula | Flávio | Lula IC 80% (polling) | Lula IC 80% (erro comum) |
| --- | ---: | ---: | ---: | --- | --- |
| Principal, só campo integralmente pós-1º turno | 3 | 48,56% | 51,44% | 46,78–50,35% | 44,94–52,23% |
| Sensibilidade incluindo Atlas | 4 | 48,18% | 51,82% | 46,67–49,70% | 44,66–51,74% |

Pesquisas: PoderData/Aya (BR-08134/2026, 53% Flávio/47% Lula);
Vox Brasil (BR-09623/2026, 49,14% Flávio/50,86% Lula em válidos, calculados de 42,7%/44,2% totais);
Datafolha (BR-02949/2026, 52% Flávio/48% Lula);
AtlasIntel (BR-03663/2026, 52,8% Flávio/47,2% Lula).
Atlas tem coleta 03–08/10, incluindo antes do 1º turno em 04/10, portanto não entra no cenário principal.

**Viés histórico:** estimado apenas de pesquisas de 2º turno, comparadas à urna do mesmo turno. O histórico com dados elegíveis cobre 2006, 2010, 2014 e 2022 (26 levantamentos). Falta completar 2002 e 2018 na fonte automatizada. Média livre de erro (pesquisa menos urna): -0,01230 ILR, aproximadamente -0,87 pp na margem PT–adversário, mas **rejeitada** no LOO e jackknife. Logscores LOO (maior é melhor): média livre 2,159; média zero 2,653; prior externo 6,029. Mantivemos a variância residual de pesquisas históricas (tau_p=0,0591 ILR) e o prior externo de 2,5 pp para o erro comum, **sem correção direcional**.

A coluna 'erro comum' é o intervalo de votos **se a eleição fosse hoje**, não previsão do resultado em 25/10/2026. O modelo não prevê deslocamentos até o dia da votação.

Código, fontes e auditoria: [documentação](../../docs/SECOND_ROUND_DESIGN.md), [dados de entrada](../../data/manual_second_round_2026.csv), [CSV dos resultados](nowcast.csv).
