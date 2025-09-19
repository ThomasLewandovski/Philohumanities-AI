from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from ..core.roles.registry import RoleCardRegistry


router = APIRouter(prefix="/api/role-cards", tags=["role-cards"])


def _registry() -> RoleCardRegistry:
    return RoleCardRegistry()


@router.get("")
def list_roles() -> List[Dict[str, Any]]:
    items = []
    for r in _registry().list():
        items.append(
            {
                "id": r.slug,
                "slug": r.slug,
                "name": r.name,
                "tags": [],
                "locales": r.locales or ["zh-CN"],
            }
        )
    return items


@router.get("/{slug}")
def get_role(slug: str) -> Dict[str, Any]:
    r = _registry().get(slug)
    if not r:
        raise HTTPException(status_code=404, detail="role card not found")
    return {
        "id": r.slug,
        "slug": r.slug,
        "name": r.name,
        "styleHints": r.style_hints,
        "greeting": r.greeting,
        "locales": r.locales or ["zh-CN"],
    }
