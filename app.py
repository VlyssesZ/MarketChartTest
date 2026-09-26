import random, uuid, json
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
import requests

st.set_page_config(page_title='Prognoza rynku', page_icon='📈', layout='centered', initial_sidebar_state='collapsed')
BASE=Path(__file__).parent
CASES_PATH=BASE/'cases.csv'; HISTORY_PATH=BASE/'case_history.csv'; OUT_PATH=BASE/'quiz_answers_live.csv'
HISTORY=120; FUTURE=20; NQ=30; SIDEWAYS=2.5
CONF=[50,60,70,80,90,100]
WORDS={
    50:'Równe szanse',
    60:'Nieco bardziej prawdopodobne',
    70:'Prawdopodobne',
    80:'Bardzo prawdopodobne',
    90:'Prawie pewne',
    100:'Pewne',
}

st.markdown('''<style>
.block-container{max-width:860px;padding-top:1rem;padding-bottom:2rem}
h1{font-size:1.75rem!important;margin-bottom:.1rem!important}
h3{font-size:1.08rem!important;margin-top:.55rem!important;margin-bottom:.35rem!important}
div[data-testid="stPlotlyChart"]{margin-top:-.4rem;margin-bottom:-.6rem}
div.stButton>button{min-height:3rem;font-weight:650}
div[data-testid="stProgress"]{margin-bottom:.15rem}
#MainMenu, footer, header{visibility:hidden}
@media (max-width: 640px){
 .block-container{padding:.45rem .55rem 1rem .55rem}
 h1{font-size:1.35rem!important}
 h3{font-size:1rem!important}
 div.stButton>button{min-height:2.7rem;font-size:.88rem;padding:.25rem .25rem}
}
</style>''', unsafe_allow_html=True)

@st.cache_data(show_spinner='Wczytuję wykresy…')
def load_sources():
    meta=pd.read_csv(CASES_PATH)
    hist=pd.read_csv(HISTORY_PATH)
    grouped={cid:g.sort_values('step')['value'].to_numpy(dtype=float) for cid,g in hist.groupby('case_id')}
    cases=[]
    for _,r in meta.iterrows():
        cid=str(r.case_id); y=grouped.get(cid)
        if y is None or len(y)!=HISTORY: continue
        ret=float(r.future_return_pct)
        actual='WZROST' if ret>SIDEWAYS else ('SPADEK' if ret<-SIDEWAYS else 'BOK')
        cases.append({'case_id':cid,'instrument':str(r.instrument),'rating':str(r.rating),
                      'cutoff_date':str(r.cutoff_date),'forecast_end':str(r.forecast_end),
                      'hist_values':y,'future_return':ret,'actual':actual})
    return cases

def make_chart(c):
    y=np.asarray(c['hist_values'],dtype=float)
    yr=max(float(y.max()-y.min()),1); lo=float(y.min()-.05*yr); hi=float(y.max()+.05*yr)
    x=np.arange(-HISTORY+1,1)
    fig=go.Figure(go.Scatter(x=x,y=y,mode='lines',line=dict(width=2),hoverinfo='skip'))
    fig.add_vline(x=0,line_dash='dash',line_width=1)
    fig.add_vrect(x0=0,x1=FUTURE,fillcolor='gray',opacity=.06,line_width=0)
    fig.update_xaxes(range=[-HISTORY,FUTURE],tickmode='array',tickvals=[-120,-80,-40,0,20],
                     ticktext=['−6 mies.','−4','−2','TERAZ','+1 mies.'],fixedrange=True)
    fig.update_yaxes(range=[lo,hi],title=None,fixedrange=True)
    fig.update_layout(height=405,margin=dict(l=8,r=8,t=5,b=25),showlegend=False,
                      paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)')
    return fig

def init_test():
    cases=load_sources(); chosen=random.sample(cases,min(NQ,len(cases)))
    st.session_state.test_id=uuid.uuid4().hex
    st.session_state.variant=random.choice(['A_NUM','B_WORDS'])
    st.session_state.cases=chosen; st.session_state.q=0; st.session_state.answers=[]
    st.session_state.direction=None; st.session_state.confidence=None
    st.session_state.finished=False; st.session_state.started=True

def remote_config():
    try:
        url=st.secrets.get('SUPABASE_URL',''); key=st.secrets.get('SUPABASE_KEY',''); table=st.secrets.get('SUPABASE_TABLE','quiz_answers')
        return url,key,table
    except Exception: return '','','quiz_answers'

def save_rows(rows):
    clean=[]
    for a in rows:
        r={k:v for k,v in a.items() if k!='hist_values'}
        clean.append(r)
    url,key,table=remote_config()
    if url and key:
        try:
            resp=requests.post(f"{url.rstrip('/')}/rest/v1/{table}",headers={'apikey':key,'Authorization':f'Bearer {key}','Content-Type':'application/json','Prefer':'return=minimal'},data=json.dumps(clean),timeout=15)
            if resp.status_code in (200,201,204): return 'cloud'
        except Exception: pass
    new=pd.DataFrame(clean)
    if OUT_PATH.exists():
        try: new=pd.concat([pd.read_csv(OUT_PATH),new],ignore_index=True)
        except Exception: pass
    new.to_csv(OUT_PATH,index=False); return 'local'

if 'started' not in st.session_state: st.session_state.started=False

if not st.session_state.started:
    st.title('Prognoza rynku')
    st.write('Zobaczysz **30 historycznych wykresów**. Każdy kończy się w punkcie **TERAZ**.')
    st.write('Oceń, czy za miesiąc rynek będzie **wyżej czy niżej**, a potem określ, jak bardzo jesteś pewien swojej prognozy.')
    st.info('Nie musisz wiedzieć. Musisz wybrać. Niewielkie zmiany ceny będą traktowane jako brak wyraźnego ruchu i nie będą zaliczane ani jako trafienie, ani jako błąd.')
    if st.button('ZACZYNAM',type='primary',use_container_width=True): init_test(); st.rerun()
    st.stop()

if not st.session_state.finished:
    q=st.session_state.q; c=st.session_state.cases[q]
    st.caption(f'PROGNOZA {q+1} / {len(st.session_state.cases)}')
    st.progress(q/len(st.session_state.cases))
    st.plotly_chart(make_chart(c),use_container_width=True,config={'displayModeBar':False,'staticPlot':True})
    st.markdown('### Gdzie będzie rynek za miesiąc?')
    a,b=st.columns(2)
    if a.button('SPADNIE',type='primary' if st.session_state.direction=='SPADEK' else 'secondary',use_container_width=True):
        st.session_state.direction='SPADEK'; st.rerun()
    if b.button('WZROŚNIE',type='primary' if st.session_state.direction=='WZROST' else 'secondary',use_container_width=True):
        st.session_state.direction='WZROST'; st.rerun()
    st.markdown('### Jak bardzo jesteś pewien?')
    if st.session_state.variant=='A_NUM':
        labels=[f'{v}%' for v in CONF]
    else:
        labels=[WORDS[v] for v in CONF]
    # 3 x 2 works better on phones and keeps all six choices readable
    for start in (0,3):
        cols=st.columns(3)
        for col,val,label in zip(cols,CONF[start:start+3],labels[start:start+3]):
            if col.button(label,type='primary' if st.session_state.confidence==val else 'secondary',use_container_width=True,key=f'c{val}'):
                st.session_state.confidence=val; st.rerun()
    if st.session_state.variant=='A_NUM': st.caption('50% = równe szanse • 100% = pewność')
    disabled=st.session_state.direction is None or st.session_state.confidence is None
    if st.button('DALEJ',type='primary',use_container_width=True,disabled=disabled):
        ans={'test_id':st.session_state.test_id,'variant':st.session_state.variant,'question_no':q+1,
             'case_id':c['case_id'],'instrument':c['instrument'],'cutoff_date':c['cutoff_date'],'forecast_end':c['forecast_end'],
             'selection_rating':c['rating'],'prediction':st.session_state.direction,'confidence':st.session_state.confidence,
             'confidence_label':WORDS[st.session_state.confidence] if st.session_state.variant=='B_WORDS' else f"{st.session_state.confidence}%",
             'future_return_pct':round(c['future_return'],6),'actual':c['actual'],
             'answered_at_utc':datetime.now(timezone.utc).isoformat()}
        ans['result']='BOK' if c['actual']=='BOK' else ('TRAFIONA' if ans['prediction']==c['actual'] else 'NIETRAFIONA')
        st.session_state.answers.append(ans); st.session_state.direction=None; st.session_state.confidence=None
        if q+1>=len(st.session_state.cases):
            st.session_state.finished=True; st.session_state.save_mode=save_rows(st.session_state.answers)
        else: st.session_state.q+=1
        st.rerun()
else:
    df=pd.DataFrame(st.session_state.answers)
    st.title('Wynik testu')
    hit=int((df.result=='TRAFIONA').sum()); miss=int((df.result=='NIETRAFIONA').sum()); side=int((df.result=='BOK').sum())
    c1,c2,c3=st.columns(3); c1.metric('Trafione',hit); c2.metric('Nietrafione',miss); c3.metric('Bok',side)
    resolved=df[df.result!='BOK']
    if len(resolved): st.metric('Skuteczność rozstrzygniętych',f'{100*(resolved.result=="TRAFIONA").mean():.1f}%')
    st.markdown('### Pewność')
    cols=st.columns(3)
    cols[0].metric('Wszystkie',f'{df.confidence.mean():.1f}%')
    for col,label,res in zip(cols[1:],['Trafione','Nietrafione'],['TRAFIONA','NIETRAFIONA']):
        x=df.loc[df.result==res,'confidence']; col.metric(label,'—' if x.empty else f'{x.mean():.1f}%')
    x=df.loc[df.result=='BOK','confidence']; st.caption('Średnia pewność przy ruchu bocznym: '+('—' if x.empty else f'{x.mean():.1f}%'))
    st.caption(f'Ruch od −{SIDEWAYS:.1f}% do +{SIDEWAYS:.1f}% traktujemy jako boczny.')
    if st.button('NOWY TEST',use_container_width=True):
        for k in list(st.session_state.keys()): del st.session_state[k]
        st.rerun()
