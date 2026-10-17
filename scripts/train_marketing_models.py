"""Public-data validation for the ontology marketing platform; no private rows exported.

Usage: python scripts/train_marketing_models.py --data-dir PATH --output-dir PATH
The booking model uses only fields available before ancillary selection.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from sklearn.cluster import KMeans
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score, precision_recall_curve, f1_score, silhouette_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

FEATURES = ['num_passengers','sales_channel','trip_type','purchase_lead','length_of_stay',
            'flight_hour','flight_day','route','booking_origin','flight_duration']
CATEGORIES = ['sales_channel','trip_type','flight_day','route','booking_origin']
RFM_FEATURES = ['membership_days','LAST_TO_END','FLIGHT_COUNT','SEG_KM_SUM','avg_discount']

def dump(path, data):
    # Stable bytes keep manifest hashes valid on Windows and Linux checkouts.
    path.write_bytes(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8'))

def metrics(y, p, threshold):
    count = max(1, int(np.ceil(len(y)*.2)))
    picked = np.argsort(-p, kind='stable')[:count]
    base = float(np.mean(y))
    return dict(n=len(y), positives=int(np.sum(y)), positive_rate=base,
                roc_auc=float(roc_auc_score(y,p)), pr_auc=float(average_precision_score(y,p)),
                f1=float(f1_score(y,p>=threshold)), threshold=float(threshold),
                top20_precision=float(np.mean(y[picked])), top20_recall=float(np.sum(y[picked])/np.sum(y)),
                top20_lift=float(np.mean(y[picked])/base))

def train(args):
    started=time.time(); source=Path(args.data_dir); out=Path(args.output_dir)
    out.mkdir(parents=True,exist_ok=True)
    frame=pd.read_parquet(source/'booking.parquet')
    manifest_path=source/'data-manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.is_file() else {}
    for c in CATEGORIES: frame[c]=frame[c].fillna('Unknown').astype(str)
    report={'version':'holiday-20261017','purpose':'Support models for ontology-driven marketing',
       'scope':'Public anonymous aviation data; not calibrated China Eastern production probabilities',
       'booking':{'source':'https://github.com/adityanaranje/British-airways-forage',
       'raw_rows':manifest.get('booking',{}).get('raw_rows'),'deduplicated_rows':len(frame),'features':FEATURES,
       'excluded':['booking_complete','source_row','split','route_holdout_split',
                   'wants_extra_baggage','wants_preferred_seat','wants_in_flight_meals'],
       'label':'booking_complete','protocol':'Fixed 70/15/15 stratified split; selection and threshold on validation only',
       'splits':frame.groupby('split').size().to_dict()},'input_manifest':manifest}
    parts={k:frame[frame.split==k] for k in ['train','val','test']}
    X={k:v[FEATURES] for k,v in parts.items()}; y={k:v.booking_complete.to_numpy() for k,v in parts.items()}
    numeric=[c for c in FEATURES if c not in CATEGORIES]
    transform=ColumnTransformer([('num',make_pipeline(SimpleImputer(strategy='median'),StandardScaler()),numeric),
        ('cat',OneHotEncoder(handle_unknown='ignore'),CATEGORIES)])
    lr=make_pipeline(transform,LogisticRegression(max_iter=600,random_state=2026))
    lr.fit(X['train'],y['train'])
    candidates=[]
    for depth in [5,7]:
        model=CatBoostClassifier(iterations=650,depth=depth,learning_rate=.045,loss_function='Logloss',
          eval_metric='AUC',random_seed=2026,thread_count=4,allow_writing_files=False,l2_leaf_reg=6)
        model.fit(X['train'],y['train'],cat_features=CATEGORIES,eval_set=(X['val'],y['val']),
                  early_stopping_rounds=80,verbose=100)
        val=model.predict_proba(X['val'])[:,1]
        candidates.append((average_precision_score(y['val'],val),model,depth))
    _, selected, depth=max(candidates,key=lambda r:r[0])
    selected.save_model(str(out/'booking_intent.cbm'))
    comparison={}; predictions={}
    for name,estimator in [('logistic_regression',lr),('catboost',selected)]:
        pv=estimator.predict_proba(X['val'])[:,1]
        precision,recall,thresholds=precision_recall_curve(y['val'],pv)
        f=2*precision[:-1]*recall[:-1]/np.maximum(precision[:-1]+recall[:-1],1e-12)
        threshold=float(thresholds[int(np.argmax(f))])
        pt=estimator.predict_proba(X['test'])[:,1]
        comparison[name]=metrics(y['test'],pt,threshold)
        predictions[name]=pt
    baseline=np.full(len(y['test']),np.mean(y['train']))
    comparison['constant_prior']=metrics(y['test'],baseline,1.)
    comparison['constant_prior'].update(top20_precision=float(np.mean(y['test'])),top20_recall=.2,
        top20_lift=1.,selection='Expected random selection; constant scores have no ordering information')
    report['booking'].update(results=comparison,selected_depth=depth,trees=selected.tree_count_,
         validation_grid=[{'depth':d,'pr_auc':float(s)} for s,m,d in candidates])
    # Paired bootstrap on the same held-out rows; no re-fitting or test selection.
    rng=np.random.default_rng(2026); differences=[]
    for _ in range(300):
        idx=rng.integers(0,len(y['test']),len(y['test']))
        differences.append(average_precision_score(y['test'][idx],predictions['catboost'][idx])-
                           average_precision_score(y['test'][idx],predictions['logistic_regression'][idx]))
    report['booking']['paired_pr_auc_delta_ci95']=[float(v) for v in np.quantile(differences,[.025,.975])]
    # Route-level OOD: no test route appears during fitting; separate experiment.
    ood={k:frame[frame.route_holdout_split==k] for k in ['train','val','test']}
    m=CatBoostClassifier(iterations=selected.tree_count_,depth=depth,learning_rate=.045,loss_function='Logloss',
        random_seed=2026,thread_count=4,allow_writing_files=False,l2_leaf_reg=6)
    m.fit(ood['train'][FEATURES],ood['train'].booking_complete,cat_features=CATEGORIES,verbose=False)
    report['booking']['route_holdout']={'splits':{k:len(v) for k,v in ood.items()},
        'roc_auc':float(roc_auc_score(ood['test'].booking_complete,m.predict_proba(ood['test'][FEATURES])[:,1])),
        'pr_auc':float(average_precision_score(ood['test'].booking_complete,m.predict_proba(ood['test'][FEATURES])[:,1]))}
    importance=selected.get_feature_importance()
    report['booking']['global_importance']=[{'feature':c,'importance':float(v)} for c,v in sorted(zip(FEATURES,importance),key=lambda r:-r[1])]
    examples=X['test'].head(8).to_dict('records')
    dump(out/'booking_examples.json',[{'features':x,'score':float(selected.predict_proba(pd.DataFrame([x]))[0,1])} for x in examples])
    profiles=pd.read_parquet(source/'profiles.parquet')
    valid=profiles[RFM_FEATURES].apply(pd.to_numeric,errors='coerce')
    valid=valid[valid.notna().all(axis=1)&(valid>=0).all(axis=1)&(valid.avg_discount>0)&(valid.avg_discount<=1.5)&(valid.FLIGHT_COUNT>0)]
    transformed=np.log1p(valid.to_numpy()); scaler=StandardScaler().fit(transformed); z=scaler.transform(transformed)
    groups=KMeans(n_clusters=5,n_init=20,random_state=2026).fit(z)
    centers=np.expm1(scaler.inverse_transform(groups.cluster_centers_))
    # Name clusters from their data, never use future purchase labels.
    order=np.argsort(centers[:,2]); labels={int(i):name for i,name in zip(order,['低频待唤醒','低频发展','稳定出行','活跃成长','高价值常旅客'])}
    counts=np.bincount(groups.labels_,minlength=5)
    spec={'version':report['version'],'features':RFM_FEATURES,'transform':'log1p_then_standardize',
       'mean':scaler.mean_.tolist(),'scale':scaler.scale_.tolist(),'centroids':groups.cluster_centers_.tolist(),
       'names':{str(k):v for k,v in labels.items()},'public_source':'https://tianchi.aliyun.com/dataset/64977'}
    dump(out/'customer_value.json',spec)
    report['profiles']={'source':spec['public_source'],'raw_rows':len(profiles),'valid_rows':len(valid),
      'features':RFM_FEATURES,'method':'Log1p + StandardScaler + KMeans(k=5,n_init=20,seed=2026)',
      'silhouette_sample_n':5000,'silhouette':float(silhouette_score(z,groups.labels_,sample_size=5000,random_state=2026)),
      'clusters':[{'name':labels[i],'count':int(counts[i]),'center':dict(zip(RFM_FEATURES,centers[i].tolist()))} for i in range(5)],
      'scope':'Unsupervised value segmentation; no classification accuracy or churn claims'}
    report['seconds']=round(time.time()-started,2)
    report['files']={name:hashlib.sha256((out/name).read_bytes()).hexdigest()
        for name in ['booking_intent.cbm','customer_value.json','booking_examples.json']}
    dump(out/'validation.json',report)
    print(json.dumps(report,ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data-dir',required=True);p.add_argument('--output-dir',required=True)
    train(p.parse_args())
