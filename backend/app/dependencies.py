from __future__ import annotations

from functools import lru_cache

from ..core.settings import Settings, get_settings as load_settings
from ..core.conversations.repository import Storage
from ..core.groups.repository import GroupStorage
from ..core.llm.client import LLMClient
from ..core.llm.providers import ProviderRegistry


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide Settings 单例，避免重复读取环境变量。"""
    return load_settings()


@lru_cache(maxsize=1)
def get_storage() -> Storage:
    settings = get_settings()
    return Storage(settings.data_dir)


@lru_cache(maxsize=1)
def get_group_storage() -> GroupStorage:
    settings = get_settings()
    return GroupStorage(settings.data_dir)


def get_llm_client() -> LLMClient:
    settings = get_settings()
    return LLMClient(base_url=settings.llm_base_url, api_key=settings.llm_api_key, default_model=settings.llm_model)


@lru_cache(maxsize=1)
def get_provider_registry() -> ProviderRegistry:
    return ProviderRegistry()
