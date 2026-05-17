"""Knowledge management API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.agent_runtime.skill_catalog import SkillCatalog
from app.api.providers import get_knowledge_service, get_skill_catalog
from app.api.responses import json_response
from app.application.knowledge_service import KnowledgeService

router = APIRouter(prefix="/knowledge")


class KnowledgeItemCreateRequest(BaseModel):
    knowledge_base_id: str
    item_type: str = Field(pattern="^(faq|sop|incident|document|summary)$")
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1)
    source_run_id: str | None = None
    metadata: dict[str, Any] | None = None


class KnowledgeItemPublishRequest(BaseModel):
    published_by: str = "system"


class SkillMatchRequest(BaseModel):
    scene: dict[str, Any] = Field(default_factory=dict)
    goal: str = Field(min_length=1)


@router.get("/items")
def list_knowledge_items(
    kb_id: str = Query(..., alias="kb_id"),
    item_type: str | None = Query(None),
    status: str = Query("published"),
    service: KnowledgeService = Depends(get_knowledge_service),
) -> dict[str, Any]:
    """List knowledge items by type and status."""
    from app.platform.persistence.repositories.knowledge_items import KnowledgeItemRepository

    repo = KnowledgeItemRepository()
    if item_type:
        items = repo.list_by_type(kb_id, item_type, status=status)
    else:
        # List all types
        items = []
        for t in ["faq", "sop", "incident", "document", "summary"]:
            items.extend(repo.list_by_type(kb_id, t, status=status))
    return {"items": items, "count": len(items)}


@router.post("/items")
def create_knowledge_item(
    req: KnowledgeItemCreateRequest,
    service: KnowledgeService = Depends(get_knowledge_service),
) -> dict[str, Any]:
    """Create a new knowledge item. Returns dedup_conflict if similar content exists."""
    result = service.create_item(
        kb_id=req.knowledge_base_id,
        item_type=req.item_type,
        title=req.title,
        content=req.content,
        source_run_id=req.source_run_id,
        metadata=req.metadata,
    )
    return json_response(result)


@router.get("/drafts")
def list_drafts(
    kb_id: str = Query(..., alias="kb_id"),
    service: KnowledgeService = Depends(get_knowledge_service),
) -> dict[str, Any]:
    """List draft knowledge items awaiting human confirmation."""
    drafts = service.list_drafts(kb_id)
    return {"items": drafts, "count": len(drafts)}


@router.post("/{item_id}/confirm")
def confirm_knowledge_item(
    item_id: int,
    req: KnowledgeItemPublishRequest = KnowledgeItemPublishRequest(),
    service: KnowledgeService = Depends(get_knowledge_service),
) -> dict[str, Any]:
    """Human confirms a draft knowledge item -> published."""
    service.publish_item(item_id, published_by=req.published_by)
    return {"status": "published", "item_id": item_id}


@router.post("/{item_id}/reject")
def reject_knowledge_item(
    item_id: int,
    service: KnowledgeService = Depends(get_knowledge_service),
) -> dict[str, Any]:
    """Human rejects a draft knowledge item -> archived."""
    service.reject_item(item_id, actor="api_user")
    return {"status": "archived", "item_id": item_id}


@router.get("/search")
def search_knowledge(
    kb_id: str = Query(..., alias="kb_id"),
    workspace_id: str = Query(..., alias="workspace_id"),
    query: str = Query(..., min_length=1),
    item_type: str | None = Query(None),
    top_k: int = Query(5, ge=1, le=20),
    service: KnowledgeService = Depends(get_knowledge_service),
) -> dict[str, Any]:
    """Vector search over published knowledge items."""
    results = service.search(
        workspace_id=workspace_id,
        kb_id=kb_id,
        query=query,
        item_type=item_type,
        top_k=top_k,
    )
    return {"results": results, "count": len(results)}


@router.get("/stats")
def knowledge_stats(
    kb_id: str = Query(..., alias="kb_id"),
    service: KnowledgeService = Depends(get_knowledge_service),
) -> dict[str, Any]:
    """Get knowledge item type distribution for release gate."""
    dist = service.get_type_distribution(kb_id)
    total = sum(dist.values())
    faq_count = dist.get("faq", 0)
    return {
        "distribution": dist,
        "total": total,
        "faq_ratio": faq_count / total if total > 0 else 0.0,
    }


@router.get("/badcase-clusters")
def list_badcase_clusters(
    kb_id: str = Query(..., alias="kb_id"),
    min_count: int = Query(5, ge=2),
) -> dict[str, Any]:
    """List badcase clusters ready for FAQ promotion.

    Placeholder: full clustering implemented in T094.
    """
    return {"clusters": [], "count": 0}


@router.get("/skills")
def list_skills(
    catalog: SkillCatalog = Depends(get_skill_catalog),
) -> dict[str, Any]:
    """List all active SRE skills."""
    from dataclasses import asdict

    skills = [asdict(s) for s in catalog.all_skills]
    return {"skills": skills, "count": len(skills)}


@router.get("/skills/{skill_id}")
def get_skill(
    skill_id: str,
    catalog: SkillCatalog = Depends(get_skill_catalog),
) -> dict[str, Any]:
    """Get a single skill manifest by id."""
    from dataclasses import asdict

    skill = catalog.get(skill_id)
    if skill is None:
        return json_response({"error": "skill not found"}, status_code=404)
    return asdict(skill)


@router.post("/skills/match")
def match_skills(
    req: SkillMatchRequest,
    catalog: SkillCatalog = Depends(get_skill_catalog),
) -> dict[str, Any]:
    """Match skills to a goal and scene."""
    from dataclasses import asdict

    matched = catalog.match(scene=req.scene, goal=req.goal)
    return {"skills": [asdict(s) for s in matched], "count": len(matched)}
