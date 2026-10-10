# Modelo de segundo turno — retrato de 10 de outubro de 2026

**Reprodução auditada de um nowcast de pesquisas; não é previsão para a urna de 25/10/2026.**

Execução: [GitHub Actions #38095082885](https://github.com/dmiranda2/polling-bayes-br/actions/runs/38095082885) — 59 testes aprovados;
calibração histórica separada de segundo turno, janela 14–21 dias; 
código [commit 540fcf8](https://github.com/dmiranda2/polling-bayes-br/commit/540fcf883272ac5cfa18d223b8224f56af1ce0d8).

## Cenário principal: apenas pesquisas totalmente posteriores ao 1º turno

| Versão | Pesquisas | Lula (agregado) | Flávio (agregado) | Lula IC80% — pesquisas | Lula IC80% — votação hipotética hoje* |
|---|---:|---:|---:|---|---|
| Sem correção 1ºT | 3 | 48.31% | 51.69% | 46.84–49.78% | 44.80–51.85% |
| Com correção 1ºT | 3 | 47.03% | 52.97% | 45.56–48.49% | 43.53–50.57% |

Institutos: PoderData, Vox Brasil e Datafolha. O erro do 1º turno está disponível para
PoderData e Datafolha, que representam 77,12% do peso estimado no cenário corrigido.
**Vox Brasil não recebeu correção**, pois não há erro correspondente no calendário fornecido.

## Sensibilidade: incluindo pesquisa Atlas de campo misto

| Versão | Pesquisas | Lula (agregado) | Flávio (agregado) | Lula IC80% — pesquisas | Lula IC80% — votação hipotética hoje* |
|---|---:|---:|---:|---|---|
| Sem correção 1ºT | 4 | 48.07% | 51.93% | 46.77–49.37% | 44.62–51.55% |
| Com correção 1ºT | 4 | 46.55% | 53.45% | 45.26–47.85% | 43.12–50.03% |

A pesquisa Atlas teve campo 03–08/10, incluindo dias anteriores ao primeiro turno de 04/10.
Somente por isso aparece como sensibilidade, nunca como observação do cenário principal.
Os três institutos com erro do 1º turno informado correspondem a 82,11% do peso nessa análise.

## Como foi aplicada a correção

- Erro fornecido: `b_j=(Flávio−Lula) pesquisa no 1ºT − (Flávio−Lula) resultado no 1ºT`.
- Votos válidos corrigidos: `Lula_corr=Lula_original+b_j/2`, `Flávio_corr=Flávio_original−b_j/2`.
- Os erros dos 10 institutos são consistentes entre si com margem oficial *implícita* de +1,8 p.p. Flávio−Lula, **não verificada independentemente**.
- **Hipótese não validada:** transportamos integralmente o erro observado no 1º turno para um levantamento do 2º turno. Isto serve apenas como análise de sensibilidade.
- Todas as demais escolhas são idênticas nas versões: seleção de pesquisas, componentes de incerteza e pesos. O erro histórico de 2º turno manteve média zero, porque a correção direcional não passou no LOO.
- O termo histórico comum de 2,5 p.p. constitui incerteza **da urna hipotética hoje**, não estimativa de mudança até 25/10.

*Os intervalos condicionais da versão corrigida não quantificam a incerteza sobre a transportabilidade do viés.*

## Calendário

O calendário de 10/10 contém 11 registros nacionais futuros e oito regionais. Não foram
incorporados como resultados. Dois registros têm publicação anterior ao final do campo:
`BR-05187` (Gerp) e `BR-06778` (Correio do Povo, TO). Ambos estão marcados
na auditoria do script. A última pesquisa efetivamente incorporada nesta data
terminou o campo em 07/10 no cenário principal.

- [CSV com as quatro estimativas](nowcast.csv)
- [Script](../../src/runoff_nowcast.py)
- [Tabela de vieses](../../data/first_round_pollster_bias_2026.csv)
- [Calendário](../../data/scheduled_polls_2026_10_10.csv)
- [Artefatos integrais do run](https://github.com/dmiranda2/polling-bayes-br/actions/runs/38095082885/artifacts/11685637478)
