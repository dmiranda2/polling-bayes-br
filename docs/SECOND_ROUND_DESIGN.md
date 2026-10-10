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
  --round 2 --windows 1:3,1:7,1:14,14:21 \
  --out output_history_rounds/round_2

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



## Comparação de segundo turno: sem e com correção EXCLUSIVAMENTE do segundo turno (10/10/2026)

**O modelo nunca transfere para o segundo turno o erro observado no primeiro turno de 2026.**
A calibração usa pesquisas de SEGUNDO turno históricas comparadas com urnas de SEGUNDO turno do respectivo ano.
Preservamos os arquivos do modelo de primeiro turno para reprodução de trabalhos antigos, mas eles são completamente separados.

Os dois modos são executados sobre exatamente os mesmos levantamentos atuais de segundo turno (com as mesmas variâncias e ponderações):

1. **Sem correção:** na estimativa central, cada levantamento permanece com os seus percentuais publicados (a coordenada ILR original). Não se subtrai efeito histórico de instituto nem média direcional comum.
2. **Com correção do histórico de segundo turno:** para cada instituto, subtrai-se o efeito posterior regularizado estimado apenas em SEGUNDOS turnos anteriores, se houver correspondência histórica; institutos sem histórico não recebem deslocamento. A média comum pesquisa menos urna só é subtraída à distribuição hipotética de urna hoje se passar os critérios LOO por eleição inteira, estabilidade de sinal, janelas e jackknife.

A variável modelada é:

\[
 z=\frac{\log p_{\mathrm{Lula}}-\log p_{\mathrm{Flávio}}}{\sqrt2},
 \qquad
 z_{\mathrm{ajustado}}=z_{\mathrm{pesquisa,2T}}-\widehat h_{\mathrm{instituto,2T}}.
\]

Os efeitos históricos de instituto não representam uma garantia de persistência no ciclo de 2026. A parte comum do viés é mantida em zero se não validada, mesmo que a estimativa livre calculada seja diferente de zero. O erro eleitoral comum permanece separado do erro amostral e da dispersão residual.

O cenário principal considera somente pesquisas publicadas e com coleta integralmente posterior ao primeiro turno de 04/10. A pesquisa Atlas, cujo campo começou em 03/10, permanece apenas como sensibilidade; as pesquisas previstas no calendário para 11–16/10 não entram antes de seus resultados serem efetivamente publicados.

O arquivo data/scheduled_polls_2026_10_10.csv contém somente instituto, registro, alcance, amostra e datas. Inclui 11 pesquisas nacionais previstas e 8 regionais, com alertas de conflito de datas nos registros BR-05187 e BR-06778. O calendário não contém percentuais de votação nem erros de primeiro turno.

### Comandos reproduzíveis

Primeiro, calibrar apenas segundos turnos históricos:

    python src/historical_calibration.py --round 2 --windows 1:3,1:7,1:14,14:21 --out output_history_rounds/round_2

Depois, gerar as duas versões do mesmo nowcast de segundo turno:

    python src/runoff_nowcast.py --as-of 2026-10-10 --history output_history_rounds/round_2/historical_poll_errors.csv --historical-window 14:21 --bias-modes both

O programa grava:

- nowcast_uncorrected_2026-10-10.csv e report_uncorrected_2026-10-10.md;
- nowcast_second_round_corrected_2026-10-10.csv e report_second_round_corrected_2026-10-10.md;
- nowcast_2026-10-10.csv e report_2026-10-10.md para comparação;
- polls_used_2026-10-10.csv, bias_audit_2026-10-10.json e calendar_audit_2026-10-10.csv para auditoria.

**Nenhuma versão constitui previsão do resultado de 25 de outubro de 2026.**
