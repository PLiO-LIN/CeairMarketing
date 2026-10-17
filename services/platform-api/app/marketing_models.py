"""Versioned support models. Predictions never override ontology qualifications."""
from __future__ import annotations
import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .auth import get_tenant_context

router = APIRouter(prefix='/api/marketing-models', tags=['marketing-models'])
ASSETS = Path(__file__).parent / 'model_assets'
FEATURES = ['num_passengers','sales_channel','trip_type','purchase_lead','length_of_stay',
            'flight_hour','flight_day','route','booking_origin','flight_duration']

@lru_cache(maxsize=1)
def validation():
    try:
        return json.loads((ASSETS/'validation.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise RuntimeError('模型验证清单不可用，请检查模型部署') from exc

def verified_file(name):
    path=ASSETS/name
    expected=validation().get('files',{}).get(name)
    if not expected or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
        raise RuntimeError('模型文件缺失或版本校验失败：'+name)
    return path

@lru_cache(maxsize=1)
def intent_model():
    try:
        from catboost import CatBoostClassifier
        model=CatBoostClassifier();model.load_model(str(verified_file('booking_intent.cbm')))
        return model
    except ImportError as exc:
        raise RuntimeError('意向模型运行库未安装，请安装平台依赖') from exc

class BookingFeatures(BaseModel):
    model_config=ConfigDict(extra='forbid', allow_inf_nan=False)
    num_passengers: int=Field(ge=1,le=50)
    sales_channel: Literal['Internet','Mobile']
    trip_type: Literal['RoundTrip','OneWay','CircleTrip']
    purchase_lead: int=Field(ge=0,le=1000)
    length_of_stay: int=Field(ge=0,le=1000)
    flight_hour: int=Field(ge=0,le=23)
    flight_day: Literal['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
    route: str=Field(pattern=r'^[A-Z]{6}$')
    booking_origin: str=Field(min_length=1,max_length=80)
    flight_duration: float=Field(gt=0,le=48)

class ValueFeatures(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    membership_days: int=Field(ge=0,le=30000)
    LAST_TO_END: int=Field(ge=0,le=30000)
    FLIGHT_COUNT: int=Field(ge=1,le=100000)
    SEG_KM_SUM: float=Field(ge=0,le=1000000000)
    avg_discount: float=Field(gt=0,le=1.5)

def score_intent(features: BookingFeatures):
    values=features.model_dump()
    score=float(intent_model().predict_proba([[values[f] for f in FEATURES]])[0,1])
    return {'model':'booking_intent','version':validation()['version'],'reference_score':round(score,6),
        'status':'参考评分','qualification':'待本体校验',
        'scope':'公开航空预订数据训练，跨航司评分未校准，不能视为东航实际购票概率或营销增量',
        'feature_names':FEATURES,'evidence':{'source':validation()['booking']['source'],
            'test_pr_auc':validation()['booking']['results']['catboost']['pr_auc']}}

def score_value(features: ValueFeatures):
    spec=json.loads(verified_file('customer_value.json').read_text(encoding='utf-8'))
    values=features.model_dump()
    z=[(math.log1p(values[f])-mean)/scale for f,mean,scale in zip(spec['features'],spec['mean'],spec['scale'])]
    distances=[sum((a-b)**2 for a,b in zip(z,center)) for center in spec['centroids']]
    cluster=min(range(len(distances)),key=distances.__getitem__)
    return {'model':'customer_value','version':spec['version'],'segment':spec['names'][str(cluster)],
        'distance':round(math.sqrt(distances[cluster]),4),'qualification':'待本体校验',
        'scope':'公开数据训练的价值分层，仅补充现有画像，不替代既有客群体系',
        'features':values}

def evaluation_card():
    v=validation();models=v['booking']['results'];rows=[]
    for name,label in [('logistic_regression','逻辑回归'),('catboost','CatBoost意向模型')]:
        m=models[name];rows.append([label,round(m['roc_auc'],4),round(m['pr_auc'],4),
            str(round(m['top20_recall']*100,2))+'%',round(m['top20_lift'],2)])
    return {'type':'scenario','id':'marketing-model-validation','title':'模型验证',
        'summary':'本体组织数据、校验资格与保存证据；模型提供参考评分。',
        'chart':{'title':'前20%候选覆盖的实际完成预订样本','labels':['随机选择期望','逻辑回归','CatBoost'],
            'values':[20.,round(models['logistic_regression']['top20_recall']*100,2),
                round(models['catboost']['top20_recall']*100,2)],'unit':'%',
            'source':'公开预订数据；独立测试7393条，正例1109条；不是营销转化提升'},
        'table':{'columns':['方法','ROC-AUC','PR-AUC','Top20%召回','富集倍数'],'rows':rows},
        'metrics':[{'label':'有效客户价值样本','value':v['profiles']['valid_rows']},
            {'label':'价值分层','value':len(v['profiles']['clusters'])},
            {'label':'模型版本','value':v['version']}],
        'evidence':['训练、验证、测试分离；阈值仅使用验证集确定',
            '本体资格约束优先于模型评分；渠道、频控、产品有效期继续独立校验',
            '分群为无监督分析，轮廓系数不等于分类准确率']}

@router.get('/evaluation')
def model_evaluation(context=Depends(get_tenant_context)):
    try:return {'validation':validation(),'card':evaluation_card()}
    except RuntimeError as exc:raise HTTPException(503,str(exc)) from exc

@router.get('/examples')
def public_examples(context=Depends(get_tenant_context)):
    try:return json.loads(verified_file('booking_examples.json').read_text(encoding='utf-8'))
    except (OSError,ValueError,RuntimeError) as exc:raise HTTPException(503,'公开模型样例暂不可用') from exc

@router.post('/booking-intent/score')
def booking_score(payload: BookingFeatures,context=Depends(get_tenant_context)):
    try:return score_intent(payload)
    except RuntimeError as exc:raise HTTPException(503,str(exc)) from exc

@router.post('/customer-value/score')
def value_score(payload: ValueFeatures,context=Depends(get_tenant_context)):
    try:return score_value(payload)
    except RuntimeError as exc:raise HTTPException(503,str(exc)) from exc
