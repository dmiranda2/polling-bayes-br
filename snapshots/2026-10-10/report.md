# Segundo turno — três modos preservados (10/10/2026)

Este snapshot reproduz o cálculo com dados nacionais disponíveis até 10/10/2026.
**O terceiro modo usa uma hipótese histórica não validada. Não é uma previsão da urna de 25/10.**

Execução reproduzível: [GitHub Actions #38099999954](https://github.com/dmiranda2/polling-bayes-br/actions/runs/38099999954); **70 testes aprovados**.

## Consenso das pesquisas versus sensibilidade condicional ao erro comum

| Seleção | Método | Lula no consenso | Flávio no consenso | Lula no cenário condicional (80%) | Flávio no cenário condicional |
|---|---|---:|---:|---:|---:|
| Principal (3 pesquisas) | Sem correção | 48.28% | 51.72% | 48.26% [44.78–51.83] | 51.74% |
| Principal (3 pesquisas) | Correção histórica aceita | 48.31% | 51.69% | 48.29% [44.80–51.85] | 51.71% |
| Principal (3 pesquisas) | EXPERIMENTAL: média livre não validada | 48.31% | 51.69% | 50.54% [46.56–54.61] | 49.46% |
| Sensibilidade Atlas (4) | Sem correção | 48.05% | 51.95% | 48.03% [44.60–51.53] | 51.97% |
| Sensibilidade Atlas (4) | Correção histórica aceita | 48.07% | 51.93% | 48.04% [44.62–51.55] | 51.96% |
| Sensibilidade Atlas (4) | EXPERIMENTAL: média livre não validada | 48.07% | 51.93% | 50.30% [46.37–54.30] | 49.70% |

**Importante:** a média livre altera somente o cenário condicional; o consenso das pesquisas não é deslocado por ela.
Os cenários principal e com histórico de instituto permanecem com a média comum direcional rejeitada (zero).
No terceiro cenário, o deslocamento de erro comum é explicitamente experimental e o intervalo inclui a incerteza estimada de sua média.

## O sinal histórico preservado

| Segundo turno | Institutos | PT: pesquisa menos urna (p.p.) |
|---|---:|---:|
| 2006 | 2 | -4.20 |
| 2010 | 4 | -1.84 |
| 2014 | 6 | -4.11 |
| 2022 | 11 | +1.19 |

- Média livre no balanço ILR: **-0.063986**; erro padrão **0.042525**.
- Janela histórica: **14:21 dias** antes de cada segundo turno; 23 pesquisas em 4 eleições.
- Logscore LOO livre: **1.69**; média zero: **3.58**; prior externo: **4.05** (maior é melhor).
- Correção direcional comum no modelo principal: **rejeitada**.

**Por que não é conclusivo?** Os desvios de pesquisas realizadas duas a três semanas antes da eleição em relação à urna incorporam tanto erro de medição quanto possíveis mudanças reais da preferência eleitoral. O histórico cobre apenas quatro eleições nesta janela. A média livre perdeu no backtest por eleição inteira.

## Arquivos de auditoria

- [Todos os seis resultados, com intervalos de 80% e 95%](nowcast.csv)
- [Parâmetros e decisões da calibração histórica](calibration_audit.json)
- [Erros observados em cada eleição da janela](historical_election_errors.csv)
- [Código do agregador](../../src/runoff_nowcast.py)
- [Metodologia e ressalvas](../../docs/SECOND_ROUND_DESIGN.md)
- [Saídas completas e histórico por instituto da execução](https://github.com/dmiranda2/polling-bayes-br/actions/runs/38099999954)

Nenhum viés do primeiro turno de 2026 nem resultado futuro foi usado no cálculo.
