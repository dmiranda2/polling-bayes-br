"""Offline data-only update. Numerical model and historical calibration are frozen."""
from pathlib import Path
import csv,io,json,sys,hashlib,os,subprocess,math,re,unicodedata
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parent
PRIOR=ROOT/'prior_2026-10-19_1017'
REPO=ROOT.parents[1]
MODEL_SRC=REPO/'src'
sys.path.insert(0,str(MODEL_SRC))
from runoff_nowcast import _calibrate_historical,read_current_polls,estimate
C=json.loads((ROOT/'config_update.json').read_text())
NEW=json.loads((ROOT/'new_polls.json').read_text())
ASOF=C['as_of']; MODES=['none','second_round_history','experimental_free_mean_2t']

def write_inputs():
    old=(PRIOR/'data/input_polls.csv').read_bytes()
    cols=pd.read_csv(PRIOR/'data/input_polls.csv',nrows=0).columns.tolist()
    buf=io.StringIO(); w=csv.DictWriter(buf,fieldnames=cols,lineterminator='\n')
    for p in NEW:
        for candidate,key in [('Lula','lula'),('Flávio Bolsonaro','flavio')]:
            row={k:p.get(k,'') for k in cols}
            row.update(election_year=2026,round=2,scenario='2º turno',candidate=candidate,pct=p.get(key+'_total',''),pct_valid=p[key+'_valid'],vote_basis=p.get('vote_basis','published_valid'))
            w.writerow(row)
    (ROOT/'data/input_polls.csv').write_bytes(old+buf.getvalue().encode())
    raw=pd.read_csv(ROOT/'data/input_polls.csv')
    assert len(raw)==50+2*len(NEW) and not raw.duplicated(['poll_id','candidate']).any()
    assert np.allclose(raw.groupby('poll_id').pct_valid.sum(),100,atol=1e-12,rtol=0)
    old_sources=pd.read_csv(PRIOR/'sources.csv')
    sources=[]
    for p in NEW:
        row=dict(p); row.update(vote_basis=p.get('vote_basis','published_valid'),verified_cutoff_brt=C['cutoff_brt'])
        sources.append(row)
    pd.concat([old_sources,pd.DataFrame(sources)],ignore_index=True).to_csv(ROOT/'sources.csv',index=False)
    for day in pd.date_range('2026-10-20',ASOF):
        ds=day.date().isoformat();lo=(day-pd.Timedelta(days=2)).date().isoformat()
        raw[raw.publish_date.between(lo,ds)].to_csv(ROOT/'daily_inputs'/f'{ds}.csv',index=False)
    return raw

def calibrate():
    cals={w:_calibrate_historical(ROOT/'data/historical_poll_errors.csv',ROOT/'data/presidential_second_round_results.csv',w) for w in C['historical_windows']}
    serial={w:{k:v for k,v in c.items() if k!='fit'} for w,c in cals.items()}
    assert serial==json.loads((PRIOR/'calibration_all_windows.json').read_text()),'Historical calibration changed'
    (ROOT/'calibration_all_windows.json').write_text(json.dumps(serial,ensure_ascii=False,indent=2)+'\n')
    return cals

def daily(cals):
    rows=[];res=[];weights=[]
    for day in pd.date_range('2026-10-08',ASOF):
        ds=day.date().isoformat();lo=(day-pd.Timedelta(days=2)).date().isoformat()
        s=read_current_polls(ROOT/'daily_inputs'/f'{ds}.csv',ds)
        r,u=estimate(s,cals['7:14'],ds,draws=C['draws'],seed=C['seed'],bias_mode='none')
        assert u.house_mean_applied_ilr.eq(0).all() and r.mean_common_shift_applied_ilr.eq(0).all()
        u['as_of']=ds;u['window_start']=lo;u['window_end']=ds
        u['weight_share_pct']=100/u.obs_var_ilr/(1/u.obs_var_ilr).sum()
        assert abs(u.weight_share_pct.sum()-100)<1e-10
        assert u.publish_date.between(lo,ds).all() and u.field_end.le(ds).all()
        assert u.field_start.gt('2026-10-04').all() and u.pollster.is_unique
        w=1/u.obs_var_ilr.to_numpy(float);center=100/(1+np.exp(-math.sqrt(2)*np.average(u.z_poll_ilr,weights=w)))
        rows.append(dict(date=ds,window_start=lo,n_institutes=len(s),lula_pct=r.iloc[0].polling_lula_pct,flavio_pct=r.iloc[0].polling_flavio_pct,analytic_weighted_location_lula_pct=center,pollsters=' | '.join(sorted(s.pollster)),poll_ids=' | '.join(sorted(s.poll_id)),bias_mode='none',plotted_quantity='polling_consensus'))
        res.append(r);weights.append(u)
    d=pd.DataFrame(rows);d.to_csv(ROOT/'valores_diarios.csv',index=False)
    # Freeze the exact serialized historical observations, not only their rounding.
    old=(PRIOR/'valores_diarios.csv').read_bytes().splitlines(keepends=True)
    assert old==(ROOT/'valores_diarios.csv').read_bytes().splitlines(keepends=True)[:len(old)]
    pd.concat(res,ignore_index=True).to_csv(ROOT/'full_model_outputs.csv',index=False)
    ww=pd.concat(weights,ignore_index=True);ww.to_csv(ROOT/'daily_weights.csv',index=False)
    ww[ww.as_of.eq(ASOF)].to_csv(ROOT/'latest_weights.csv',index=False)
    assert np.allclose(d.lula_pct+d.flavio_pct,100,atol=1e-12,rtol=0)
    return d,ww

def run_models(cals):
    rows=[];weights=[];recent='publication_'+(pd.Timestamp(ASOF)-pd.Timedelta(days=2)).strftime('%d')+'_'+pd.Timestamp(ASOF).strftime('%d')
    selections=[('full',ROOT/'data/input_polls.csv'),(recent,ROOT/'daily_inputs'/f'{ASOF}.csv')]
    for window,cal in cals.items():
        for selection,path in selections:
            surveys=read_current_polls(path,ASOF)
            for mode in MODES:
                if mode=='experimental_free_mean_2t' and cal.get('free_mu_ilr') is None:
                    rows.append(pd.DataFrame([dict(historical_window=window,selection=selection,bias_mode=mode,n_surveys=len(surveys),execution_status='not_estimable_insufficient_history',reason='7:10 has 8 polls / 3 elections; nowcast requires 12 / 4; free mean unavailable')]))
                    continue
                r,u=estimate(surveys,cal,ASOF,draws=C['draws'],seed=C['seed'],bias_mode=mode)
                r.insert(0,'historical_window',window);r.insert(1,'selection',selection);r['execution_status']='executed'
                u['historical_window']=window;u['selection']=selection;u['weight_share_pct']=100/u.obs_var_ilr/(1/u.obs_var_ilr).sum()
                assert abs(u.weight_share_pct.sum()-100)<1e-10
                rows.append(r);weights.append(u)
    d=pd.concat(rows,ignore_index=True); w=pd.concat(weights,ignore_index=True)
    d.to_csv(ROOT/'model_comparison_full_2026-10-21.csv',index=False)
    cols=['historical_window','selection','bias_mode','n_surveys','execution_status','polling_lula_pct','polling_flavio_pct','counterfactual_lula_pct','counterfactual_flavio_pct']
    d[cols].to_csv(ROOT/'model_comparison_core_2026-10-21.csv',index=False)
    w.to_csv(ROOT/'weights_all_calibrations.csv',index=False)
    good=d[d.execution_status.eq('executed')]
    assert len(good)==22 and len(d)==24
    for q in ['polling','counterfactual']: assert np.allclose(good[q+'_lula_pct']+good[q+'_flavio_pct'],100,atol=1e-12,rtol=0)
    assert not good.directional_mean_validated.any()
    for sel,_ in selections:
        m=good[good.historical_window.eq('7:14')&good.selection.eq(sel)].set_index('bias_mode')
        assert m.loc['experimental_free_mean_2t','polling_lula_pct']==m.loc['second_round_history','polling_lula_pct']
    return d,w,recent

def independent(d,w,cals):
    cal=cals['7:14'];fit=cal['fit'];maxw=maxr=maxv=0.
    for row in d.itertuples():
        x=w[w.as_of.eq(row.date)];p=x.lula_valid_pct.to_numpy()/100
        neff=np.maximum(50,np.minimum(x.n_reported/1.5,1.96**2*.25/(x.moe_pp/100)**2))
        z=np.log(p/(1-p))/math.sqrt(2);var=(1/p+1/(1-p))/(2*neff);hv=[]
        for name in x.pollster:
            s=unicodedata.normalize('NFKD',name);s=''.join(c for c in s if not unicodedata.combining(c));s=re.sub(r'\s+',' ',re.sub(r'[^A-Za-z0-9]+',' ',s).strip().upper())
            k=fit.tau_h**2*(fit.pollsters==s).astype(float);hv.append(fit.tau_h**2-float(k@np.linalg.solve(fit.V,k)))
        ov=var+cal['tau_p_ilr']**2+np.array(hv);weight=1/ov
        draw=np.random.default_rng(C['seed']).normal(float(weight@z/weight.sum()),math.sqrt(1/weight.sum()),C['draws'])
        med=float(np.median(100/(1+np.exp(-math.sqrt(2)*draw))))
        maxw=max(maxw,float(np.max(abs(100*weight/weight.sum()-x.weight_share_pct))))
        maxr=max(maxr,abs(med-row.lula_pct));maxv=max(maxv,float(np.max(abs(ov-x.obs_var_ilr))))
    assert maxw<1e-9 and maxr<1e-9 and maxv<1e-12
    return dict(max_independent_weight_difference_pp=maxw,max_independent_result_difference_pp=maxr,max_independent_variance_difference_ilr=maxv)

def main():
    raw=write_inputs();cals=calibrate();d,ww=daily(cals);m,w,recent=run_models(cals)
    assert m[m.historical_window.eq('7:14')&m.selection.eq(recent)&m.bias_mode.eq('none')].iloc[0].polling_lula_pct==d.iloc[-1].lula_pct
    expected_code=json.loads((ROOT/'source_code_sha256.json').read_text())
    for name,digest in expected_code.items(): assert hashlib.sha256((MODEL_SRC/name).read_bytes()).hexdigest()==digest
    for p in (PRIOR/'daily_inputs').glob('*.csv'): assert p.read_bytes()==(ROOT/'daily_inputs'/p.name).read_bytes()
    assert (ROOT/'data/input_polls.csv').read_bytes().startswith((PRIOR/'data/input_polls.csv').read_bytes())
    oldsel=read_current_polls(PRIOR/'data/input_polls.csv','2026-10-19')
    newsel=read_current_polls(ROOT/'data/input_polls.csv',ASOF)
    changes=dict(old_n=len(oldsel),new_n=len(newsel),removed_ids=sorted(set(oldsel.poll_id)-set(newsel.poll_id)),added_ids=sorted(set(newsel.poll_id)-set(oldsel.poll_id)))
    audit={**C,**independent(d,ww,cals),'new_poll_records':len(NEW),'all_poll_records':raw.poll_id.nunique(),'raw_rows':len(raw),'full_selection_change':changes,'recent_n':int(d.iloc[-1].n_institutes),'historical_calibration_exactly_unchanged':True,'prior_daily_points_through_19oct_byte_exact':True,'prior_daily_inputs_byte_exact':True,'previous_rows_byte_exact':True,'model_code_byte_identical':True,'none_directional_shifts_zero':True,'no_lookahead':True,'weights_sum_100':True,'first_round_bias_transfer':False,'experimental_mean_validated':False,'git_publication':False,'executed_model_rows':22,'unavailable_model_rows':2,'data_trends_19oct_after_prior_cutoff_excluded_from_archived_point':True,'excluded':['Gerp tracking 20 October: field-window / registration unresolved','Veritá old 17 October republished: no duplicate','Data Pop BR-01683/2026: Tocantins, not national']}
    env=os.environ.copy();env['PYTHONPATH']=str(MODEL_SRC)
    r=subprocess.run([sys.executable,'-m','pytest','-q'],cwd=REPO,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (ROOT/'logs/pytest.txt').write_text(r.stdout);assert r.returncode==0,r.stdout
    audit['tests_stdout']=r.stdout.strip()
    (ROOT/'audit_update.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    print(d[['date','n_institutes','lula_pct','flavio_pct']].to_string(index=False))
    print(m[m.historical_window.eq('7:14')][['selection','bias_mode','n_surveys','polling_lula_pct','polling_flavio_pct','counterfactual_lula_pct','counterfactual_flavio_pct']].to_string(index=False))
    print(json.dumps(audit,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
