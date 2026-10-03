# v0.9 — resposta à revisão estrutural

A v0.9 foi feita para atacar as fontes de complexidade e erro identificadas depois da v0.8.1, sem reescrever a camada de dados.

## 1. Candidatos ajustados separadamente

**Resolvido.** O modelo passa a ajustar cada levantamento como uma composição única em coordenadas ILR. A covariância multinomial amostral entra diretamente no espaço transformado. Não existe correlação empírica entre candidatos seguida de projeção posterior no simplex.

Foi usada ILR, e não ALR, porque ALR ainda privilegia uma categoria de referência e continua problemática quando uma coordenada se aproxima de zero. Zeros são regularizados por meia contagem dependente de `n_eff` antes da transformação.

## 2. Média da indústria versus voto real

**Separado explicitamente.** O estado latente é o consenso das pesquisas. Um erro comum a toda a indústria não é inferido a partir do mesmo ciclo.

O relatório pode acrescentar um segundo intervalo eleitoral usando um prior externo de erro comum. Sua escala aparece no `config.json` e em `external_error_prior.csv`; ela não é estimada nem escolhida pelo backtest de 2018/2022.

## 3. Muitos hiperparâmetros manuais

**Removidos do núcleo v0.9.** Processo temporal, dispersão de instituto e ruído extra de levantamento são estimados por REML.

Para evitar uma matriz cheia mal identificada, cada um dos três componentes usa duas escalas: uma para o contraste dos dois líderes e outra para os demais balanços ILR. São seis hiperparâmetros estimados.

## 4. Transferência histórica

**Removida do nowcast.** `fit_nowcast()` aceita os argumentos antigos `quality` e `bias` apenas por compatibilidade de API e os ignora. Não há `transfer=0.35`, shrinkage histórico por candidato ou penalidade especial para instituto novo.

## 5. Passeio aleatório homocedástico

**Mantido por parcimônia nesta versão.** A volatilidade passa a ser estimada, mas não varia no tempo. Inovações t ou volatilidade dinâmica ficam como extensões que só devem entrar se o backtest justificar.

## 6. Baseline simples

**Adicionado.** O backtest calcula uma média simples de levantamentos completos usando a mesma janela temporal. O relatório mostra modelo e baseline lado a lado.

## 7. Resultado do diagnóstico atual

No cache de 3 de outubro de 2026, os 12 cortes de 2018/2022 dão, em média:

- v0.8.1: MAE 4,27 p.p.; RMSE 5,22 p.p.;
- v0.9.0: MAE 3,37 p.p.; RMSE 4,27 p.p.;
- baseline simples da v0.9: MAE 5,00 p.p.; RMSE 6,41 p.p.

A melhora é maior em 2018. Em 2022, a v0.9 é próxima do baseline e não vence em todos os cortes, o que é um sinal saudável contra uma narrativa de ganho artificialmente uniforme.

Os intervalos do polling nowcast continuam tendo cobertura baixa contra o resultado eleitoral — como esperado quando há erro sistemático compartilhado. O intervalo eleitoral com prior externo melhora a cobertura em alguns cortes, mas não é tratado como calibrado nesses dois ciclos.

## Fechamento v0.9.1

A v0.9.1 não altera a arquitetura estatística da v0.9. Ela congela a última base pré-primeiro-turno em 3 de outubro de 2026, incorporando explicitamente os levantamentos finais Datafolha BR-01708/2026 e Quaest BR-02197/2026. O ajuste final usa 43 levantamentos completos.

A decisão editorial é encerrar aqui a sequência de ajustes: as críticas estruturais que motivaram a revisão foram incorporadas; Student-t, volatilidade variante no tempo ou estruturas de covariância mais ricas ficam fora desta versão por não haver validação histórica suficiente para justificá-las.
