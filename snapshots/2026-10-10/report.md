# Segundo turno: nowcast 10/10/2026, somente histórico de 2º turno

Este retrato substitui integralmente o snapshot anterior, que havia empregado indevidamente erros de primeiro turno de 2026. Não há transferência de viés de primeiro turno nesta versão.

Reprodução do cálculo: [GitHub Actions run 38096531189](https://github.com/dmiranda2/polling-bayes-br/actions/runs/38096531189) — **58 testes aprovados**.

## Agregado em votos válidos

| Seleção | Correção | Lula | Flávio | IC80% para consenso Lula |
|---|---|---:|---:|---|
| Principal | Sem correção | 48.28% | 51.72% | 46.81–49.76% |
| Principal | Com ajuste histórico 2T | 48.31% | 51.69% | 46.84–49.78% |
| Sensibilidade Atlas | Sem correção | 48.05% | 51.95% | 46.75–49.35% |
| Sensibilidade Atlas | Com ajuste histórico 2T | 48.07% | 51.93% | 46.77–49.37% |

No cenário principal, o ajuste histórico de segundo turno muda a estimativa de Lula em **+0.024 ponto percentual**. Incluir a pesquisa Atlas, cujo campo incluiu dias anteriores ao primeiro turno de 04/10, é apenas análise de sensibilidade.

## Metodologia e limites

- Todos os levantamentos atuais usados são perguntas **de segundo turno**; três entram no cenário principal (PoderData, Vox Brasil, Datafolha).
- O ajuste por instituto é estimado exclusivamente a partir de pesquisas nacionais de **segundo turno** de eleições anteriores, comparadas com a urna de **segundo turno** desses anos.
- O erro comum direcional histórico foi **rejeitado** no LOO por eleição inteira: não há deslocamento direcional comum aplicado.
- A calibração usada foi a janela histórica 14–21 dias antes da urna. São quatro eleições com dados elegíveis e 23 levantamentos na janela.
- O histórico identificou efeitos específicos para dois dos três institutos no cenário principal; o peso estatístico coberto foi 77,12%. O ajuste resultante é muito pequeno.
- Ambos os modos usam o mesmo conjunto de observações, mesma ponderação amostral e mesmas escalas de incerteza.
- O prior externo de erro eleitoral comum de 2,5 p.p. não é uma correção direcional: representa apenas incerteza da votação hipotética hoje.
- Resultados futuros listados no calendário não foram imputados nem utilizados. Gerp BR-05187 e Correio do Povo/TO BR-06778 seguem sinalizados por inconsistências de data.

**Trata-se de nowcast com dados disponíveis até 10/10, não de previsão do resultado em 25/10/2026.**

## Arquivos relacionados

- [CSV reproduzido deste snapshot](nowcast.csv)
- [Código do segundo turno](../../src/runoff_nowcast.py)
- [Documentação das correções](../../docs/SECOND_ROUND_DESIGN.md)
- [Auditoria e saídas completas da execução](https://github.com/dmiranda2/polling-bayes-br/actions/runs/38096531189)
