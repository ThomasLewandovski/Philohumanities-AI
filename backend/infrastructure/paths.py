from __future__ import annotations

from pathlib import Path


_BACKEND_ROOT = Path(__file__).resolve().parent.parent


def backend_root() -> Path:
    """返回 backend 目录的绝对路径。"""
    return _BACKEND_ROOT


def prompts_dir() -> Path:
    """默认的 prompts 目录位置。"""
    return _BACKEND_ROOT / "prompts"


def resolve_data_dir(data_dir: str) -> Path:
    """根据配置解析数据目录，兼容相对路径。"""
    return Path(data_dir).expanduser().resolve()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
