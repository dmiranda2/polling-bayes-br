# Segundo turno de 2026 — arquitetura e auditoria

O modelo de segundo turno **não** usa o histórico de pesquisas de primeiro turno como estimador de viés. Na branch experimental `v1-historical-error`, `src/historical_error.py` é o experimento antigo de primeiro turno, mantido apenas para comparação. O código aplicável ao confronto Lula × Flávio Bolsonaro é `src/historical_second_round.py`, calibrado com levantamentos nacionais **de segundo turno** das eleições de 2002, 2006, 2010, 2014, 2018 e 2022, confrontados com a apuração oficial **de segundo turno**. Embora os resultados oficiais estejam disponíveis nos seis ciclos, o snapshot público empregado em 09/10/2026 fornece observações utilizáveis na janela final apenas para **2006, 2010, 2014 e 2022**; a ausência de 2002 e 2018 é explicitada na auditoria e reduz a segurança da calibração.

## Variável comum e sinal

A referência é sempre PT menos adversário, inclusive em 2018, quando o PT perdeu. Usamos a coordenada ILR
`z=(log(p_PT)-log(p_oponente))/sqrt(2)`, com `p` da mesma pergunta de segundo turno. O viés é definido como `z_pesquisa-z_urna`; logo, um viés histórico positivo deve ser **subtraído** do agregado atual.

O modelo histórico é `y_eji = mu + b_e + h_j + eps_eji`, em que `b_e` é o erro comum de uma eleição, `h_j` é o efeito de instituto e `eps_eji` inclui erro amostral e dispersão adicional. As variâncias são ajustadas por REML. A unidade de validação é a **eleição inteira**, não a observação individual. A calibração usa a última pesquisa por instituto em cada janela; cenário nacional, pesquisa estimulada, **segundo turno**, e exclui o próprio dia do pleito porque a base pode conter exit polls.

A janela principal é sete dias antes da votação; três e catorze dias são verificações predefinidas. Um viés médio direcional só pode ser aplicado se melhora o logscore LOO, vence o baseline de 2,5 p.p., mantém sinal nas três janelas e em todos os jackknifes. Se essas verificações falham, usa-se média histórica zero com escala aprendida, se o modelo zero-médio ainda vence o baseline. Se a amostra histórica for insuficiente ou o baseline vencer, preserva-se a hipótese externa de erro eleitoral comum de 2,5 p.p. Quando há histórico suficiente para estimar dispersão **entre levantamentos**, essa dispersão é mantida mesmo se a estimativa histórica do choque **comum** perder no LOO. Não se vende como estimativa calibrada um número condicionado a um resultado de apenas seis eleições.

## Pesquisas atuais (publicadas até 09/10/2026)

O arquivo `data/manual_second_round_2026.csv` armazena fontes e registros, além de período de campo, publicação, metodologia e base total/válida. Os números de votos válidos são:
- PoderData/Aya (05–07/10, 3.000 pessoas): Lula 47% / Flávio 53%. BR-08134/2026.
- Vox Brasil (05–07/10, 2.100 pessoas): Lula 50,86% / Flávio 49,14%, **calculados** de 44,2% / 42,7% em votos totais. BR-09623/2026.
- Datafolha (06–07/10, 2.520 pessoas): Lula 48% / Flávio 52%. BR-02949/2026.
- AtlasIntel/Bloomberg (03–08/10, 5.026 pessoas): Lula 47,2% / Flávio 52,8%. BR-03663/2026.

**O Atlas começa antes da votação de primeiro turno em 04/10.** Portanto o nowcast principal inclui somente as três pesquisas com coleta integralmente posterior. Um segundo resultado inclui Atlas como **sensibilidade**, com indicação no CSV e no relatório. Não misturamos pré e pós-primeiro turno como observações equivalentes.


## Seleção de turno e janela histórica (atualização de 09/10)

A calibração agora aceita **`--round 1`, `--round 2` ou `--round both`**. No modo `both`, o programa executa os dois ajustes **separadamente**: cada pesquisa entra apenas no seu turno e é comparada com o resultado eleitoral daquele turno. Nunca se misturam levantamentos nem erros de primeiro e segundo turnos.

O argumento `--windows` aceita intervalos inclusivos de **dias anteriores à eleição**, escritos `proximo:distante`. O dia zero fica sempre excluído, por risco de confundir pesquisas eleitorais com pesquisas de boca de urna:

- `1:7` utiliza os dias **1 a 7** antes do pleito (última semana);
- `14:21` utiliza os dias **14 a 21** antes do pleito — aproximadamente a posição de 09/10 em relação ao segundo turno de 25/10;
- `1:3` e `1:14` fornecem comparações adicionais;
- o formato antigo `7` continua funcionando como abreviação de `1:7`.

Exemplo completo:

```bash
python src/historical_calibration.py \
  --round both --windows 1:3,1:7,1:14,14:21 \
  --out output_history_rounds

python src/runoff_nowcast.py \
  --as-of 2026-10-09 \
  --history output_history_rounds/round_2/historical_poll_errors.csv \
  --historical-window 14:21 \
  --out output_second_round_14_21
```

O novo arquivo de auditoria identifica `election_round`, `window_min_days`, `window_days` e `window_label`, impedindo que períodos com o mesmo limite superior sejam agregados acidentalmente. Janelas sem amostra histórica suficiente permanecem na auditoria, mas **não** geram estimativas artificiais. A calibração para o nowcast de segundo turno rejeita automaticamente arquivos de histórico sem identificação de turno ou contendo dados de primeiro turno.

**Correção no backtest:** o baseline externo de 2,5 p.p. é convertido para a coordenada ILR em uma referência predeterminada de 50%/50%, sem consultar o resultado real da eleição omitida. Antes, essa transformação dependia indevidamente do resultado de teste; os logscores anteriores devem ser considerados provisórios até a nova execução.

A coluna `data` do Poder360 histórico é interpretada como data do levantamento na extração. É necessário confirmar a semântica da fonte antes de afirmar que os intervalos correspondem rigorosamente às datas de campo dos levantamentos.

A troca de janela é uma **análise de sensibilidade**; o código não escolhe automaticamente a janela que mais favorece um candidato ou a que melhor se ajusta ao resultado de 2026.

## Nowcast presente versus voto futuro

O nowcast em `src/runoff_nowcast.py` usa pesos inversos à variância, com margens amostrais, dispersão residual histórica e incerteza do efeito de instituto separadas. A média histórica validada, se houver, é subtraída apenas na camada hipotética de eleição hoje; o erro comum da eleição **não** diminui artificialmente com mais sondagens do mesmo ciclo.

A saída tem duas distribuições diferentes: consenso latente das pesquisas em 09/10 e votação hipotética hoje sob o erro comum histórico. **Nenhuma delas prevê o resultado em 25/10/2026**, pois não se modela evolução da preferência durante a campanha nas duas semanas restantes.

Comandos reproduzíveis:

```sh
python src/historical_second_round.py --results data/presidential_second_round_results.csv --out output_second_round_bias --windows 3,7,14
python src/runoff_nowcast.py --as-of 2026-10-09
PYTHONPATH=src pytest -q
```

Executar o nowcast sem calibração histórica produz resultado explicitamente marcado como `external_fallback`. Os arquivos gerados incluem auditoria do histórico, fontes individuais e uma sensibilidade Atlas.


## Duas saídas paralelas com viés do primeiro turno (10/10/2026)

A nova camada usa **somente como sensibilidade** os erros informados no calendário do usuário de 10/10/2026. Não altera a calibração de erro comum de **segundos turnos históricos** descrita acima.

Definimos sempre a margem como **Flávio menos Lula**. Cada erro de instituto informado é:

\[
b_j^{(1)}=[F-L]_{\text{pesquisa, 1ºT}}-[F-L]_{\text{urna, 1ºT}}.
\]

As dez linhas informadas são consistentes com uma margem de referência de +1,8 ponto percentual, inferida dos próprios dados fornecidos (sem checagem independente do resultado oficial). A hipótese de transferência produz

\[
 [F-L]_{\mathrm{2ºT,corr}}=[F-L]_{\mathrm{2ºT,publicado}}-b_j^{(1)},
 \quad L_{\mathrm{corr}}=L_{\mathrm{publicado}}+b_j^{(1)}/2,
 \quad F_{\mathrm{corr}}=F_{\mathrm{publicado}}-b_j^{(1)}/2.
\]

Isso preserva L+F=100 e usa a **mesma observação, mesma amostragem e mesma calibração de segundo turno** nos dois modos. Trata-se de um ajuste de margem em pontos percentuais, não de usar percentuais brutos de primeiro turno como votos válidos de segundo turno. Após o ajuste de margens, convertemos as proporções à coordenada ILR para executar o agregador normalmente.

A saída **sem correção** usa as percentagens publicadas e é a referência principal. A saída **com correção de 1º turno** supõe transferência integral de cada viés e deve ser lida como sensibilidade: a estabilidade de um erro específico entre turnos não foi validada. Os intervalos condicionais apresentados na versão corrigida **não** incluem incerteza de transporte desse viés.

Viés não conhecido não é igual a viés zero. Institutos não identificados (atualmente Vox Brasil) permanecem sem ajuste e aparecem claramente identificados, com quantidade e cobertura amostral ponderada no relatório. Equivalências de marca são verificadas em data/pollster_aliases.csv.

Arquivos novos:

- data/first_round_pollster_bias_2026.csv — erros de margem extraídos do calendário fornecido;
- data/scheduled_polls_2026_10_10.csv — registros futuros nacionais e regionais, com dados das últimas pesquisas apenas como referências, **não resultados futuros**;
- src/first_round_bias.py — validação de sinais e aplicação condicional dos erros;
- tests/test_first_round_bias.py — testes de identidade, sinal, cobertura e proteção contra resultados futuros.

Execução (o comando gera **dois relatórios** e **dois CSVs** além do comparativo):

    python src/runoff_nowcast.py --as-of 2026-10-10 --bias-modes both --historical-window 14:21

Arquivos de saída incluem report_uncorrected_2026-10-10.md, report_first_round_corrected_2026-10-10.md, nowcast_uncorrected_2026-10-10.csv, nowcast_first_round_corrected_2026-10-10.csv, polls_used_2026-10-10.csv, calendar_audit_2026-10-10.csv e report_2026-10-10.md.

**Auditoria de calendário:** BR-05187 (Gerp) e BR-06778 (Correio do Povo/TO) têm data de publicação prevista anterior ao encerramento do campo. Eles permanecem registrados e sinalizados, mas não são convertidos em resultados. As pesquisas regionais tampouco entram no agregado nacional. Novos levantamentos nacionais entram **somente quando há resultado de segundo turno publicado e auditado** em data/manual_second_round_2026.csv.

Esta camada não transforma o nowcast em previsão para a urna de 25/10.
