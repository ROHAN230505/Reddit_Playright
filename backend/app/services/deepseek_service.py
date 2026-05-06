import requests

from app.config import settings


def deepseek_call(
    prompt: str,
    *,
    system_prompt: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    frequency_penalty: float | None = None,
) -> str:
    if not settings.deepseek_api_key:
        raise ValueError("DEEPSEEK_API_KEY is not configured.")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": settings.deepseek_model,
        "messages": messages,
        "temperature": settings.deepseek_temperature if temperature is None else temperature,
        "max_tokens": settings.deepseek_max_tokens if max_tokens is None else max_tokens,
        "frequency_penalty": (
            settings.deepseek_frequency_penalty
            if frequency_penalty is None
            else frequency_penalty
        ),
    }

    response = requests.post(
        "https://api.deepseek.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    return payload["choices"][0]["message"]["content"]
