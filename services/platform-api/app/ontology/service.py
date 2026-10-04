from __future__ import annotations

import json
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db_models import OntologyEntityRecord, OntologyRelationRecord
from ..models import GraphStats, MarketingGraph, OntologyEdge, OntologyNode, OntologySemanticStatus
from .semantic_model import SEMANTIC_MODEL_VERSION, object_type_ids, relation_type_ids


def build_campaign_graph(session: Session, tenant_id: int, campaign_id: str | None = None, limit: int = 300) -> MarketingGraph:
    entity_query = select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id == tenant_id)
    entities = list(session.scalars(entity_query.order_by(OntologyEntityRecord.id).limit(limit)))
    if campaign_id:
        campaign = session.scalar(select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id == tenant_id, OntologyEntityRecord.external_id == campaign_id))
        if campaign is not None:
            all_relations = list(
                session.scalars(select(OntologyRelationRecord).where(OntologyRelationRecord.tenant_id == tenant_id))
            )
            connected_ids = {campaign.id}
            for relation in all_relations:
                if relation.source_entity_id == campaign.id or relation.target_entity_id == campaign.id:
                    connected_ids.update({relation.source_entity_id, relation.target_entity_id})
            for relation in all_relations:
                if relation.source_entity_id in connected_ids or relation.target_entity_id in connected_ids:
                    connected_ids.update({relation.source_entity_id, relation.target_entity_id})
            entities = list(session.scalars(select(OntologyEntityRecord).where(OntologyEntityRecord.tenant_id == tenant_id, OntologyEntityRecord.id.in_(connected_ids)).order_by(OntologyEntityRecord.id).limit(limit)))
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
    entity_counts = dict(session.execute(select(OntologyEntityRecord.entity_type, func.count()).where(OntologyEntityRecord.tenant_id == tenant_id).group_by(OntologyEntityRecord.entity_type)).all())
    source_count = session.scalar(select(func.count(func.distinct(OntologyEntityRecord.source))).where(OntologyEntityRecord.tenant_id == tenant_id)) or 0
    relation_count = session.scalar(select(func.count()).select_from(OntologyRelationRecord).where(OntologyRelationRecord.tenant_id == tenant_id)) or 0
    return GraphStats(
        entity_count=sum(entity_counts.values()),
        relation_count=relation_count,
        entity_types=entity_counts,
        source_count=source_count,
    )


def semantic_status(session: Session, tenant_id: int) -> OntologySemanticStatus:
    entity_types = Counter(
        session.scalars(
            select(OntologyEntityRecord.entity_type).where(OntologyEntityRecord.tenant_id == tenant_id)
        )
    )
    relation_types = Counter(
        session.scalars(
            select(OntologyRelationRecord.relation_type).where(OntologyRelationRecord.tenant_id == tenant_id)
        )
    )
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
