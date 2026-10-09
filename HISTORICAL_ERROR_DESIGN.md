# Historical common polling error — experimental design

This document describes the experimental calibration on branch `v1-historical-error`.
It is intentionally **not wired into the published nowcast** until the validation gates below are passed.

## Goal

Replace the ad hoc external layer centered at zero with a Brazil-specific estimate of the
**election-level error shared by polling institutes**, while keeping pollster-specific effects
and ordinary sampling/poll noise separate.

The primary estimand is the leading-pair balance. Across presidential first rounds from 2002
through 2022 the reference direction is defined consistently as

> PT candidate minus the principal rival that reached the second round.

That gives Lula–Serra (2002), Lula–Alckmin (2006), Dilma–Serra (2010), Dilma–Aécio (2014),
Haddad–Bolsonaro (2018), and Lula–Bolsonaro (2022). The direction therefore has an explicit,
reproducible meaning and can be mapped to Lula–Flávio Bolsonaro in 2026.

## Why the leading-pair ILR coordinate

The current model orders the two leading candidates first and uses a Helmert ILR basis. Its
first coordinate is exactly

\[
z=\frac{1}{\sqrt 2}\log\frac{p_1}{p_2}.
\]

So a historical calibration of the error in this coordinate can be inserted into the current
model without inventing a separate scale or a post-hoc correction.

For poll `i`, institute `j`, election `e`, define

\[
y_{eji}=z^{\rm poll}_{eji}-z^{\rm result}_{e}.
\]

The experimental model is

\[
y_{eji}=\mu+b_e+h_j+\varepsilon_{eji},
\]

with

\[
b_e\sim N(0,\tau_e^2),\qquad
h_j\sim N(0,\tau_h^2),\qquad
\varepsilon_{eji}\sim N(0,s_{eji}^2+\tau_p^2).
\]

Here `b_e` is the common election error, `h_j` is persistent pollster error, `s_eji` is the
sampling variance implied by the poll, and `tau_p` is residual poll-level dispersion.
All three variance components are estimated by marginal likelihood / REML.

For a future election the poll-minus-result common error is predicted as

\[
y_{\rm new}\sim N(\hat\mu,\hat\tau_e^2+\operatorname{Var}(\hat\mu)).
\]

Because the model is expressed as poll minus result, the correction applied to the polling
state would have the opposite sign.

## Data

### Polls

Primary source: Poder360 historical polling data distributed by Base dos Dados
(`br_poder360_pesquisas.microdados`), which covers the period from 2000 onward.
The raw table is downloaded from Base dos Dados' public one-click snapshot and is not vendored
into the repository.

The extraction is deliberately fail-closed:

- national polls only;
- President, first round;
- stimulated voting intention only;
- **election-day observations are excluded** because the historical source does not reliably distinguish a final pre-election poll from an exit poll;
- candidate rows only;
- target pair must both be present;
- target-pair shares must be positive and finite;
- total-vote and valid-vote scenarios are comparable for the leading-pair ILR because the common
  renormalization cancels in the ratio; published valid-vote scenarios are preferred when both exist;
- one scenario is chosen deterministically per poll;
- only the latest poll from each institute is retained in each election/window, avoiding
  pseudo-replication from tracking polls.

The primary window is **7 days before election day**. Windows of **3 and 14 days** are retained
as pre-specified sensitivity analyses; the best-looking window is not chosen after seeing the
2026 answer.

### Election results

Official first-round valid-vote counts are stored in
`data/presidential_first_round_results.csv`. Percentages and result ILR coordinates are derived
from counts rather than rounded published percentages.

## Directional mean: two competing models

With only six presidential cycles, a non-zero historical mean can easily be driven by one
unusual election. Therefore two models are fit from the start:

- `zero_mean`: `mu = 0`;
- `free_mean`: `mu` estimated from the Brazilian history.

A directional correction is allowed into the production model only if the free-mean model has
better whole-election out-of-sample performance and the sign is stable to window and jackknife
sensitivity.

## Validation

The unit of cross-validation is the **whole election**, never an individual poll.
For each historical election:

1. remove every poll from that election;
2. fit the historical error model to all other elections;
3. estimate pollster effects using only the training elections;
4. predict the common error of the omitted election;
5. compare the prediction with the held-out poll consensus after training-only pollster
   adjustment.

Reported diagnostics include predictive log score, 80%/95% coverage, and standardized error.

## Acceptance gates before touching the current nowcast

The historical layer will remain experimental unless all of these hold:

1. the pipeline passes unit tests and source/audit checks;
2. results are qualitatively stable for 3-, 7-, and 14-day windows;
3. no single election determines the sign or scale (jackknife sensitivity);
4. whole-election LOO predictive performance is at least competitive with the present
   zero-centered external prior;
5. a non-zero mean is used only if the free-mean model improves LOO performance rather than
   merely fitting the six observed cycles better;
6. the original `main` branch remains reproducible and unchanged until the experiment is
   accepted.

## Deliberate non-features in the first experiment

No time-decay parameter, changing variance by era, or full cross-election ILR covariance is
estimated initially. Six elections do not justify that many degrees of freedom. In particular,
**2022 receives no extra weight merely for being the most recent cycle**.

Because 2022 may be atypical, Student-t tails are included only as a **second-stage diagnostic
sensitivity** (fixed df = 3, 4, 5), alongside the Gaussian fit. They do not enter the production
nowcast unless whole-election validation supports that choice.


## 2022 influence check

The design explicitly treats 2022 as a potentially influential cycle rather than assuming it is
typical. The report therefore includes:

- a fit with all six elections;
- a fit excluding 2022;
- full leave-one-election-out validation;
- jackknife estimates of the historical mean and election-level scale;
- Normal versus Student-t robust sensitivity for the election-level common errors.

A directional correction is rejected if its sign or magnitude depends materially on retaining
2022.

## Related implementation

The public R package `agregR` also uses Poder360 historical data for empirical polling priors.
Its current historical helper uses the last poll per institute in a five-day window and maps
current left/right candidacies to the previous election. That is useful as an independent
cross-check of the source and the general idea, but the model here differs by using all
presidential cycles from 2002–2022 and explicitly separating election-, pollster-, and
poll-level components with whole-election cross-validation.