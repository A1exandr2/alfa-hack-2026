import ollama 

from ml.llm_assistant.fallback import rule_based_fallback
from ml.llm_assistant.preprocessor import enrich_data_for_llm
from ml.llm_assistant.prompts import SYSTEM_PROMPT
from ml.llm_assistant.schemas import CreditAdvice

MODEL = "qwen3.5:4b"


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

        response = ollama.chat(
            model=MODEL, 
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT}, 
                {"role": "user", "content": user_content}
            ],
            format=CreditAdvice.model_json_schema(), 
            think=False, # Отключаем reasoning-режим
            options={"temperature": 0.1, "num_predict": 300},
        )
        ai_response = CreditAdvice.model_validate_json(
            response["message"]["content"]
        )
        return {"source": "AI", "data": ai_response.model_dump()}
    except Exception as e:
        print(f"[llm_assistant] AI error: {e}. Falling back to rules.")
        fb = rule_based_fallback(raw_data)
        return {"source": "Fallback_Rules", "data": fb.model_dump()}