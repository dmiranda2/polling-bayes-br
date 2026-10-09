# polling-bayes-br

> **Nota de 09/10/2026 — segundo turno:** o modelo de primeiro turno v0.9.1 continua preservado para reprodutibilidade. O confronto Lula × Flávio Bolsonaro do segundo turno possui agora um pipeline independente (`src/runoff_nowcast.py`), com viés histórico estimado **exclusivamente de pesquisas de segundos turnos anteriores**, e não da base do primeiro turno. O arquivo `data/manual_second_round_2026.csv` inclui PoderData, Vox Brasil, Datafolha e AtlasIntel. A Atlas é tratada apenas na análise de sensibilidade porque começou a entrevistar antes da votação do primeiro turno. Consulte [desenho e limitações](docs/SECOND_ROUND_DESIGN.md).

**Para reproduzir o retrato de 9 de outubro:**

```bash
python src/historical_second_round.py --out output_second_round_bias --windows 3,7,14
python src/runoff_nowcast.py --as-of 2026-10-09
```

A primeira etapa usa a base histórica Poder360/Base dos Dados e o segundo comando preserva fallback explícito se não houver histórico validado. Os valores são nowcast presente, **não** previsão da urna em 25/10.

Agregador experimental de pesquisas nacionais para a eleição presidencial brasileira.

> **Versão atual: v0.9.1**

## Em 30 segundos

O projeto pega as pesquisas nacionais mais recentes, coloca todas na **mesma base de votos válidos** e estima um retrato agregado da corrida eleitoral.

A ideia é simples:

1. cada pesquisa entra com a incerteza compatível com seu tamanho amostral e margem de erro;
2. diferenças persistentes entre institutos são estimadas pelo próprio modelo;
3. todos os candidatos são modelados **em conjunto**.
4. pesquisas mais antigas perdem influência à medida que novas pesquisas aparecem, por meio de um estado latente que evolui no tempo;
5. o modelo separa duas coisas diferentes: **incerteza sobre o consenso das pesquisas** e **erro eleitoral comum a toda a indústria de pesquisas**.

O resultado principal é um **nowcast**: uma estimativa do que as pesquisas, tomadas em conjunto, estão dizendo **agora**.

Ele não deve ser lido como uma previsão infalível da urna.

## Principais características do modelo

O núcleo estatístico do projeto tem as seguintes características:

- **modelo composicional conjunto:** todos os candidatos são ajustados simultaneamente, em vez de um modelo separado para cada um;
- **coordenadas ILR:** a composição de votos é levada ao espaço euclidiano por uma transformação isométrica, seguindo a geometria de dados composicionais de [Egozcue et al. (2003)](https://doi.org/10.1023/A:1023818214614);
- **hiperparâmetros estimados:** seis escalas de variância do processo temporal, efeitos de instituto e ruído extra são estimadas por REML, em vez de escolhidas manualmente;
- **efeitos de instituto aprendidos no ciclo atual:** não há transferência fixa do viés observado em 2018/2022 para 2026;
- **duas incertezas separadas:** o modelo distingue a incerteza sobre a média latente das pesquisas da incerteza eleitoral comum à indústria;
- **baseline explícito:** o backtest sempre compara o modelo com uma média simples das mesmas pesquisas, para verificar se a sofisticação realmente acrescenta informação;
- **camada de dados preservada:** a auditoria de base válida/total, identidade de instituto, cédula, datas e casos ambíguos continua sendo parte central do projeto.

---

## O que entra no modelo

O pipeline trabalha com pesquisas nacionais de primeiro turno e mantém uma trilha de auditoria para cada levantamento.

Antes de qualquer ajuste estatístico, o código verifica:

- instituto e identidade da pesquisa;
- datas de campo e divulgação;
- tamanho da amostra e margem de erro, quando disponíveis;
- se a pesquisa publicou **votos totais** ou **votos válidos**;
- presença de branco, nulo, indecisos e outras respostas não válidas;
- composição da cédula usada na pesquisa;
- candidatos fora da cédula vigente;
- pesquisas incompletas ou estruturalmente ambíguas.

### Fontes de dados

A versão atual usa, entre outras fontes:

- **2026:** Mural dos Candidatos + suplementos manuais auditáveis para levantamentos ausentes ou quebrados na fonte automática;
- **2022:** Nexo Dados, enriquecido com metadados do TSE;
- **2018:** Poder360 via base histórica do Pindograma;
- **metadados:** Portal de Dados Abertos do TSE / PesqEle;
- **cédula de 2026:** arquivo curado `data/candidate_status_2026.csv`.

Os suplementos manuais só substituem uma linha automática quando `manual_override=true`.

---

## O que o modelo entrega

A saída principal contém, para cada candidato:

- estimativa central em votos válidos;
- IC de 80% e 95% para a **média latente das pesquisas**;
- número de pesquisas utilizadas;
- última data de pesquisa incorporada;
- opcionalmente, uma faixa eleitoral mais larga que adiciona um termo externo de erro sistemático comum às pesquisas.

Essa distinção é importante:

### 1. Incerteza do polling nowcast

É a incerteza sobre o consenso subjacente às pesquisas disponíveis.

Ela responde à pergunta:

> “Se pudéssemos observar muitas pesquisas semelhantes hoje, qual seria a média latente indicada por elas?”

### 2. Incerteza eleitoral

Pesquisas diferentes podem compartilhar o **mesmo erro** — por exemplo, uma dificuldade comum em medir determinado grupo de eleitores. Esse erro não pode ser identificado simplesmente acumulando mais pesquisas do mesmo ciclo. Essa separação entre variância amostral, viés e erro não amostral é motivada pela literatura de *total survey error*, em particular por [Shirani-Mehr et al. (2018)](https://doi.org/10.1080/01621459.2018.1448823).

Por isso o modelo permite adicionar uma camada externa de erro eleitoral. No `config.json` atual, a escala marginal aproximada usada para os dois líderes é de **2,5 pontos percentuais**.

Essa camada é uma hipótese externa, não algo “aprendido” a partir de apenas 2018 e 2022.

Os **2,5 p.p.** são um prior externo baseado na literatura internacional; em uma próxima versão, essa escala será estimada especificamente a partir de dados brasileiros.

---

# Como funciona tecnicamente

## 1. A composição é modelada de uma vez

Se uma pesquisa reporta a composição

\[
\hat p_i=(p_{i1},\ldots,p_{iK}),\qquad \sum_{k=1}^K p_{ik}=1,
\]

não ajustamos um modelo independente para cada candidato.

Isso evita dois problemas comuns:

- previsões marginais que não somam 100%;
- correlações entre candidatos adicionadas apenas depois do ajuste.

O modelo trabalha diretamente no simplex de probabilidades.

## 2. Transformação ILR

Após uma pequena correção de continuidade dependente do tamanho efetivo da amostra, a composição é transformada para coordenadas **ILR** (*isometric log-ratio*):

\[
y_i = H^\top \log p_i \in \mathbb R^{K-1},
\]

onde \(H\) é uma base ortonormal de Helmert para o subespaço de soma zero.

A grande vantagem é que o problema composicional vira um problema gaussiano comum em \(\mathbb R^{K-1}\), sem privilegiar arbitrariamente um candidato como categoria de referência. A transformação ILR usada aqui segue [Egozcue et al. (2003)](https://doi.org/10.1023/A:1023818214614).

## 3. Estado latente + efeito de instituto

No espaço ILR, o modelo é

\[
y_i = \theta(t_i) + h_{j(i)} + \varepsilon_i,
\]

onde:

- \(\theta(t)\) é o consenso latente das pesquisas no tempo \(t\);
- \(h_j\) é o *house effect* do instituto \(j\);
- \(\varepsilon_i\) é o erro específico da pesquisa.

O estado evolui como um passeio aleatório gaussiano contínuo no tempo:

\[
\theta(t)-\theta(s)\sim N\!\left(0,(t-s)Q\right).
\]

Os efeitos de instituto seguem

\[
h_j\sim N(0,\Sigma_h),
\]

e a observação satisfaz

\[
\varepsilon_i\sim N(0,R_i+\Omega).
\]

Aqui:

- \(R_i\) vem da covariância multinomial da própria pesquisa, transportada para o espaço ILR pelo método delta;
- \(\Omega\) representa dispersão adicional entre levantamentos além do erro amostral.

## 4. Poucos hiperparâmetros

O núcleo do nowcast evita parâmetros manuais desse tipo.

Para evitar o extremo oposto — uma matriz de covariância enorme e mal identificada — usamos uma estrutura parcimoniosa com duas escalas por componente:

- uma escala para o balanço entre os dois líderes;
- outra compartilhada pelos demais balanços composicionais.

Assim, \(Q\), \(\Sigma_h\) e \(\Omega\) somam **seis escalas de variância**.

Essas escalas são estimadas por **máxima verossimilhança marginal restrita (REML)** em cada ajuste, na tradição de [Patterson & Thompson (1971)](https://doi.org/10.1093/biomet/58.3.545).

## 5. Volta ao simplex

Como ILR é uma transformação bijetiva entre o interior do simplex e \(\mathbb R^{K-1}\), depois do ajuste basta aplicar a transformação inversa:

\[
p_t=\operatorname{ilr}^{-1}(\theta_t).
\]

A soma 100% é respeitada por construção. Não existe mais uma etapa posterior de “projetar” candidatos independentes no simplex.

---

# Efeito de instituto

O modelo admite que institutos diferentes possam apresentar desvios persistentes em direções diferentes.

Esses efeitos são estimados **junto com o estado eleitoral** e regularizados em direção a zero. Institutos com pouco dado disponível não recebem automaticamente grandes correções.

---

# Backtest

O projeto possui backtest temporal para os primeiros turnos de **2018 e 2022**.

Os cortes usados são:

- 30 dias;
- 21 dias;
- 14 dias;
- 7 dias;
- 3 dias;
- 1 dia antes da eleição.

Em cada corte, o modelo só vê pesquisas que poderiam ser consideradas disponíveis naquele momento.

Também é calculado um baseline deliberadamente simples: a média das pesquisas completas na mesma janela.

No cache usado no desenvolvimento, a média dos doze cortes foi aproximadamente:

| Método | MAE médio | RMSE médio |
|---|---:|---:|
| **modelo** | **3,37 p.p.** | **4,27 p.p.** |
| média simples | 5,00 p.p. | 6,41 p.p. |

Esses valores são **diagnóstico em apenas dois ciclos**, não uma validação suficiente para aprender uma distribuição completa de erro eleitoral. Como referência externa sobre a escala e a heterogeneidade histórica dos erros de pesquisas eleitorais, ver [Jennings & Wlezien (2018)](https://doi.org/10.1038/s41562-018-0315-6).

---



# Estrutura do projeto

```text
polling-bayes-br/
├── config.json
├── data/
│   ├── candidate_status_2026.csv
│   ├── manual_2026.csv
│   ├── pollster_aliases.csv
│   └── tse_2022_field_dates.csv
├── src/
│   ├── backtest.py
│   ├── candidate_status.py
│   ├── common.py
│   ├── composition.py
│   ├── fetch_data.py
│   ├── model.py
│   ├── plot.py
│   ├── preprocess.py
│   ├── report.py
│   └── run.py
├── tests/
│   ├── test_identity.py
│   ├── test_v08.py
│   └── test_v09.py
└── requirements.txt
```

O cache grande `data/polls_master.csv` e arquivos gerados em `output/` podem ser reconstruídos e não precisam ser versionados.

---

# Instalação

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Atualização completa das fontes

```bash
python src/run.py --as-of YYYY-MM-DD
```

## Reusar o cache local

```bash
python src/run.py --no-fetch --as-of YYYY-MM-DD
```

## Testes

```bash
PYTHONPATH=src pytest -q
```

A suíte corrente contém **22 testes**.

---

# Principais saídas

- `output/nowcast_latest.csv` — estado atual dos principais candidatos;
- `output/nowcast_all_candidates.csv` — composição completa;
- `output/nowcast_trajectory.csv` — evolução temporal do nowcast;
- `output/model_hyperparameters.csv` — seis escalas REML;
- `output/house_effects_all.csv` — efeitos posteriores de instituto;
- `output/pollster_effect_audit.csv` — resumo auditável dos efeitos;
- `output/polls_used_2026.csv` — observações efetivamente usadas;
- `output/vote_basis_audit.csv` — classificação total/válido/ambíguo;
- `output/current_composition_audit.csv` — auditoria da composição;
- `output/pollster_identity_audit.csv` — identidade dos institutos;
- `output/backtest_temporal.csv` — backtest detalhado;
- `output/backtest_metrics.csv` — métricas agregadas;
- `output/external_error_prior.csv` — hipótese externa usada na faixa eleitoral;
- `output/report.md` — relatório legível.

---

# Desenvolvimento e revisão do código

A implementação foi **desenvolvida e refatorada com GPT (OpenAI)** e depois submetida a **revisão adversarial independente no Claude (Anthropic)**. 

Essa revisão por modelos diferentes é uma etapa adicional de checagem, não uma verificação formal. O repositório mantém testes automatizados, backtests, auditorias intermediárias e saídas reproduzíveis para permitir inspeção humana do pipeline.

---

# Referências metodológicas

O modelo não é uma implementação literal de um único artigo. Ele combina ideias de análise composicional, modelos gaussianos de estado, estimação de componentes de variância e literatura sobre erro de pesquisas.

### Coordenadas ILR e dados composicionais

Egozcue, J. J., Pawlowsky-Glahn, V., Mateu-Figueras, G. & Barceló-Vidal, C. (2003). **Isometric Logratio Transformations for Compositional Data Analysis.** *Mathematical Geology*, 35, 279–300.  
https://doi.org/10.1023/A:1023818214614

### Estimação REML

Patterson, H. D. & Thompson, R. (1971). **Recovery of inter-block information when block sizes are unequal.** *Biometrika*, 58(3), 545–554.  
https://doi.org/10.1093/biomet/58.3.545

### Erro de pesquisas além da margem amostral

Shirani-Mehr, H., Rothschild, D., Goel, S. & Gelman, A. (2018). **Disentangling Bias and Variance in Election Polls.** *Journal of the American Statistical Association*, 113(522), 607–614.  
https://doi.org/10.1080/01621459.2018.1448823

### Erros eleitorais em diferentes eleições e países

Jennings, W. & Wlezien, C. (2018). **Election polling errors across time and space.** *Nature Human Behaviour*, 2, 276–283.  
https://doi.org/10.1038/s41562-018-0315-6

---

# Nota de interpretação

Este é um projeto estatístico experimental e auditável. O objetivo é organizar informação de pesquisas de maneira coerente e explicitar a incerteza — não substituir a votação real nem produzir certezas onde os dados não permitem. Use com moderação!
