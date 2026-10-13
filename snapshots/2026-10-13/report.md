# Segundo turno — atualização de 13/10/2026

Repositório: polling-bayes-br. Execução auditável: [GitHub Actions #38413282065](https://github.com/dmiranda2/polling-bayes-br/actions/runs/38413282065). **71 testes passaram**. Base: `data/manual_second_round_2026.csv`; modelo: `src/runoff_nowcast.py`. Todos os valores abaixo são percentuais dos **votos válidos**. Não são uma previsão dos votos nas urnas em 25/10/2026.

## Pesquisas consideradas

Uma única pesquisa mais recente por instituto. Coleta exclusivamente posterior ao primeiro turno (04/10), salvo cenário de sensibilidade da Atlas.

| Instituto | Coleta | Lula | Flávio Bolsonaro | Registro |
|---|---|---:|---:|---|
| PoderData | 10–12/10 | 49,00 | 51,00 | BR-01209/2026 |
| Nexus/BTG | 10–12/10 | 48,00 | 52,00 | BR-07997/2026 |
| Gerp | 08–12/10 | 45,00 | 55,00 | BR-07877/2026 |
| DataTrends | 07–09/10 | 46,90 | 53,10 | BR-03576/2026 |
| Ipespe | 06–08/10 | 47,30 | 52,70 | BR-00933/2026 |
| Datafolha | 06–07/10 | 48,00 | 52,00 | BR-02949/2026 |
| Vox Brasil | 05–07/10 | 50,86 | 49,14 | BR-09623/2026 |
| AtlasIntel (somente sensibilidade) | 03–08/10 | 47,20 | 52,80 | BR-03663/2026 |

O PoderData antigo, BR-08134/2026, foi preservado no arquivo auditável, mas não contado duas vezes no ajuste. O percentual da Vox Brasil é convertido dos percentuais totais 44,2 e 42,7 para votos válidos. A Atlas começou a coleta **antes** de 04/10 e não integra o cenário principal.

## Nowcast — janela histórica 14 a 21 dias antes do segundo turno

| Seleção | Tratamento | N | Consenso Lula | Consenso Flávio | Lula cenário hipotético de erro eleitoral comum | IC 80% de Lula nesse cenário |
|---|---|---:|---:|---:|---:|---|
| Principal, pós-04/10 | Sem correção | 7 | 47,8241 | 52,1759 | 47,7970 | 44,4768–51,2120 |
| Principal, pós-04/10 | House effects históricos 2T | 7 | 47,8743 | 52,1257 | 47,8472 | 44,5265–51,2622 |
| Principal, pós-04/10 | Média histórica livre, **experimental/não validada** | 7 | 47,8743 | 52,1257 | 50,1023 | 46,2572–54,0352 |
| Sensibilidade, com Atlas | Sem correção | 8 | 47,7486 | 52,2514 | 47,7220 | 44,4232–51,1206 |
| Sensibilidade, com Atlas | House effects históricos 2T | 8 | 47,7928 | 52,2072 | 47,7661 | 44,4669–51,1648 |
| Sensibilidade, com Atlas | Média histórica livre, **experimental/não validada** | 8 | 47,7928 | 52,2072 | 50,0196 | 46,1823–53,9290 |

Consenso principal corrigido: intervalo marginal de 80% para Lula de **46,8414 a 48,9078** e de 95% **46,2984 a 49,4506**. Após acrescentar o erro compartilhado da indústria no cenário hipotético (não projetado para 25/10), IC80% de Lula **44,5265 a 51,2622**, IC95% **42,7803 a 53,0281**.

Ajustes de instituto: **4 de 7 institutos** com histórico 2T, correspondendo a **66,46% do peso** das observações. Deslocamento do consenso é +0,0502 p.p. para Lula. A camada comum continua com média direcional zero, pois a média livre não passou no LOO por eleição inteira.

## Calibração histórica 14–21 dias (mesma janela da comparação de 10/10)

23 pesquisas em quatro eleições (2006, 2010, 2014, 2022). Média livre histórica no balanço `z=(log p_PT - log p_oponente)/sqrt(2)`: **-0,06398579** (EP **0,04252468**). Validação LOO: livre **1,69**, média zero **3,58**, prior externo de erro comum 2,5 p.p. **4,05** (maior é melhor). **Média histórica direcional rejeitada como correção principal.**

Desvios históricos PT pesquisa menos urna, em pontos percentuais, nesta janela: 2006 **-4,20**; 2010 **-1,84**; 2014 **-4,11**; 2022 **+1,19**. Essa diferença inclui possível evolução de voto entre pesquisa e eleição, não apenas erro de medição. Nunca aplicar viés do primeiro turno ao segundo.

## Sensibilidade da janela histórica 1 a 14 dias

Com as mesmas **sete pesquisas atuais**, o consenso **sem correção** é **47,8767% Lula / 52,1233% Flávio** e **com correção histórica regularizada** cerca de **47,88% / 52,12%**. O cenário experimental de média histórica livre (rejeitada) dá **48,26% Lula / 51,74% Flávio** como cenário hipotético de eleição imediata, com IC80% Lula **44,80–51,81**.

Média histórica livre ILR **-0,01165499**, EP **0,01713317**; logscore LOO: livre **1,9559**, média zero **2,5850**, prior externo **6,0907** — a média livre também é rejeitada nesta janela. Para 13/10 (12 dias até 25/10), `1:14` é uma sensibilidade útil de proximidade temporal; `14:21` é a comparação limpa com o snapshot de 10/10.

## Comparação com snapshot arquivado de 10/10

No snapshot de 10/10 com apenas três pesquisas, o consenso com efeitos históricos de instituto foi **48,31% Lula / 51,69% Flávio**. Agora é **47,87% / 52,13%**, variação de aproximadamente **-0,43 / +0,43 p.p.**, mas a seleção de pesquisas e disponibilidade de dados mudaram, então não é uma estimativa causal de deslocamento do eleitorado.

## Arquivos de execução e referências

- [Execução de 13/10 com todos os CSVs, relatórios e auditorias (71 testes)](https://github.com/dmiranda2/polling-bayes-br/actions/runs/38413282065)
- [Artefato de 13/10, inclusive as janelas 14:21 e 1:14](https://github.com/dmiranda2/polling-bayes-br/actions/runs/38413282065/artifacts/11821239760)
- [Snapshot de 10/10](../2026-10-10/report.md)
- [Modelo e política de validação](../../docs/SECOND_ROUND_DESIGN.md)
- [Dados e fontes por instituto](../../data/manual_second_round_2026.csv)

**Nota técnica:** nenhuma destas saídas é previsão do resultado de 25 de outubro: o nowcast não projeta mudanças na intenção de voto nos dias restantes. A sensibilidade com média histórica direcional não validada não deve substituir o modelo principal. Os arquivos CSV completos e a auditoria são disponibilizados no artefato da execução.
