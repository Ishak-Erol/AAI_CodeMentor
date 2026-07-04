from __future__ import annotations

from codementor.config import AppConfig, get_config
from codementor.llm import BaseLLMClient, MockLLMClient, OpenAICompatibleLLMClient


def get_llm_client(
    config: AppConfig | None = None, enabled: bool | None = None
) -> BaseLLMClient:
    config = config or get_config()
    llm_enabled = config.llm_enabled if enabled is None else enabled
    if not llm_enabled:
        return MockLLMClient()
    return OpenAICompatibleLLMClient(
        api_key=config.llm_api_key,
        base_url=config.llm_base_url,
        model=config.llm_model,
    )
