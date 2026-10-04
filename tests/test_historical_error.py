import numpy as np
import pandas as pd

from historical_error import (
    fit_historical_error,
    jackknife_parameters,
    loo_validate,
    prepare_historical_final_polls,
)


def test_prepare_selects_valid_scenario_and_latest_poll():
    results = pd.DataFrame([{
        "election_year": 2022,
        "election_date": pd.Timestamp("2022-10-02"),
        "reference_candidate": "Lula",
        "opponent_candidate": "Jair Bolsonaro",
        "reference_aliases": "Lula",
        "opponent_aliases": "Bolsonaro|Jair Bolsonaro",
        "reference_share": .4843,
        "opponent_share": .4320,
        "result_pair_ilr": np.log(.4843/.4320)/np.sqrt(2),
        "result_margin_pp": 5.23,
    }])
    rows=[]
    def add(pid, scen, date, pollster, tipo_voto, vals, n=2000, moe=2.2):
        for cand,pct in vals.items():
            rows.append(dict(id_pesquisa=pid,ano=2022,sigla_uf=np.nan,cargo="Presidente",
                data=date,instituto=pollster,tipo="Estimulada",turno=1,tipo_voto=tipo_voto,
                id_cenario=scen,nome_candidato=cand,condicao=0,percentual=pct,
                quantidade_entrevistas=n,margem_mais=moe))
    add("a","1","2022-09-29","X","Votos Totais",{"Lula":45,"Jair Bolsonaro":40,"Ciro":5})
    add("a","2","2022-09-29","X","Votos Válidos",{"Lula":50,"Jair Bolsonaro":44,"Ciro":6})
    add("b","1","2022-10-01","X","Votos Totais",{"Lula":48,"Bolsonaro":43,"Ciro":5})
    raw=pd.DataFrame(rows)
    out=prepare_historical_final_polls(raw,results,window_days=7)
    assert len(out)==1
    assert out.iloc[0].poll_id=="b"
    assert abs(out.iloc[0].reference_poll_valid_pct-50.0)<1e-8
    assert abs(out.iloc[0].opponent_poll_valid_pct-(43/96*100))<1e-8


def test_fit_recovers_signal_on_synthetic_panel():
    rng=np.random.default_rng(42)
    elections=np.arange(2002,2026,4)
    houses=["A","B","C","D","E"]
    mu=.035; tau_e=.045; tau_h=.025; tau_p=.015
    e_eff={e:rng.normal(0,tau_e) for e in elections}
    h_eff={h:rng.normal(0,tau_h) for h in houses}
    rows=[]
    for e in elections:
        for h in houses:
            sv=.0002
            y=mu+e_eff[e]+h_eff[h]+rng.normal(0,np.sqrt(sv+tau_p**2))
            rows.append(dict(election_year=e,pollster=h,pair_ilr_error=y,sampling_var_ilr=sv))
    d=pd.DataFrame(rows)
    fit=fit_historical_error(d,free_mean=True)
    assert abs(fit.mu-mu)<.08
    assert fit.election_sd>0
    assert fit.house_sd>0
    assert fit.poll_sd>0
    loo=loo_validate(d,free_mean=True)
    assert len(loo)==len(elections)
    assert np.isfinite(loo.log_score).all()


def test_zero_mean_fit_is_exactly_centered():
    d=pd.DataFrame({
        "election_year":[2002,2002,2006,2006,2010,2010],
        "pollster":["A","B","A","B","A","B"],
        "pair_ilr_error":[.02,.01,-.01,.0,.03,.01],
        "sampling_var_ilr":[.001]*6,
    })
    fit=fit_historical_error(d,free_mean=False)
    assert fit.mu==0.0


def test_jackknife_omits_one_whole_election():
    d=pd.DataFrame({
        "election_year":[2002,2002,2006,2006,2010,2010,2014,2014],
        "pollster":["A","B"]*4,
        "pair_ilr_error":[.02,.01,-.01,.0,.03,.01,.04,.02],
        "sampling_var_ilr":[.001]*8,
    })
    out=jackknife_parameters(d,free_mean=True)
    assert set(out["omitted_election"])=={2002,2006,2010,2014}
    assert (out["n_elections_train"]==3).all()
    assert np.isfinite(out["predictive_new_election_error_sd_ilr"]).all()