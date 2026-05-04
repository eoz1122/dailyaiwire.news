"""
Shared Gemini gateway for structured DailyAIWire AI calls.
Centralizes model invocation, JSON cleanup, schema validation, and audit logging.
"""
import json
import logging
import os
import sqlite3
from typing import Any, Optional

from google import genai
from google.genai import types
from pydantic import TypeAdapter

import db


logger = logging.getLogger('ai_gateway')


def _strip_markdown_fences(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[len("```json"):].strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned[len("```"):].strip()

    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()

    return cleaned


def _normalize_timeout_ms(request_options: Optional[dict[str, Any]]) -> Optional[int]:
    if not request_options:
        return None

    timeout = request_options.get("timeout")
    if timeout is None:
        return None

    timeout_value = float(timeout)
    if timeout_value <= 0:
        return None

    # Legacy google.generativeai accepted seconds; google-genai HttpOptions uses ms.
    if timeout_value <= 3600:
        timeout_value *= 1000

    return int(timeout_value)


class AIGateway:
    """Thin structured-output wrapper around google-genai."""

    def __init__(
        self,
        model_name: str,
        *,
        system_instruction: Optional[str] = None,
        generation_config: Optional[dict[str, Any]] = None,
        thinking_budget: Optional[int] = None,
        logger_name: str = 'ai_gateway',
    ):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not found in environment variables.")

        self.model_name = model_name
        self.system_instruction = system_instruction
        self.generation_config = generation_config or {}
        self.thinking_budget = thinking_budget
        self.logger = logging.getLogger(logger_name)
        self.client = genai.Client(api_key=api_key)

    def _build_config(
        self,
        generation_config: Optional[dict[str, Any]],
        request_options: Optional[dict[str, Any]],
    ) -> types.GenerateContentConfig:
        config_data = dict(self.generation_config)
        if generation_config:
            config_data.update(generation_config)

        if self.system_instruction:
            config_data.setdefault("system_instruction", self.system_instruction)

        if self.thinking_budget is not None:
            config_data.setdefault(
                "thinking_config",
                types.ThinkingConfig(thinking_budget=self.thinking_budget),
            )

        timeout_ms = _normalize_timeout_ms(request_options)
        if timeout_ms is not None:
            config_data.setdefault("http_options", types.HttpOptions(timeout=timeout_ms))

        return types.GenerateContentConfig(**config_data)

    def generate_structured(
        self,
        prompt: str,
        schema: Any,
        *,
        prompt_type: str,
        request_options: Optional[dict[str, Any]] = None,
        generation_config: Optional[dict[str, Any]] = None,
    ):
        response = None
        raw_text = ""
        try:
            response, raw_text = self._generate(
                prompt,
                request_options=request_options,
                generation_config=generation_config,
            )
            payload = json.loads(_strip_markdown_fences(raw_text))
            validated = TypeAdapter(schema).validate_python(payload)
            self._log_interaction(prompt_type, prompt, raw_text, response, error_text=None)
            return validated, response
        except Exception as exc:
            self._log_interaction(
                prompt_type,
                prompt,
                raw_text,
                response,
                error_text=str(exc),
            )
            raise

    def generate_text(
        self,
        prompt: str,
        *,
        prompt_type: str,
        request_options: Optional[dict[str, Any]] = None,
        generation_config: Optional[dict[str, Any]] = None,
    ):
        response = None
        raw_text = ""
        try:
            response, raw_text = self._generate(
                prompt,
                request_options=request_options,
                generation_config=generation_config,
            )
            self._log_interaction(prompt_type, prompt, raw_text, response, error_text=None)
            return raw_text, response
        except Exception as exc:
            self._log_interaction(prompt_type, prompt, raw_text, response, error_text=str(exc))
            raise

    def _generate(
        self,
        prompt: str,
        *,
        request_options: Optional[dict[str, Any]],
        generation_config: Optional[dict[str, Any]],
    ):
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=self._build_config(generation_config, request_options),
        )
        return response, getattr(response, 'text', '') or ''

    def _log_interaction(
        self,
        prompt_type: str,
        prompt_text: str,
        response_text: str,
        response: Any,
        *,
        error_text: Optional[str],
    ) -> None:
        try:
            conn = sqlite3.connect(db.DB_PATH)
            cur = conn.cursor()
            cur.execute('''
                CREATE TABLE IF NOT EXISTS ai_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    model TEXT,
                    prompt_type TEXT,
                    prompt_text TEXT,
                    response_text TEXT,
                    cost_estimate REAL
                )
            ''')

            usage = getattr(response, 'usage_metadata', None)
            token_total = None
            if usage is not None:
                prompt_tokens = getattr(usage, 'prompt_token_count', 0) or 0
                output_tokens = getattr(usage, 'candidates_token_count', 0) or 0
                thoughts_tokens = getattr(usage, 'thoughts_token_count', 0) or 0
                token_total = getattr(usage, 'total_token_count', None)
                if token_total is None:
                    token_total = prompt_tokens + output_tokens + thoughts_tokens
                token_total = float(token_total)

            stored_response = response_text
            if error_text:
                stored_response = f"ERROR: {error_text}\n\n{response_text}"

            cur.execute(
                '''
                INSERT INTO ai_logs (model, prompt_type, prompt_text, response_text, cost_estimate)
                VALUES (?, ?, ?, ?, ?)
                ''',
                (
                    self.model_name,
                    prompt_type,
                    prompt_text,
                    stored_response,
                    token_total,
                ),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            self.logger.warning("Failed to write ai_logs entry: %s", exc)
