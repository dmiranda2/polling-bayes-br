"""Render the trailing-publication consensus separately from conditioned scenarios."""
from pathlib import Path
import os,json
os.environ.setdefault('MPLCONFIGDIR','/tmp/polling-oct21-mpl')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter
from matplotlib.patches import FancyBboxPatch
import pandas as pd
ROOT=Path(__file__).resolve().parent
c=json.loads((ROOT/'config_update.json').read_text());d=pd.read_csv(ROOT/'valores_diarios.csv',float_precision='round_trip')
m=pd.read_csv(ROOT/'model_comparison_core_2026-10-21.csv',float_precision='round_trip');m=m[m.historical_window.eq('7:14')]
recent=[s for s in m.selection.unique() if s!='full'][0]
dark,muted,red,blue,accent='#172943','#536477','#c5364e','#2469a5','#8a5611'
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':12,'axes.spines.top':False,'axes.spines.right':False,'axes.spines.left':False,'axes.spines.bottom':False})
cutoff=pd.Timestamp(c['cutoff_brt']).strftime('%d/%m/%Y, %Hh%M')
fig=plt.figure(figsize=(11.2,7.7),facecolor='#f7f9fc')
fig.text(.07,.95,'Segundo turno',fontsize=27,fontweight='bold',color=dark,va='top')
fig.text(.07,.878,'Evolução das pesquisas',fontsize=23,fontweight='bold',color=dark,va='top')
fig.text(.07,.795,'Média móvel ponderada de 3 dias · 08–21 de outubro de 2026',fontsize=13.7,color=muted,va='top')
fig.text(.07,.729,'● Lula',fontsize=14.5,fontweight='bold',color=red)
fig.text(.265,.729,'● Flávio Bolsonaro',fontsize=14.5,fontweight='bold',color=blue)
ax=fig.add_axes([.09,.245,.75,.435],facecolor='white');dates=pd.to_datetime(d.date);first,last=dates.min(),dates.max()
ax.axhline(50,color='#8995a4',lw=1.15,ls=(0,(4,4)),zorder=1)
for col,color in [('lula_pct',red),('flavio_pct',blue)]:
 ax.plot(dates,d[col],color=color,lw=2.7,marker='o',markersize=6,markeredgecolor='white',markeredgewidth=.8,zorder=3)
 ax.text(last+pd.Timedelta(days=.20),d.iloc[-1][col],f'{d.iloc[-1][col]:.2f}%'.replace('.',','),fontsize=16.5,fontweight='bold',color=color,va='center')
ax.set_ylim(45.5,54.5);ax.set_yticks([46,48,50,52,54]);ax.yaxis.set_major_formatter(FuncFormatter(lambda x,pos:f'{x:.0f}%'))
ax.set_xlim(first-pd.Timedelta(days=.15),last+pd.Timedelta(days=1.65));ax.set_xticks(dates);ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))
ax.tick_params(axis='both',length=0,labelsize=10.0,pad=8,colors=muted);ax.grid(axis='y',color='#e8edf3',lw=.7,zorder=0);ax.set_axisbelow(True)
fig.text(.07,.144,f'Verificação até {cutoff} (BRT) · votos válidos · N={int(d.iloc[-1].n_institutes)} institutos no ponto final',fontsize=10.6,color=muted)
fig.text(.07,.102,'Consenso sem ajuste direcional · calibração histórica 7:14 mantida · últimos 3 dias de divulgação',fontsize=10.2,color=muted)
fig.text(.07,.065,'Pontos até 19/10 preservados no corte original. Não é previsão do resultado nem probabilidade de vitória.',fontsize=9.5,color=muted)
fig.text(.07,.030,'Futura: percentuais confirmados em reportagens; relatório primário não acessado. Ressalvas por fonte no pacote.',fontsize=9.2,color=muted)
fig.savefig(ROOT/'medias_moveis_3_dias_2026-10-21.png',dpi=220,facecolor=fig.get_facecolor());plt.close(fig)

fig=plt.figure(figsize=(13.2,9.2),facecolor='#f7f9fc');ax=fig.add_axes([0,0,1,1]);ax.set_axis_off();ax.set_xlim(0,1);ax.set_ylim(0,1)
fig.text(.05,.95,'Segundo turno · comparação das três saídas',fontsize=25,fontweight='bold',color=dark,va='top')
fig.text(.05,.902,f'21/10/2026 · verificação até {pd.Timestamp(c["cutoff_brt"]).strftime("%Hh%M")} BRT · calibração histórica 7:14 inalterada',fontsize=13,color=muted,va='top')
fig.text(.05,.857,'Cada par mostra Lula / Flávio Bolsonaro, em % dos votos válidos.',fontsize=12,color=muted,va='top')
fig.text(.05,.816,'Lula',fontsize=12,fontweight='bold',color=red);fig.text(.098,.816,'/',fontsize=12,color=muted);fig.text(.110,.816,'Flávio Bolsonaro',fontsize=12,fontweight='bold',color=blue)

def pair(x,y,row,quantity):
 fig.text(x,y,f'{row[quantity+"_lula_pct"]:.4f}'.replace('.',','),color=red,fontsize=15,fontweight='bold',va='center')
 fig.text(x+.087,y,'/',color=muted,fontsize=12,va='center')
 fig.text(x+.108,y,f'{row[quantity+"_flavio_pct"]:.4f}'.replace('.',','),color=blue,fontsize=15,fontweight='bold',va='center')
fig.text(.05,.754,'Seleção / modo',fontsize=12,color=muted,fontweight='bold')
fig.text(.48,.754,'Consenso das pesquisas',fontsize=13,color=dark,fontweight='bold')
fig.text(.745,.754,'Cenário condicionado',fontsize=13,color=dark,fontweight='bold')
fig.text(.48,.724,'polling_*',fontsize=10.5,color=muted);fig.text(.745,.724,'counterfactual_*',fontsize=10.5,color=muted)
for sel,y,label in [('full',.664,'Seleção completa'),(recent,.519,'Divulgações 19–21/10')]:
 n=int(m[m.selection.eq(sel)].iloc[0].n_surveys)
 fig.text(.05,y,label+f'\nN={n} institutos',fontsize=12,color=dark,fontweight='bold',va='center')
 for mode,off,lbl in [('none',0,'Sem ajuste'),('second_round_history',.052,'Ajustes históricos aceitos')]:
  r=m[m.selection.eq(sel)&m.bias_mode.eq(mode)].iloc[0]
  fig.text(.445,y-off,lbl,fontsize=11,color=muted,ha='right',va='center');pair(.48,y-off,r,'polling');pair(.745,y-off,r,'counterfactual')
 ax.plot([.05,.95],[y-.092,y-.092],color='#dbe3ed',lw=1)
box=FancyBboxPatch((.036,.164),.928,.222,boxstyle='round,pad=0.008,rounding_size=0.008',transform=fig.transFigure,facecolor='#fff3df',edgecolor='#d7b274',linewidth=1);fig.add_artist(box)
fig.text(.05,.356,'EXPERIMENTAL · MÉDIA LIVRE 2T · NÃO VALIDADO',fontsize=15,fontweight='bold',color=accent)
fig.text(.05,.321,'A média livre perde na validação por eleição inteira. Não deve ser tratada como previsão validada.',fontsize=11,color=accent)
for sel,y,label in [('full',.258,'Seleção completa'),(recent,.203,'Divulgações 19–21/10')]:
 r=m[m.selection.eq(sel)&m.bias_mode.eq('experimental_free_mean_2t')].iloc[0]
 fig.text(.05,y,label+f' · N={int(r.n_surveys)}',fontsize=12,color=accent,va='center');pair(.48,y,r,'polling');pair(.745,y,r,'counterfactual')
fig.text(.05,.121,'O gráfico de evolução usa somente o consenso sem ajuste da janela móvel, não os cenários condicionados.',fontsize=10.8,color=muted)
fig.text(.05,.087,'Cenários condicionados à hipótese de eleição hoje; não são previsões para 25/10 nem probabilidades de vitória.',fontsize=10.3,color=muted)
fig.text(.05,.053,'Futura e parte dos válidos confirmados na imprensa, não em PDF primário. Proveniência detalhada no pacote.',fontsize=10.1,color=muted)
fig.text(.05,.024,'Mesmos parâmetros · 30.000 draws · seed 418 · sem transferência de viés de primeiro turno',fontsize=9.7,color=muted)
fig.savefig(ROOT/'comparativo_tres_saidas_2026-10-21.png',dpi=180,facecolor=fig.get_facecolor());plt.close(fig)
print('Two charts generated from validated numerical outputs.')
