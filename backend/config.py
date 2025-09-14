import os
from dotenv import load_dotenv


load_dotenv()


class Settings:
    def __init__(self) -> None:
        self.llm_base_url: str = (os.getenv("LLM_BASE_URL", "").rstrip("/"))
        self.llm_api_key: str | None = os.getenv("LLM_API_KEY") or None
        self.llm_model: str = os.getenv("LLM_MODEL", "")
        self.data_dir: str = os.getenv("DATA_DIR", "./data")
        env_origins = os.getenv("ALLOW_ORIGINS")
        self.allow_origins = [o.strip() for o in env_origins.split(",") if o.strip()] if env_origins else ["*"]


def get_settings() -> Settings:
    s = Settings()
    # 强制要求 LLM 配置（本项目不再支持无 LLM 场景）
    if not s.llm_base_url:
        raise RuntimeError("LLM_BASE_URL is not set in env")
    if not s.llm_model:
        raise RuntimeError("LLM_MODEL is not set in env")
    return s
