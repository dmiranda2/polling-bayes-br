# Atualização do segundo turno: 21/10/2026, 10h32 BRT

Atualização exclusivamente de dados: nove novas rodadas, incluindo Quaest de 21/10. A calibração histórica principal 7:14, o código numérico, 30.000 draws, seed 418, os critérios de seleção e os três modos foram mantidos. Publicação deste snapshot autorizada em 21/10/2026, após a entrega dos resultados.

## Resultado

A média móvel ponderada pelos pesos de precisão/incerteza do modelo, com as divulgações de 19–21/10 e uma rodada por instituto, chega a **Lula 48,871469% / Flávio Bolsonaro 51,128531%**, com **12 institutos**. Em 20/10 eram 49,041617% / 50,958383% (10 institutos). O último ponto arquivado de 19/10 permanece 49,018422% / 50,981578%; a diferença de Lula é −0,146953 ponto percentual.

A seleção completa inclui 19 institutos. O gráfico de evolução usa somente `polling_*` do modo `none` na janela móvel. Os cenários `counterfactual_*` respondem à hipótese condicionada de uma eleição hoje, **não são previsão do resultado de 25/10 nem probabilidade de vitória**. A média livre permanece **experimental e não validada**; ela altera o cenário condicionado, não o consenso histórico.

| selection         | bias_mode                 |   n_surveys |   polling_lula_pct |   polling_flavio_pct |   counterfactual_lula_pct |   counterfactual_flavio_pct |
|:------------------|:--------------------------|------------:|-------------------:|---------------------:|--------------------------:|----------------------------:|
| full              | none                      |          19 |       48.976105162 |         51.023894838 |              48.948837408 |                51.051162592 |
| full              | second_round_history      |          19 |       49.205737734 |         50.794262266 |              49.178465356 |                50.821534644 |
| full              | experimental_free_mean_2t |          19 |       49.205737734 |         50.794262266 |              50.114008017 |                49.885991983 |
| publication_19_21 | none                      |          12 |       48.871469209 |         51.128530791 |              48.838219105 |                51.161780895 |
| publication_19_21 | second_round_history      |          12 |       48.848772981 |         51.151227019 |              48.815523576 |                51.184476424 |
| publication_19_21 | experimental_free_mean_2t |          12 |       48.848772981 |         51.151227019 |              49.749946499 |                50.250053501 |

## Novas pesquisas

| Divulgação | Instituto | Registro | Lula / Flávio válidos (%) | Base |
|---|---|---|---:|---|
| 2026-10-19 | DataTrends | BR-04454/2026 | 48.500000 / 51.500000 | Válidos publicados |
| 2026-10-20 | Real Time Big Data | BR-02952/2026 | 48.000000 / 52.000000 | Válidos publicados |
| 2026-10-20 | Alfa Inteligência | BR-00820/2026 | 48.500000 / 51.500000 | Válidos publicados |
| 2026-10-20 | Instituto França | BR-07896/2026 | 49.190000 / 50.810000 | Válidos publicados |
| 2026-10-20 | Data Ranking | BR-00152/2026 | 50.400000 / 49.600000 | Válidos publicados |
| 2026-10-21 | Ideia | BR-08251/2026 | 48.900000 / 51.100000 | Válidos publicados |
| 2026-10-21 | Palver | BR-04612/2026 | 49.000000 / 51.000000 | Válidos publicados |
| 2026-10-21 | Futura | BR-06614/2026 | 48.900000 / 51.100000 | Válidos publicados |
| 2026-10-21 | Quaest | BR-08535/2026 | 49.438202 / 50.561798 | Calculados de 44/45 totais |

O conjunto passa de 50 para 68 linhas e de 25 para 34 registros. Cinco institutos novos para esta seleção (Real Time Big Data, Alfa, Instituto França, Data Ranking e Ideia) entram pelo mesmo critério já existente, sem alteração de pesos ou do universo elegível. DataTrends, Futura, Palver e Quaest substituem suas rodadas anteriores apenas na seleção vigente. Todas as rodadas anteriores continuam na base.

## Datas e ausência de informação futura

Os pontos e arquivos diários de 08–19/10 foram preservados byte a byte, no corte que existia quando foram produzidos. A DataTrends BR-04454 foi publicada às 14h25 de 19/10, depois do corte arquivado de 10h17, e portanto só entra a partir do ponto de 20/10. O ponto de 20/10 utiliza as publicações verificadas até 13h46 naquele dia. O corte atual é 21/10 às 10h32 BRT; a Quaest já estava publicada às 10h18–19, embora localizada na conferência posterior.

## Proveniência e ressalvas

- Quaest: Lula44 / Flávio45 nos totais, corroborados em UOL e Itatiaia; válidos **calculados** como 44/89 e 45/89, não apresentados como percentuais publicados. Não se arredondou para 49/51. As categorias residuais são branco/nulo9 e indecisos2; a VEJA as inverte. Essa divergência não afeta o par de candidatos.
- Meio/Ideia: válidos e totais conferidos visualmente no PDF primário, páginas6–7. Palver: totais e metodologia conferidos no PDF; os válidos49/51 são os publicados pelo JOTA, não a conversão de totais arredondados. O n efetivo1745 e DEFF2,86 informados pela Palver estão registrados na proveniência, sem trocar a regra de n efetivo do modelo.
- Futura21/10: rodadas, campo e registro corroborados no catálogo oficial; percentuais, amostra e CATI em múltiplas reportagens. O PDF primário exige cadastro e não foi acessado. A ressalva da Futura19/10 continua preservada no histórico.
- Real Time: totais/ficha no relatório primário; válidos publicados pela imprensa. Alfa: duas reportagens concordantes; PDF não acessado. Instituto França: ficha e válidos no primário. Data Ranking: publicação do parceiro e cobertura independente; margem declarada sem efeito de conglomerados, sem mudança metodológica silenciosa.
- Gerp tracking20/10 fica fora por campo/registro não resolvidos. A Veritá antiga de17/10 não foi duplicada. Data Pop BR-01683 é estadual de Tocantins, não nacional. Pesquisas apenas agendadas não entram.

`new_polls.json` e `sources.csv` contêm as URLs de cada observação e o nível de verificação. PDFs de fontes não são incorporados ao Git. As URLs públicas e a ficha auditável acompanham os dados.

## Validação e preservação

Antes da atualização, a execução anterior foi reproduzida offline: série diária, pesos, calibrações e CSV central idênticos byte a byte. **73 testes passaram** na reprodução e na execução atual. A auditoria independente dos pesos/mediana encontrou diferença máxima de resultado de 0 ponto percentual, pesos 1.42e-14 pp e variância ILR 8.67e-19.

Verificados: soma dos candidatos e pesos em100%, IDs/candidatos únicos, uma rodada por instituto, ausência de lookahead, zero deslocamento direcional em `none`, código e calibração inalterados, nenhuma transferência de viés de primeiro turno, 22 saídas executadas e duas indisponíveis na janela7:10 por insuficiência histórica. As comparações14:21 e1:14 continuam disponíveis no CSV; 7:10 não ganhou uma média livre inventada. Ambos os PNGs foram abertos e conferidos visualmente.

Os dados necessários para reproduzir e comparar o corte anterior estão em `prior_2026-10-19_1017/`. Os snapshots antigos do repositório não foram alterados. O arquivo integral de entrega preserva os309 arquivos anteriores byte a byte, fora do Git. `prior_reproduction_audit.json`, `audit_update.json`, `visual_qa.json` e `source_code_sha256.json` documentam a verificação.

## Reprodução

Requer Python e as dependências de `requirements.txt`; as versões efetivamente usadas estão em `requirements-lock.txt` e `runtime_environment.json`. Na raiz do repositório, instalar as dependências de `snapshots/2026-10-21/requirements-lock.txt` e executar `python snapshots/2026-10-21/run_all.py`. Isso não usa rede: reconstrói os dados a partir do snapshot e das nove novas rodadas, executa as verificações e a bateria de testes, e gera os dois PNGs. Este snapshot Git não contém PDFs ou ZIPs. O código numérico é importado de `../../src/` e conferido contra `source_code_sha256.json`. A versão congelada dos dados históricos já está incluída, sem necessidade de buscar fontes na rede.

Arquivos principais: `medias_moveis_3_dias_2026-10-21.png`, `comparativo_tres_saidas_2026-10-21.png`, `model_comparison_core_2026-10-21.csv`, `model_comparison_full_2026-10-21.csv`, `valores_diarios.csv`, `latest_weights.csv`, `daily_weights.csv`, `changes_since_2026-10-19.csv` e `data/input_polls.csv`.

## Integração Git

Este snapshot foi adaptado apenas para importar o código existente da raiz do repositório, sem duplicá-lo. O arquivo legado `data/manual_second_round_2026.csv` permanece intacto como fixture dos testes históricos; a base atual está em `snapshots/2026-10-21/data/input_polls.csv`. Foram adicionados cinco testes de regressão específicos deste snapshot: **78 testes passam** no repositório. Um workflow separado reproduz offline os resultados e verifica que os CSVs numéricos não mudam. O campo `git_publication=false` da auditoria registra que o script numérico não publica; a publicação autorizada posterior é registrada pelo histórico Git.
