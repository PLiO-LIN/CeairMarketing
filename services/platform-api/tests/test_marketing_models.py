import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.auth import get_tenant_context
from app.main import app
from app.a2ui import ReplySurfaces, VALIDATOR
from app import marketing_models as models

def test_saved_model_predictions_match_heldout_examples():
    examples=json.loads(models.verified_file('booking_examples.json').read_text(encoding='utf-8'))
    for example in examples:
        result=models.score_intent(models.BookingFeatures(**example['features']))
        assert result['reference_score']==pytest.approx(example['score'],abs=1e-6)
        assert result['qualification']=='待本体校验'

def test_no_labels_or_post_selection_features_and_no_invented_missing_values():
    example=json.loads(models.verified_file('booking_examples.json').read_text(encoding='utf-8'))[0]['features']
    with pytest.raises(ValidationError):models.BookingFeatures(**example,booking_complete=1)
    with pytest.raises(ValidationError):models.BookingFeatures(**example,wants_extra_baggage=1)
    del example['purchase_lead']
    with pytest.raises(ValidationError):models.BookingFeatures(**example)
    with pytest.raises(ValidationError):models.ValueFeatures(membership_days=100,LAST_TO_END=1,FLIGHT_COUNT=2,SEG_KM_SUM=float('nan'),avg_discount=.8)

def test_value_model_is_deterministic_and_does_not_replace_eligibility():
    features=models.ValueFeatures(membership_days=1800,LAST_TO_END=10,FLIGHT_COUNT=30,SEG_KM_SUM=40000,avg_discount=.8)
    a=models.score_value(features)
    assert a==models.score_value(features)
    assert a['segment']=='高价值常旅客' and a['qualification']=='待本体校验'

def test_model_files_are_integrity_checked(tmp_path,monkeypatch):
    monkeypatch.setattr(models,'ASSETS',tmp_path)
    with pytest.raises(RuntimeError,match='缺失或版本'):models.verified_file('customer_value.json')

def test_evaluation_has_valid_a2ui_and_authenticated_endpoints():
    ui=ReplySurfaces('ML-VALIDATION');ui.add(models.evaluation_card(),'scenario')
    for msg in ui.messages:VALIDATOR.validate(msg)
    with TestClient(app) as client:
        assert client.get('/api/marketing-models/evaluation').status_code==401
    app.dependency_overrides[get_tenant_context]=lambda:SimpleNamespace(tenant_id=9,user_id=9,role='viewer')
    try:
        with TestClient(app) as client:
            assert client.get('/api/marketing-models/evaluation').status_code==200
            assert client.post('/api/marketing-models/booking-intent/score',json={}).status_code==422
            example=client.get('/api/marketing-models/examples').json()[0]
            assert client.post('/api/marketing-models/booking-intent/score',json=example['features']).status_code==200
    finally:app.dependency_overrides.clear()
