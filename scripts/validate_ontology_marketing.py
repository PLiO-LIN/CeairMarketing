"""Reproducible component validation with controlled faults in platform ORM data.

This is an engineering fixture benchmark, not real campaign uplift evidence.
All variants read the same rows. A complete relational rule implementation may
match the ontology result; this benchmark does not prove ontology uniqueness.
"""
from pathlib import Path
import sys,json,time,hashlib

API=Path(__file__).resolve().parents[1]/'services/platform-api'
sys.path[:0]=[str(API),str(API/'tests')]
from sqlalchemy import delete
from app.db_models import OntologyRelationRecord
from app.holiday_marketing import analyze_holiday, HolidayParameters
from test_holiday_marketing import scenario

def run():
    definitions=[('正常关系链','normal',True),('预算为零','zero_budget',False),
       ('缺失航线归属边','operates_on',False),('缺失票价产品边','uses_product',False),
       ('缺失辅营包含边','includes_ancillary',False),('报价来自未来','future_fare',False),
       ('报价缺少时点','missing_fare_time',False),('产品已过期','expired_product',False),
       ('产品尚未生效','future_product',False),('本体端点类型错误','wrong_type',False),
       ('客群保护','protected',False),('无渠道授权','no_consent',False)]
    results=[]
    for repeat in range(10):
      for label,fault,expected in definitions:
        fixture=scenario.__wrapped__();s,ctx,other,nodes=next(fixture)
        try:
          params=HolidayParameters()
          if fault in {'operates_on','uses_product','includes_ancillary'}:
            s.execute(delete(OntologyRelationRecord).where(OntologyRelationRecord.tenant_id==ctx.tenant_id,OntologyRelationRecord.relation_type==fault))
          elif fault in {'future_fare','missing_fare_time'}:
            n=nodes['FARE'];a=json.loads(n.attributes_json);a['captured_at']='2026-10-02 10:00:00' if fault=='future_fare' else None;n.attributes_json=json.dumps(a)
          elif fault in {'expired_product','future_product'}:
            n=nodes['ANC'];a=json.loads(n.attributes_json);a['valid_to' if fault=='expired_product' else 'valid_from']='2026-09-30' if fault=='expired_product' else '2026-10-08';n.attributes_json=json.dumps(a)
          elif fault=='wrong_type':nodes['R'].entity_type='Airport'
          elif fault in {'protected','no_consent'}:
            from sqlalchemy import select
            from app.db_models import DatasetRowRecord,DatasetRecord
            row=s.scalar(select(DatasetRowRecord).join(DatasetRecord).where(DatasetRecord.name=='客户画像',DatasetRowRecord.record_key=='0'))
            a=json.loads(row.payload_json);a['protected' if fault=='protected' else 'app_consent']=1 if fault=='protected' else 0;row.payload_json=json.dumps(a)
          elif fault=='zero_budget':params=HolidayParameters(budget_yuan=0)
          s.flush();begin=time.perf_counter();answer=analyze_holiday(s,ctx.tenant_id,params)
          elapsed=(time.perf_counter()-begin)*1000
          # Attribute gates know consent, budget etc., but have no cross-object paths.
          attribute_ready=fault not in {'zero_budget','protected','no_consent'}
          results.append({'repeat':repeat,'case':label,'expected_ready':expected,
              'attribute_gate_ready':attribute_ready,'ontology_ready':answer['ready'],
              'ontology_checks':answer['rule_summary'],'latency_ms':round(elapsed,3),
              'evidence_nodes':answer['graph_node_count']})
        finally:
          try:next(fixture)
          except StopIteration:pass
    n=len(results);negative=[r for r in results if not r['expected_ready']]
    report={'protocol':'12 controlled platform scenarios x 10 repetitions; one pristine in-memory database per case',
      'scope':'Engineering fault-injection benchmark, not open-world LLM accuracy or live campaign effectiveness',
      'cases':n,'valid_cases':n-len(negative),'invalid_cases':len(negative),
      'attribute_gate_false_accepts':sum(r['attribute_gate_ready'] for r in negative),
      'ontology_false_accepts':sum(r['ontology_ready'] for r in negative),
      'ontology_valid_retained':sum(r['ontology_ready'] for r in results if r['expected_ready']),
      'mean_latency_ms':round(sum(r['latency_ms'] for r in results)/n,3),
      'case_definitions':[(label,expected) for label,fault,expected in definitions],
      'interpretation':'Scalar eligibility alone misses relational and temporal facts. A full SQL/rule implementation can be equivalent; ontology centralizes typed constraints and evidence reuse.',
      'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'rows':results}
    target=Path(sys.argv[1]);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='rows'},ensure_ascii=False))
    if report['ontology_false_accepts'] or report['ontology_valid_retained']!=report['valid_cases']:raise SystemExit('Constraint validation did not pass')

if __name__=='__main__':run()
