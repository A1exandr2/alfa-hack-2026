import logging
import os

import ollama

from ml.llm_assistant.fallback import rule_based_fallback
from ml.llm_assistant.preprocessor import enrich_data_for_llm
from ml.llm_assistant.prompts import SYSTEM_PROMPT
from ml.llm_assistant.schemas import CreditAdvice

MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:4b")
logger = logging.getLogger(__name__)


def get_ai_advice(
    raw_data: dict, risk_score: float, risk_factors: list
) -> dict:
    """
    Возвращает {"source": "AI" | "Fallback_Rules", "data": {...}}.
    Никогда не падает - при любой ошибке Ollama возвращает fallback.
    """
    try:
        enriched = enrich_data_for_llm(raw_data, risk_score, risk_factors)
        user_content = (
            f"Контекст компании:\n{enriched['context']}\n\n"
            f"Запрос клиента: {enriched['safe_query']}"
        )

        client = ollama.Client(
            host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
            timeout=float(os.getenv("OLLAMA_TIMEOUT", "120")),
        )
        response = client.chat(
            model=MODEL, 
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT}, 
                {"role": "user", "content": user_content}
            ],
            format=CreditAdvice.model_json_schema(), 
            think=False, # Отключаем reasoning-режим
            options={"temperature": 0.1, "num_predict": 300, "num_ctx": 4096},
        )
        ai_response = CreditAdvice.model_validate_json(
            response["message"]["content"]
        )
        return {"source": "AI", "data": ai_response.model_dump()}
    except Exception as e:
        logger.warning("Ollama unavailable or invalid response (%s); using rules", type(e).__name__)
        fb = rule_based_fallback(raw_data, risk_score)
        return {"source": "Fallback_Rules", "data": fb.model_dump()}
