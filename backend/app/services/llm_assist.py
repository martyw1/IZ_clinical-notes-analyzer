from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.models.models import AppSetting

logger = logging.getLogger(__name__)


def llm_is_configured(app_settings: AppSetting | None) -> bool:
    if app_settings is None:
        return False
    return bool(
        app_settings.llm_enabled
        and app_settings.llm_api_key.strip()
        and app_settings.llm_base_url.strip()
        and app_settings.llm_model.strip()
    )


def _extract_content(payload: dict[str, Any]) -> str | None:
    choices = payload.get('choices')
    if not isinstance(choices, list) or not choices:
        return None
    message = choices[0].get('message') if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        return None
    content = message.get('content')
    if isinstance(content, str):
        return content.strip() or None
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get('text'), str):
                parts.append(item['text'])
        text = ''.join(parts).strip()
        return text or None
    return None


def call_llm_text(
    app_settings: AppSetting | None,
    *,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 400,
    temperature: float = 0.1,
) -> str | None:
    if not llm_is_configured(app_settings):
        return None

    endpoint = f"{app_settings.llm_base_url.rstrip('/')}/chat/completions"
    payload = {
        'model': app_settings.llm_model,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
        'temperature': temperature,
        'max_tokens': max_tokens,
    }
    headers = {
        'Authorization': f'Bearer {app_settings.llm_api_key}',
        'Content-Type': 'application/json',
    }

    try:
        with httpx.Client(timeout=max(1, app_settings.access_lookup_timeout_seconds)) as client:
            response = client.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()
            return _extract_content(response.json())
    except Exception as exc:  # pragma: no cover - exercised indirectly via runtime failures
        logger.warning('LLM request failed: %s', exc)
        return None


def call_llm_json(
    app_settings: AppSetting | None,
    *,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 600,
    temperature: float = 0.1,
) -> dict[str, Any] | None:
    text = call_llm_text(
        app_settings,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    if not text:
        return None

    candidate = text.strip()
    if candidate.startswith('```'):
        candidate = candidate.strip('`')
        if candidate.startswith('json'):
            candidate = candidate[4:].strip()

    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        logger.warning('LLM JSON response could not be parsed.')
        return None
    return payload if isinstance(payload, dict) else None
