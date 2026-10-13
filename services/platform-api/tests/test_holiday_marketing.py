"""Cross-domain evidence gates, counterfactuals, persistence and streamed UI."""
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.database import Base, get_session
from app.auth import get_tenant_context
from app.db_models import (TenantRecord, UserRecord, DatasetRecord, DatasetRowRecord,
    ImportJobRecord, OntologyEntityRecord, OntologyRelationRecord, ProductPackageRecord,
    CampaignVersionRecord, ContentAssetRecord, AssistantConversationRecord, AssistantMessageRecord)
from app.holiday_marketing import analyze_holiday, HolidayParameters, parameters_from_message, save_draft
from app.a2ui import ReplySurfaces, VALIDATOR
from app.main import app


@pytest.fixture
def scenario():
    engine = create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        tenant = TenantRecord(code='HOL-QA', name='QA'); other = TenantRecord(code='HOL-OTHER',name='Other')
        user = UserRecord(username='hol-qa', display_name='QA', password_hash='unused')
        s.add_all([tenant, other, user]);s.flush()
        job = ImportJobRecord(id='HOL-IMPORT',tenant_id=tenant.id,created_by=user.id,dataset_type='bundle',file_name='qa',file_format='json',status='completed')
        s.add(job);s.flush()
        tid=tenant.id
        def dataset(name,rows):
            ds=DatasetRecord(tenant_id=tid,dataset_key='QA-'+name,name=name,row_count=len(rows),source='SIM-QA',data_mode='模拟',metadata_json=json.dumps({'namespace':'QA','as_of':'2026-09-30 23:59:59'}),import_job_id=job.id)
            s.add(ds);s.flush()
            for i,r in enumerate(rows):s.add(DatasetRowRecord(tenant_id=tid,dataset_id=ds.id,record_key=str(i),route_id=r.get('route_id'),flight_id=r.get('flight_id'),customer_id=r.get('customer_id'),payload_json=json.dumps(r,ensure_ascii=False)))
        customers=[dict(customer_id='C'+str(i),business_segment='家庭出游',preferred_route='R-SHA-SYX',profile_as_of='2026-09-30 23:59:59',protected=0,app_consent=1,member_tier='普通') for i in range(5)]
        customers[1]['protected']=1; customers[2]['app_consent']=0
        flight=dict(flight_id='F1',route_id='R-SHA-SYX',flight_no='MU-QA',departure_at='2026-10-01 10:00:00',wifi_supported=0)
        product=dict(product_id='P-FLEX',product_name='灵活权益',valid_from='2025-10-01',valid_to='2026-10-31',eligibility='模拟规则')
        dataset('客户画像',customers);dataset('航线目录',[dict(route_id='R-SHA-SYX',origin='SHA',destination='SYX',origin_city='上海',destination_city='三亚')]);dataset('航班计划',[flight])
        dataset('搜索行为',[dict(event_at='2026-09-20 10:00:00',departure_date='2026-10-01',customer_id='C0',route_id='R-SHA-SYX',passenger_count=2)])
        dataset('客票订单',[dict(customer_id='C3',flight_id='F1',issued_at='2026-09-25 10:00:00',cancelled_at=None,refund_at=None)])
        dataset('触达回执',[dict(customer_id='C4',delivered_at='2026-09-28 10:00:00'),dict(customer_id='C4',delivered_at='2026-09-29 10:00:00')]);dataset('产品目录',[product])
        dataset('营销增量实验样本',[dict(treatment=0,label_complete=1,outcome_window_end='2026-09-29 10:00:00',outcome_issued_7d=1),dict(treatment=1,label_complete=0,outcome_window_end='2026-10-08',outcome_issued_7d=None)])
        nodes={}
        def node(id,kind,attrs):
            n=OntologyEntityRecord(tenant_id=tid,external_id='QA-'+id,entity_type=kind,label=id,attributes_json=json.dumps(attrs),source='SIM-QA');s.add(n);s.flush();nodes[id]=n
        def edge(a,r,b):s.add(OntologyRelationRecord(tenant_id=tid,source_entity_id=nodes[a].id,relation_type=r,target_entity_id=nodes[b].id,evidence='源字段关联'))
        node('F1','Flight',flight);node('R','Route',{'route_id':'R-SHA-SYX'});node('SEG','FlightSegment',{'flight_id':'F1'});node('SHA','Airport',{'airport_code':'SHA'});node('SYX','Airport',{'airport_code':'SYX'})
        node('CAB','Cabin',{});node('FARE','Fare',{'captured_at':'2026-09-29 10:00:00','synthetic':True,'currency':'CNY'});node('FARE-P','Product',{})
        node('PP-P-FLEX','ProductPackage',{});node('ANC','AncillaryProduct',product)
        for a,r,b in [('F1','operates_on','R'),('F1','has_segment','SEG'),('F1','has_cabin','CAB'),('R','departs_from','SHA'),('R','arrives_at','SYX'),('SEG','departs_from','SHA'),('SEG','arrives_at','SYX'),('CAB','has_fare','FARE'),('FARE','uses_product','FARE-P'),('PP-P-FLEX','includes_ancillary','ANC')]:edge(a,r,b)
        s.add(ProductPackageRecord(tenant_id=tid,external_id='QA-PP-P-FLEX',name='灵活权益',product_type='灵活',created_by=user.id));s.commit()
        context=SimpleNamespace(tenant_id=tid,user_id=user.id,display_name='QA',role='admin')
        yield s,context,other.id,nodes
    engine.dispose()


def test_cross_domain_filters_budget_and_no_personal_details(scenario):
    s,ctx,_,_=scenario
    r=analyze_holiday(s,ctx.tenant_id,HolidayParameters())
    assert r['eligible_count']==1 and r['proposal']['audience_size']==1 and r['qualified_flights']==1
    assert [c['id'] for c in r['cards']]==['holiday-'+k for k in ['scope','demand','audience','supply','ontology','plan','measurement']]
    assert 'customer_id' not in json.dumps(r,ensure_ascii=False)
    assert r['cards'][-1]['metrics'][0]['value']=='缺少成熟标签'
    assert not analyze_holiday(s,ctx.tenant_id,HolidayParameters(budget_yuan=0))['ready']
    c=s.scalar(select(DatasetRowRecord).join(DatasetRecord).where(DatasetRecord.name=='客户画像',DatasetRowRecord.record_key=='0'))
    payload=json.loads(c.payload_json);payload['app_consent']=0;c.payload_json=json.dumps(payload);s.flush()
    assert not analyze_holiday(s,ctx.tenant_id,HolidayParameters())['ready']


@pytest.mark.parametrize('relation',['operates_on','uses_product','includes_ancillary'])
def test_missing_critical_relation_blocks_composition(scenario,relation):
    s,ctx,_,_=scenario
    baseline=analyze_holiday(s,ctx.tenant_id,HolidayParameters())
    assert baseline['ready']
    comparison=analyze_holiday(s,ctx.tenant_id,HolidayParameters(),omitted_relation=relation)
    assert not comparison['ready']
    # Compare simulation leaves persisted graph intact.
    assert analyze_holiday(s,ctx.tenant_id,HolidayParameters())['ready']
    s.execute(delete(OntologyRelationRecord).where(OntologyRelationRecord.tenant_id==ctx.tenant_id,OntologyRelationRecord.relation_type==relation))
    assert not analyze_holiday(s,ctx.tenant_id,HolidayParameters())['ready']


def test_version_and_observation_guards_and_tenant_isolation(scenario):
    s,ctx,other,nodes=scenario
    with pytest.raises(ValueError,match='未导入'):analyze_holiday(s,other,HolidayParameters())
    with pytest.raises(ValueError,match='画像版本'):analyze_holiday(s,ctx.tenant_id,HolidayParameters(as_of='2026-09-29 23:59:59'))
    n=nodes['FARE'];a=json.loads(n.attributes_json);a['captured_at']='2026-10-01 10:00:00';n.attributes_json=json.dumps(a);s.flush()
    assert not analyze_holiday(s,ctx.tenant_id,HolidayParameters())['ready']
    a['captured_at']=None;n.attributes_json=json.dumps(a);s.flush()
    assert not analyze_holiday(s,ctx.tenant_id,HolidayParameters())['ready']
    a['captured_at']='2026-09-29 10:00:00';n.attributes_json=json.dumps(a)
    n=nodes['ANC'];a=json.loads(n.attributes_json);a['valid_to']='2026-09-30';n.attributes_json=json.dumps(a);s.flush()
    assert not analyze_holiday(s,ctx.tenant_id,HolidayParameters())['ready']


def test_streamed_stages_validate_a2ui_and_draft_projects_business(scenario):
    s,ctx,_,_=scenario
    wire=[];events=[];ui=ReplySurfaces('HOL',wire.append)
    r=analyze_holiday(s,ctx.tenant_id,HolidayParameters(),ui.add,lambda event,data:events.append((event,data)))
    assert len(wire)==21 and len(events)==14
    for msg in wire:VALIDATOR.validate(msg)
    result=save_draft(HolidayParameters(),ctx,s)
    v=s.scalar(select(CampaignVersionRecord).where(CampaignVersionRecord.campaign_id==result['campaign_id']))
    assert v.audience_snapshot_id==result['audience_snapshot_id']
    assert json.loads(v.content_asset_ids_json)==[result['content_asset_id']]
    assert s.get(ContentAssetRecord,result['content_asset_id']).status=='草稿'
    assert s.scalar(select(OntologyEntityRecord).where(OntologyEntityRecord.external_id==result['campaign_id'])).entity_type=='Campaign'
    assert r['proposal']['status']=='候选草稿'
    assert s.scalar(select(OntologyEntityRecord).where(OntologyEntityRecord.entity_type=='Evidence',OntologyEntityRecord.source=='holiday-evidence-planner')) is not None


def test_natural_language_scope_and_invalid_holiday():
    p=parameters_from_message('国庆家庭出游活动 R-SHA-SYX App P-FLEX 预算2万元 2026-10-01至2026-10-07')
    assert p.route_id=='R-SHA-SYX' and p.budget_yuan==20000
    with pytest.raises(ValueError,match='指定出行日期'):parameters_from_message('帮我做春节出行营销')
    with pytest.raises(ValueError):HolidayParameters(start='2026-10-08',end='2026-10-01')
    inherited=parameters_from_message('预算改为500元，换成价格敏感客群',previous=p.model_dump(mode='json'))
    assert inherited.route_id=='R-SHA-SYX' and inherited.budget_yuan==500 and inherited.segment=='价格敏感'


def test_city_names_resolve_to_imported_route(scenario):
    s,ctx,_,_=scenario
    assert parameters_from_message('国庆上海到三亚的家庭出游营销',s,ctx.tenant_id).route_id=='R-SHA-SYX'
    assert parameters_from_message('换成三亚',s,ctx.tenant_id,HolidayParameters(route_id='R-SHA-PEK').model_dump(mode='json')).route_id=='R-SHA-SYX'


def test_ui_action_requires_saved_owned_surface_and_deduplicates(scenario):
    s,ctx,other,_=scenario
    ui=ReplySurfaces('owned');analyze_holiday(s,ctx.tenant_id,HolidayParameters(),ui.add)
    conversation=AssistantConversationRecord(id='HOL-CONV',tenant_id=ctx.tenant_id,user_id=ctx.user_id,title='Holiday')
    s.add(conversation);s.flush();s.add(AssistantMessageRecord(conversation_id=conversation.id,role='assistant',content='done',detail_json=json.dumps({'a2ui':ui.messages})));s.commit()
    sid=next(m['updateDataModel']['surfaceId'] for m in ui.messages if m.get('updateDataModel',{}).get('value',{}).get('content',{}).get('id')=='holiday-plan')
    action={'version':'v0.9.1','action':{'name':'prepare_holiday_draft','surfaceId':sid,'sourceComponentId':'content','timestamp':'2026-10-13T12:00:00Z','context':{'conversation_id':conversation.id}}}
    app.dependency_overrides[get_session]=lambda:s
    app.dependency_overrides[get_tenant_context]=lambda:ctx
    try:
        with TestClient(app) as client:
            r=client.post('/api/assistant/ui-action',json=action)
            assert r.status_code==200,r.text
            assert client.post('/api/assistant/ui-action',json=action).json()['task']['id']==r.json()['task']['id']
            action['action']['surfaceId']='fabricated'
            assert client.post('/api/assistant/ui-action',json=action).status_code==422
    finally:app.dependency_overrides.clear()
