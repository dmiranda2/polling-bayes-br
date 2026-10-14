# Segundo turno — EXPERIMENTAL — média livre 2T, não validada — 2026-10-14

Lula × Flávio Bolsonaro, votos válidos. **Não é previsão de 25/10.**
Histórico: exclusivamente pesquisas e resultados de SEGUNDO turno.
Janela histórica: 14:21.

**ALERTA: A MÉDIA LIVRE NÃO PASSOU NA VALIDAÇÃO LEAVE-ONE-ELECTION-OUT.**
A correção é mostrada apenas para preservar informação como sensibilidade,
sem elevar sua confiabilidade ou promovê-la ao cenário principal.
Ela altera apenas o cenário condicional ao erro comum histórico; a
estimativa do CONSENSO das pesquisas fica exatamente igual ao modo
de ajustes históricos aceitos. A incerteza estimada de mu é adicionada
em quadratura ao desvio-padrão do erro comum da eleição.

| Seleção | N | Lula: pesquisas (%) | Flávio: pesquisas (%) | Lula: cenário condicionado ao erro comum [IC80%] | Deslocamento comum ILR |
|---|---:|---:|---:|---:|---:|
| strict_post_first_round | 9 | 48.02 | 51.98 | 50.25 [46.42, 54.15] | -0.06399 |
| mixed_atlas_included | 10 | 47.94 | 52.06 | 50.17 [46.35, 54.06] | -0.06399 |
- strict_post_first_round: 6/9 institutos com histórico de 2T (peso 74.1%); sem correspondência: DataTrends, Nexus, Vox Brasil.
- mixed_atlas_included: 6/10 institutos com histórico de 2T (peso 67.0%); sem correspondência: AtlasIntel, DataTrends, Nexus, Vox Brasil.

## Histórico descritivo por eleição — não prova viés permanente

| Segundo turno | Institutos | PT: pesquisa menos urna (p.p.) |
|---|---:|---:|
| 2006 | 2 | -4.20 |
| 2010 | 4 | -1.84 |
| 2014 | 6 | -4.11 |
| 2022 | 11 | +1.19 |

Comparações de sondagens realizadas antes da votação com a urna final
misturam erros das pesquisas e possíveis mudanças reais do eleitorado.

## Validação histórica por eleição inteira

- Média histórica livre ILR: -0.06398579623524034.
- Erro padrão da média livre ILR: 0.042524691864571716.
- Logscore LOO da média livre: 1.6934678392691298.
- Logscore LOO da média zero: 3.584576712799966.
- Logscore LOO do prior externo: 4.049083076082821.
- Média direcional comum aceita no principal: False.
- Status da calibração: external_common_prior_historical_poll_noise.

## Limitações

- Nenhum erro do primeiro turno de 2026 é transportado para este modelo.
- Nenhuma sondagem futura ou estadual entra no agregado nacional.
- Atlas, cuja coleta começou antes da votação de 04/10, permanece
  apenas como sensibilidade, não na seleção principal.
- 19 registros no calendário; 2 datas conflitantes.
- Os intervalos são condicionais à hipótese escolhida e não são
  probabilidades de vitória nem previsões do resultado de 25/10.
