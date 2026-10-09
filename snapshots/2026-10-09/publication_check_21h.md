# Verificação de novas pesquisas nacionais — 09/10/2026, aproximadamente 21h (Brasília)

## Escopo

Confronto presidencial Lula × Flávio Bolsonaro no **segundo turno**, abrangência **Brasil**, pesquisas **efetivamente divulgadas até o horário da verificação**. Registro TSE sozinho não é divulgação de resultados. Não incluir levantamentos estaduais/DF, cenários de primeiro turno nem repetir várias notícias sobre a mesma pesquisa.

## Novos resultados verificados

**Nenhum levantamento nacional adicional foi confirmado** além dos quatro já registrados em `data/manual_second_round_2026.csv`.

| Instituto | Registro | Campo | Publicação | Lula válidos | Flávio válidos | Inclusão |
|---|---|---|---|---:|---:|---|
| PoderData/Aya | BR-08134/2026 | 05–07/10 | 08/10 | 47,00% | 53,00% | principal |
| Datafolha | BR-02949/2026 | 06–07/10 | 08/10 | 48,00% | 52,00% | principal |
| Vox Brasil | BR-09623/2026 | 05–07/10 | 09/10 | 50,86% | 49,14% | principal |
| AtlasIntel/Bloomberg | BR-03663/2026 | 03–08/10 | 09/10 | 47,20% | 52,80% | sensibilidade |

A Vox publicou percentuais **totais** de Lula 44,2% e Flávio 42,7%; os valores acima foram convertidos para base válida (com arredondamento). Atlas começa a coletar antes do primeiro turno de 04/10 e permanece fora do nowcast principal.

## Fontes consultadas

- [Poder360, síntese dos 4 levantamentos, 09/10 às 7h30](https://www.poder360.com.br/poder-pesquisas/saiba-como-estao-lula-e-flavio-nas-ultimas-pesquisas-de-2o-turno/) — especifica registros, campo, N, metodologia da base válida e exclusão temporal da Atlas.
- [Poder360, levantamentos que poderiam ser publicados na sexta-feira 09/10 às 6h15](https://www.poder360.com.br/poder-eleicoes-2026/saiba-quais-pesquisas-eleitorais-podem-sair-nesta-6a-feira-11/) — nacionais AtlasIntel e Vox Brasil; iGape é exclusivamente DF.
- [UOL, panorama do segundo turno, publicado às 17h11 de 09/10](https://noticias.uol.com.br/eleicoes/2026/10/09/pesquisa-segundo-turno-o-que-dizem-os-levantamentos-presidenciais-de-lula-e-flavio.ghtm).
- [Poder360, resultados Vox Brasil](https://www.poder360.com.br/poder-eleicoes-2026/lula-tem-442-e-flavio-427-no-2o-turno-diz-vox-brasil/).
- [Folha, Datafolha 08/10](https://www1.folha.uol.com.br/poder/2026/10/datafolha-flavio-bolsonaro-tem-52-e-lula-48-em-votos-validos-no-segundo-turno.shtml).
- [UOL, AtlasIntel/Bloomberg 09/10](https://noticias.uol.com.br/eleicoes/2026/10/09/atlasbloomberg-presidencial-segundo-turno.ghtm).

## Implicações

A estimativa nacional de 09/10 permanece inalterada porque **não há novos registros de pesquisas publicados e elegíveis** comprovados nesta verificação. Mantém-se o contraste principal com 3 institutos (todos posteriores ao primeiro turno) e Atlas como sensibilidade, conforme `snapshots/2026-10-09/window_sensitivity.csv`.

Na **calibração histórica**, todos os institutos com levantamentos elegíveis para o turno e janela escolhidos participam do ajuste conjunto `mu+b_e+h_j+eps`; a política atual retém a **última pesquisa por instituto, eleição e janela**. Isso não significa usar apenas os institutos contemporâneos, nem todos os levantamentos repetidos de um mesmo instituto.

Esta consulta é uma verificação jornalística e do agregador, **não** uma certificação de completude de todos os registros do TSE em tempo real.
