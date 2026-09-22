from crewai import LLM

from ai.config import settings


def get_llm() -> LLM:
    """Возвращает LLM согласно .env. Единственная точка переключения провайдера."""
    if settings.llm_provider == "ollama":
        return LLM(
            model=f"ollama/{settings.ollama_model}",
            base_url=settings.ollama_base_url,
            temperature=settings.llm_temperature,
        )

    if not settings.qwen_api_key:
        raise RuntimeError(
            "LLM_PROVIDER=qwen_api, но QWEN_API_KEY пуст. Проверьте .env"
        )

    return LLM(
        model=f"dashscope/{settings.qwen_model}",
        base_url=settings.qwen_base_url,
        api_key=settings.qwen_api_key.get_secret_value(),
        temperature=settings.llm_temperature,
    )
