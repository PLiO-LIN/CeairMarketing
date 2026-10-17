from __future__ import annotations

import json
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db_models import OntologyEntityRecord, OntologyRelationRecord
from ..models import GraphStats, MarketingGraph, OntologyEdge, OntologyNode, OntologySemanticStatus
from .semantic_model import SEMANTIC_MODEL_VERSION, object_type_ids, relation_type_ids


def build_campaign_graph(session: Session, tenant_id: int, campaign_id: str | None = None, limit: int = 300) -> MarketingGraph:
    entity_query = select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id == tenant_id)
    entities = []
    if campaign_id:
        campaign = session.scalar(entity_query.where(OntologyEntityRecord.external_id == campaign_id))
        if campaign is not None:
            entities = list(session.scalars(entity_query.where(
                (OntologyEntityRecord.id == campaign.id) |
                OntologyEntityRecord.attributes_json.contains('"campaign_id": ' + json.dumps(campaign_id), autoescape=True) |
                OntologyEntityRecord.attributes_json.contains('"campaign_id":' + json.dumps(campaign_id), autoescape=True))
                .order_by(OntologyEntityRecord.id).limit(limit)))
            by_id = {item.id: item for item in entities}
            connected_ids = set(by_id)
            for _ in range(4):
                if len(connected_ids) >= limit:
                    break
                all_relations = list(session.scalars(select(OntologyRelationRecord).where(
                    OntologyRelationRecord.tenant_id == tenant_id,
                    (OntologyRelationRecord.source_entity_id.in_(connected_ids)) |
                    (OntologyRelationRecord.target_entity_id.in_(connected_ids)))
                    .order_by(OntologyRelationRecord.id).limit(limit * 10)))
                candidate_ids = {r.source_entity_id for r in all_relations} | {r.target_entity_id for r in all_relations}
                by_id.update({item.id: item for item in session.scalars(entity_query.where(
                    OntologyEntityRecord.id.in_(candidate_ids)))})
                additions = set()
                for relation in all_relations:
                    target = by_id.get(relation.target_entity_id)
                    source = by_id.get(relation.source_entity_id)
                    if source is None or target is None:
                        continue
                    target_campaign = json.loads(target.attributes_json or "{}").get("campaign_id")
                    if source.id in connected_ids and target.entity_type != "Campaign" and target_campaign in {None, campaign_id}:
                        additions.add(target.id)
                    if target.id in connected_ids and source.entity_type in {"KnowledgeDocument", "KnowledgeChunk", "KnowledgeClaim", "Evidence", "MarketSignal"}:
                        additions.add(source.id)
                connected_ids.update(sorted(additions)[:max(0, limit - len(connected_ids))])
            entities = [by_id[item] for item in sorted(connected_ids)][:limit]
        else:
            entities = []
    else:
        entities = list(session.scalars(entity_query.order_by(OntologyEntityRecord.id).limit(limit)))
    ids = {item.id for item in entities}
    relations = list(
        session.scalars(
            select(OntologyRelationRecord).where(
                OntologyRelationRecord.tenant_id == tenant_id,
                OntologyRelationRecord.source_entity_id.in_(ids) if ids else OntologyRelationRecord.id == -1,
                OntologyRelationRecord.target_entity_id.in_(ids) if ids else OntologyRelationRecord.id == -1,
            )
        )
    )
    by_id = {item.id: item for item in entities}
    return MarketingGraph(
        campaign_id=campaign_id,
        nodes=[
            OntologyNode(
                id=item.external_id,
                type=item.entity_type,
                label=item.label,
                attributes=json.loads(item.attributes_json or "{}"),
                source=item.source,
                confidence=item.confidence,
            )
            for item in entities
        ],
        edges=[
            OntologyEdge(
                source=by_id[item.source_entity_id].external_id,
                relation=item.relation_type,
                target=by_id[item.target_entity_id].external_id,
                evidence=item.evidence,
                confidence=item.confidence,
            )
            for item in relations
        ],
    )


def graph_stats(session: Session, tenant_id: int) -> GraphStats:
    types = dict(session.execute(select(OntologyEntityRecord.entity_type, func.count()).where(
        OntologyEntityRecord.tenant_id == tenant_id).group_by(OntologyEntityRecord.entity_type)).all())
    relation_count = session.scalar(select(func.count()).select_from(OntologyRelationRecord).where(OntologyRelationRecord.tenant_id == tenant_id))
    return GraphStats(
        entity_count=sum(types.values()),
        relation_count=relation_count,
        entity_types=types,
        source_count=session.scalar(select(func.count(func.distinct(OntologyEntityRecord.source))).where(OntologyEntityRecord.tenant_id == tenant_id)),
    )


def semantic_status(session: Session, tenant_id: int) -> OntologySemanticStatus:
    entity_types = dict(session.execute(select(OntologyEntityRecord.entity_type, func.count()).where(
        OntologyEntityRecord.tenant_id == tenant_id).group_by(OntologyEntityRecord.entity_type)).all())
    relation_types = dict(session.execute(select(OntologyRelationRecord.relation_type, func.count()).where(
        OntologyRelationRecord.tenant_id == tenant_id).group_by(OntologyRelationRecord.relation_type)).all())
    registered_objects = object_type_ids()
    registered_relations = relation_type_ids()
    return OntologySemanticStatus(
        semantic_model_version=SEMANTIC_MODEL_VERSION,
        registered_object_type_count=len(registered_objects),
        registered_relation_type_count=len(registered_relations),
        instance_entity_count=sum(entity_types.values()),
        instance_relation_count=sum(relation_types.values()),
        registered_instance_types={key: value for key, value in entity_types.items() if key in registered_objects},
        legacy_or_extension_types={key: value for key, value in entity_types.items() if key not in registered_objects},
        registered_instance_relations={key: value for key, value in relation_types.items() if key in registered_relations},
        legacy_or_extension_relations={key: value for key, value in relation_types.items() if key not in registered_relations},
    )
