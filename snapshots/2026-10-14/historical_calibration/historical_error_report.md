# Erro histórico de pesquisas — 2º turno

Janela principal: **1:7 dias antes da votação** (intervalo inclusivo).
Primeiro e segundo turnos jamais são combinados no mesmo ajuste.

## Variâncias e viés por janela

| window_label   | model     |   n_polls |   n_elections |   mu_ilr |   tau_e_ilr |   tau_h_ilr |   tau_p_ilr |
|:---------------|:----------|----------:|--------------:|---------:|------------:|------------:|------------:|
| 1:3            | free_mean |        17 |             4 |  -0.0099 |      0.0003 |      0.0003 |      0.0512 |
| 1:3            | zero_mean |        17 |             4 |   0.0000 |      0.0003 |      0.0003 |      0.0496 |
| 1:7            | free_mean |        26 |             4 |  -0.0123 |      0.0166 |      0.0074 |      0.0570 |
| 1:7            | zero_mean |        26 |             4 |   0.0000 |      0.0003 |      0.0003 |      0.0591 |
| 1:14           | free_mean |        27 |             4 |  -0.0117 |      0.0194 |      0.0129 |      0.0545 |
| 1:14           | zero_mean |        27 |             4 |   0.0000 |      0.0045 |      0.0003 |      0.0579 |
| 14:21          | free_mean |        23 |             4 |  -0.0640 |      0.0747 |      0.0487 |      0.0273 |
| 14:21          | zero_mean |        23 |             4 |   0.0000 |      0.0830 |      0.0490 |      0.0286 |

## Validação leave-one-election-out — janela 1:7

|   heldout_year | model     |   pred_mean_ilr |   pred_sd_ilr |   z_error | covered_80   | covered_95   |   delta_log_score_vs_2p5 |
|---------------:|:----------|----------------:|--------------:|----------:|:-------------|:-------------|-------------------------:|
|           2006 | free_mean |         -0.0131 |        0.0524 |    0.6546 | True         | True         |                   0.2650 |
|           2010 | free_mean |         -0.0106 |        0.0486 |   -0.2048 | True         | True         |                   0.4956 |
|           2014 | free_mean |         -0.0081 |        0.0185 |   -3.6463 | False        | False        |                  -4.8516 |
|           2022 | free_mean |         -0.0228 |        0.0358 |    1.0698 | True         | True         |                   0.1758 |
|           2006 | zero_mean |         -0.0011 |        0.0475 |    0.4701 | True         | True         |                   0.4683 |
|           2010 | zero_mean |         -0.0001 |        0.0373 |   -0.5474 | True         | True         |                   0.6309 |
|           2014 | zero_mean |         -0.0081 |        0.0180 |   -3.7623 | False        | False        |                  -5.2496 |
|           2022 | zero_mean |         -0.0000 |        0.0326 |    0.4766 | True         | True         |                   0.7291 |

## Viés e escala — janela 1:7

| model     |   mu_ilr |   mu_sd_ilr |   tau_e_ilr |
|:----------|---------:|------------:|------------:|
| free_mean |  -0.0123 |      0.0164 |      0.0166 |
| zero_mean |   0.0000 |      0.0000 |      0.0003 |

## Auditoria de disponibilidade

| window_label   |   election_year |   rows_in_window |   polls_in_window |   institutes_retained |
|:---------------|----------------:|-----------------:|------------------:|----------------------:|
| 1:3            |            2002 |                0 |                 0 |                     0 |
| 1:3            |            2006 |               11 |                 2 |                     2 |
| 1:3            |            2010 |               30 |                 6 |                     4 |
| 1:3            |            2014 |               25 |                 6 |                     4 |
| 1:3            |            2018 |                0 |                 0 |                     0 |
| 1:3            |            2022 |               37 |                 9 |                     7 |
| 1:7            |            2002 |                0 |                 0 |                     0 |
| 1:7            |            2006 |               23 |                 4 |                     3 |
| 1:7            |            2010 |               50 |                10 |                     5 |
| 1:7            |            2014 |               55 |                12 |                     6 |
| 1:7            |            2018 |                0 |                 0 |                     0 |
| 1:7            |            2022 |               78 |                19 |                    12 |
| 1:14           |            2002 |                0 |                 0 |                     0 |
| 1:14           |            2006 |               29 |                 6 |                     3 |
| 1:14           |            2010 |               70 |                14 |                     5 |
| 1:14           |            2014 |               75 |                16 |                     6 |
| 1:14           |            2018 |                0 |                 0 |                     0 |
| 1:14           |            2022 |              126 |                31 |                    13 |
| 14:21          |            2002 |                0 |                 0 |                     0 |
| 14:21          |            2006 |               12 |                 2 |                     2 |
| 14:21          |            2010 |               25 |                 5 |                     4 |
| 14:21          |            2014 |               30 |                 6 |                     6 |
| 14:21          |            2018 |                0 |                 0 |                     0 |
| 14:21          |            2022 |               50 |                13 |                    11 |

## Restrições

- O dia da eleição é excluído (risco de exit polls).
- As janelas não selecionadas para o ajuste principal são análises separadas.
- O baseline LOO usa escala externa fixa, independente da eleição omitida.
