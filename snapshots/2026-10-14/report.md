# Segundo turno — atualização de 14/10/2026

**Consenso principal: Lula 48.02% / Flávio Bolsonaro 51.98% dos votos válidos.** São nove pesquisas nacionais distintas, com a última rodada de cada instituto e campo integralmente posterior a 04/10. Sem correção histórica: 47.99% / 52.01%. **É um retrato das pesquisas, não uma previsão da urna em 25/10.**

## Novas inclusões e qualidade dos dados

- **Quaest, divulgada em 14/10:** 44% Lula e 46% Flávio nos votos totais; campo 10–13/10, 2.154 entrevistas presenciais domiciliares, margem de 2 p.p., confiança de 95%, contratante Globo, registro BR-08729/2026. A [publicação da CNN](https://www.cnnbrasil.com.br/eleicoes/quaest-flavio-tem-46-no-2o-turno-lula-44/) foi publicada às 18h07 e atualizada às 18h09 (horário de Brasília). Não foram confirmados percentuais oficiais de votos válidos nem a decomposição dos 10% restantes. O modelo utiliza a **normalização calculada dos totais arredondados**: 100 × 44/(44+46) = 48,8889% Lula; 100 × 46/(44+46) = 51,1111% Flávio. Esses valores derivados não são percentuais oficiais do instituto; as casas decimais decorrem da conta, não da precisão da pesquisa. Totais originais e classificação `derived_valid_from_rounded_total` foram preservados no CSV.
- **Futura, divulgada em 13/10 e acrescentada nesta atualização:** votos válidos publicados de 48,2% Lula e 51,8% Flávio; totais de 46,6% e 50,0%. Campo 07–10/10, 2.000 entrevistas CATI, margem de 2,2 p.p., confiança de 95%, registro BR-00650/2026. [Publicação](https://www.poder360.com.br/poder-eleicoes-2026/flavio-tem-518-contra-482-de-lula-diz-futura/), [relatório primário, páginas impressas 4, 5, 10 e 12](https://static.poder360.com.br/uploads/2026/10/Pesquisa-Futura-presidente.pdf). Usados os válidos publicados, sem substituí-los por renormalização dos totais arredondados. O relatório registra alteração da ponderação de escolaridade de TSE para PNAD; isso é uma ressalva de comparabilidade, sem mudança automática do modelo ou de seus efeitos históricos.
- PoderData BR-01209/2026 já estava incluída; a rodada BR-08134/2026 permanece no arquivo, mas não é contada de novo. AtlasIntel permanece exclusivamente na sensibilidade, por campo iniciado em 03/10.
- Não entraram supostas rodadas Veritá de 12/10 ou Real Time Big Data BR-08265/2026 indicadas por agregadores: faltou confirmação primária suficiente de publicação nacional, identidade e ficha. Não inferimos resultados nem incluímos pesquisas regionais como nacionais. Esses indícios não são prova de nova pesquisa elegível.

## Pesquisas consideradas

| Instituto | Campo | Publicação | Lula, válidos | Flávio, válidos | Registro |
|---|---|---|---:|---:|---|
| Quaest | 2026-10-10 a 2026-10-13 | 2026-10-14 | 48.8889 | 51.1111 | BR-08729/2026 |
| Gerp | 2026-10-08 a 2026-10-12 | 2026-10-13 | 45.0000 | 55.0000 | BR-07877/2026 |
| Nexus | 2026-10-10 a 2026-10-12 | 2026-10-13 | 48.0000 | 52.0000 | BR-07997/2026 |
| PoderData | 2026-10-10 a 2026-10-12 | 2026-10-13 | 49.0000 | 51.0000 | BR-01209/2026 |
| Futura | 2026-10-07 a 2026-10-10 | 2026-10-13 | 48.2000 | 51.8000 | BR-00650/2026 |
| DataTrends | 2026-10-07 a 2026-10-09 | 2026-10-11 | 46.9000 | 53.1000 | BR-03576/2026 |
| AtlasIntel (só sensibilidade) | 2026-10-03 a 2026-10-08 | 2026-10-09 | 47.2000 | 52.8000 | BR-03663/2026 |
| Ipespe | 2026-10-06 a 2026-10-08 | 2026-10-10 | 47.3000 | 52.7000 | BR-00933/2026 |
| Datafolha | 2026-10-06 a 2026-10-07 | 2026-10-08 | 48.0000 | 52.0000 | BR-02949/2026 |
| Vox Brasil | 2026-10-05 a 2026-10-07 | 2026-10-09 | 50.8600 | 49.1400 | BR-09623/2026 |

A Vox Brasil também usa conversão de votos totais, já existente. As fontes, metadados e classificações completas foram congeladas em [input_polls.csv](input_polls.csv). O conjunto tem 11 registros únicos arquivados (22 linhas de candidatos), com 9 institutos no principal e 10 com Atlas.

## Janela histórica 14:21, comparável aos snapshots anteriores

| Seleção | Tratamento | N | Consenso Lula | Consenso Flávio | Lula, cenário de erro comum | IC80% desse cenário |
|---|---|---:|---:|---:|---:|---|
| Principal | Sem correção | 9 | 47.9889 | 52.0111 | 47.9601 | 44.6706–51.3407 |
| Principal | House effects históricos 2T | 9 | 48.0234 | 51.9766 | 47.9947 | 44.7048–51.3753 |
| Principal | Média histórica livre, EXPERIMENTAL/NÃO VALIDADA | 9 | 48.0234 | 51.9766 | 50.2469 | 46.4218–54.1472 |
| Sensibilidade com Atlas | Sem correção | 10 | 47.9130 | 52.0870 | 47.8842 | 44.6068–51.2496 |
| Sensibilidade com Atlas | House effects históricos 2T | 10 | 47.9443 | 52.0557 | 47.9155 | 44.6378–51.2809 |
| Sensibilidade com Atlas | Média histórica livre, EXPERIMENTAL/NÃO VALIDADA | 10 | 47.9443 | 52.0557 | 50.1651 | 46.3519–54.0622 |

O consenso principal corrigido tem IC80% de Lula **47.1151–48.9320** e IC95% **46.6373–49.4091**. No cenário hipotético que acrescenta erro eleitoral comum, IC80% **44.7048–51.3753** e IC95% **42.9990–53.1504**. Os intervalos do consenso não incluem toda a incerteza de uma eleição futura.

Há correspondência histórica 2T para **6 dos 9 institutos**, representando **74.08% do peso**. A correção desloca Lula em **+0.0346 p.p.**. Mantidos os pesos de precisão e as hipóteses do código existente, sem adicionar recência ou transferir viés do primeiro turno.

Calibração: 23 pesquisas de 4 eleições (2006, 2010, 2014, 2022), exclusivamente segundo turno. Média livre ILR **-0.06398580**, EP **0.04252469**. LOO por eleição inteira: livre **1.6935**, média zero **3.5846**, prior externo 2,5 p.p. **4.0491** (maior é melhor). **A média livre continua rejeitada como correção principal.** A terceira leitura não validada permanece visível apenas como sensibilidade, com incerteza da média propagada.

## Sensibilidade da janela histórica 1:14

| Seleção | Tratamento | N | Consenso Lula | Consenso Flávio | Lula, cenário de erro comum | IC80% desse cenário |
|---|---|---:|---:|---:|---:|---|
| Principal | Sem correção | 9 | 48.0247 | 51.9753 | 47.9982 | 44.6728–51.4142 |
| Principal | House effects históricos 2T | 9 | 48.0247 | 51.9753 | 47.9982 | 44.6728–51.4142 |
| Principal | Média histórica livre, EXPERIMENTAL/NÃO VALIDADA | 9 | 48.0247 | 51.9753 | 48.4078 | 44.9941–51.9152 |
| Sensibilidade com Atlas | Sem correção | 10 | 47.9273 | 52.0727 | 47.9017 | 44.5976–51.3009 |
| Sensibilidade com Atlas | House effects históricos 2T | 10 | 47.9273 | 52.0727 | 47.9017 | 44.5976–51.3009 |
| Sensibilidade com Atlas | Média histórica livre, EXPERIMENTAL/NÃO VALIDADA | 10 | 47.9273 | 52.0727 | 48.3107 | 44.9165–51.8001 |

A 11 dias da votação de 25/10, esta janela é uma sensibilidade temporal útil; mantivemos 14:21 para comparação com os snapshots. Na janela 1:14, média livre ILR **-0.01165499**, EP **0.01713320**; LOO livre **1.9559**, média zero **2.5850**, prior externo **6.0907**. A média direcional livre também não é validada.

## Comparação e revisão do dado de 13/10

O [snapshot originalmente arquivado de 13/10](../2026-10-13/report.md) tinha 7 pesquisas principais e consenso corrigido de 47,8743% Lula / 52,1257% Flávio. Hoje são 48.0234% / 51.9766%, diferença de **+0.1491 p.p. para Lula**. A comparação envolve novas pesquisas e não isola mudança de opinião do eleitorado.

A Futura já havia sido publicada em 13/10, mas faltava na versão anterior da base. Reexecutar 13/10 com a base corrigida passa a incluir 8 pesquisas principais, obtendo **48,0475% Lula / 51,9525% Flávio** no modo corrigido 14:21. O registro antigo foi preservado sem reescrita. Estão disponíveis a [reprodução da base antiga](archived_2026-10-13_reproduction.csv) e a [revisão com Futura](revised_2026-10-13_nowcast.csv). A Quaest não entra em execuções anteriores à sua publicação em 14/10.

## Reprodução e auditoria

**73 testes passaram localmente** após as alterações. Os três modos, a seleção estrita, a sensibilidade Atlas, a ausência de vazamento por data de divulgação e a preservação de registros anteriores estão cobertos. O código estatístico em `src/` e os resultados oficiais históricos não foram alterados.

```bash
PYTHONPATH=src pytest -q
python src/historical_calibration.py --round 2 --windows 1:3,1:7,1:14,14:21 --out output_history_rounds/round_2
python src/runoff_nowcast.py --polls snapshots/2026-10-14/input_polls.csv --as-of 2026-10-14 --history snapshots/2026-10-14/historical_calibration/historical_poll_errors.csv --historical-window 14:21 --out output_reproduce_14_21
python src/runoff_nowcast.py --polls snapshots/2026-10-14/input_polls.csv --as-of 2026-10-14 --history snapshots/2026-10-14/historical_calibration/historical_poll_errors.csv --historical-window 1:14 --out output_reproduce_1_14
```

- [Saídas, pesquisas e auditoria 14:21](window_14_21/)
- [Saídas, pesquisas e auditoria 1:14](window_1_14/)
- [Histórico 2T e validação](historical_calibration/)
- [Manifesto de fontes e integridade](manifest.json)
- [Workflow atualizado](../../.github/workflows/second-round.yml), com reexecuções de 09/10, 10/10, 13/10 revisado e 14/10 nas janelas separadas

Cada resultado é condicionado aos dados e às hipóteses existentes; não contempla a evolução futura da campanha. A diferença histórica entre pesquisa pré-eleitoral e urna também pode conter mudança de voto, não apenas erro de medição.
