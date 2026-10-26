"""Read preserved results; independently derive winner diagnostics for the PDF."""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
BEST = ROOT / 'reports/BEST_RESULTS'

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def weights(df):
    return 1 / df.groupby('session_id').session_id.transform('size').to_numpy()

def metrics(df, task):
    y, p, w = df.truth.to_numpy(), df.prediction.to_numpy(), weights(df)
    result = dict(frames=len(df), recordings=df.session_id.nunique())
    if task == 'force':
        e = p-y
        result.update(mae_N=float(np.average(abs(e),weights=w)),
                      rmse_N=float(np.sqrt(np.average(e*e,weights=w))),
                      bias_N=float(np.average(e,weights=w)),
                      r2=float(1-np.sum(w*e*e)/np.sum(w*(y-np.average(y,weights=w))**2)))
    else:
        labels = np.arange(1,10) if task == 'localization' else np.arange(2)
        cm = np.array([[w[(y==a)&(p==b)].sum() for b in labels] for a in labels])
        tp=np.diag(cm); rec=tp/cm.sum(axis=1)
        prec=np.divide(tp,cm.sum(axis=0),out=np.zeros(len(tp)),where=cm.sum(axis=0)>0)
        f1=2*tp/(cm.sum(axis=0)+cm.sum(axis=1))
        result.update(accuracy=float(tp.sum()/cm.sum()),balanced_accuracy=float(rec.mean()),macro_f1=float(f1.mean()))
        if task=='contact':
            result.update(precision=float(prec[1]),recall=float(rec[1]),specificity=float(rec[0]),
                          fpr=float(1-rec[0]),contact_f1=float(f1[1]))
    return result

def main():
    existing={str(p.relative_to(ROOT)):sha(p) for folder in [ROOT/'reports',ROOT/'output/pdf']
              if folder.exists() for p in folder.rglob('*') if p.is_file()
              and OUT not in p.parents and 'complete_thesis_report_2026-10-18' not in p.parts}
    (OUT/'preserved_files.json').write_text(json.dumps(existing,indent=2),encoding='utf-8')
    df=pd.read_parquet(BEST/'data/best_models_held_out_predictions.parquet')
    expected=json.loads((BEST/'BEST_METRICS.json').read_text())['results']
    result={'overall':{},'folds':{},'taxels':{},'force_bins':[],'checks':[]}
    for task in ['force','localization','contact']:
        d=df[df.task==task].copy()
        actual=metrics(d,task)
        for key,value in actual.items():
            assert abs(value-expected[task][key])<1e-11,(task,key,value,expected[task][key])
            result['checks'].append(f'{task}.{key}: independently matches saved result')
        assert d.frame_uid.nunique()==len(d)
        assert d.groupby('session_id').outer_fold.nunique().max()==1
        result['overall'][task]=actual
        result['folds'][task]=[dict(fold=int(f),**metrics(v,task)) for f,v in d.groupby('outer_fold')]
        result['taxels'][task]=[dict(taxel=int(t),**metrics(v,task)) for t,v in d.groupby('target_roi')
                                 if task=='force']
        if task!='force':
            labels=range(1,10) if task=='localization' else range(2)
            y,p,w=d.truth.to_numpy(),d.prediction.to_numpy(),weights(d)
            raw=np.array([[int(((y==a)&(p==b)).sum()) for b in labels] for a in labels])
            weighted=np.array([[w[(y==a)&(p==b)].sum() for b in labels] for a in labels])
            normalized=weighted/weighted.sum(axis=1,keepdims=True)*100
            saved_raw=pd.read_csv(BEST/f'data/{task}_raw_counts.csv',index_col=0).to_numpy()
            saved_norm=pd.read_csv(BEST/f'data/{task}_row_normalized_percent.csv',index_col=0).to_numpy()
            assert np.array_equal(raw,saved_raw)
            assert np.allclose(normalized,saved_norm,atol=1e-10)
            result['checks'].append(f'{task}: both confusion matrices independently reproduced')
    f=df[df.task=='force']
    for lo,hi in [(.05,.5),(.5,1),(1,1.5),(1.5,2),(2,2.5),(2.5,3)]:
        d=f[(f.truth>=lo)&((f.truth<hi) if hi<3 else (f.truth<=hi))]
        result['force_bins'].append(dict(lower=lo,upper=hi,**metrics(d,'force')))
    # An explicitly defined combined task, using only the common eligible positive frames.
    loc=df[df.task=='localization'][['frame_uid','session_id','truth','prediction']]
    con=df[(df.task=='contact')&(df.truth==1)][['frame_uid','prediction']]
    joined=loc.merge(con,on='frame_uid',suffixes=('_loc','_contact'),validate='one_to_one')
    assert len(joined)==7154
    result['combined_positive_detection_and_localization']=float(np.average(
        (joined.truth==joined.prediction_loc)&(joined.prediction_contact==1),weights=weights(joined)))
    (OUT/'derived_evidence.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    # Force regression is illustrated as a distribution of all held-out predictions.
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,2,figsize=(10,4.1),layout='constrained')
    a=axes[0]; a.scatter(f.truth,f.prediction,s=4,alpha=.14,color='#087e8b',rasterized=True)
    lim=max(3,float(f.prediction.max())+.05); a.plot([0,lim],[0,lim],'--',lw=1,color='#424b5a')
    a.set(xlabel='Reference force (N)',ylabel='Predicted force (N)',title='All 7,154 held-out frames',xlim=(0,3.08),ylim=(0,lim))
    a=axes[1]; b=result['force_bins']; x=np.arange(len(b));
    a.bar(x,[v['mae_N'] for v in b],color='#087e8b',width=.68)
    a.set_xticks(x,[f"{v['lower']:g}\u2013{v['upper']:g}" for v in b],rotation=25,ha='right')
    a.set(xlabel='Reference-force interval (N)',ylabel='Recording-weighted MAE (N)',title='Force error by reference interval')
    for i,v in enumerate(b): a.text(i,v['mae_N']+.012,f"{v['mae_N']:.3f}",ha='center',fontsize=9)
    a.set_ylim(0,max(v['mae_N'] for v in b)*1.18)
    fig.savefig(OUT/'force_diagnostics.png',dpi=250,bbox_inches='tight');plt.close(fig)
    print(json.dumps({'rows':len(df),'checks':len(result['checks']),'preserved_files':len(existing),
                      'folds':result['folds'],'force_bins':result['force_bins'],
                      'joint':result['combined_positive_detection_and_localization']},indent=2))

if __name__=='__main__': main()
