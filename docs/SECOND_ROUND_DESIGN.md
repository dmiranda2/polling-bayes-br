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
