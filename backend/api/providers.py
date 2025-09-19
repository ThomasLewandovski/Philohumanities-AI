from typing import Any, Dict, List

from fastapi import APIRouter

from ..app.dependencies import get_provider_registry


router = APIRouter(prefix="/api/providers", tags=["providers"])


@router.get("")
def list_providers() -> List[Dict[str, Any]]:
    reg = get_provider_registry()
    items = []
    for acc in reg.list():
        items.append(
            {
                "alias": acc.alias,
                "base_url": acc.base_url,
                "hasApiKey": bool(acc.api_key),
                "defaultModel": acc.default_model,
                "priority": acc.priority,
            }
        )
    return items
