"""
Shared Gemini gateway for structured DailyAIWire AI calls.
Centralizes model invocation, JSON cleanup, schema validation, and audit logging.
"""
import json
import logging
import os
import sqlite3
from typing import Any

import google.generativeai as genai
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


class AIGateway:
    """Thin structured-output wrapper around google.generativeai."""

    def __init__(
        self,
        model_name: str,
        *,
        system_instruction: str | None = None,
        generation_config: dict[str, Any] | None = None,
        logger_name: str = 'ai_gateway',
    ):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not found in environment variables.")

        genai.configure(api_key=api_key)
        self.model_name = model_name
        self.logger = logging.getLogger(logger_name)
        self.model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system_instruction,
            generation_config=generation_config or {},
        )

    def generate_structured(
        self,
        prompt: str,
        schema: Any,
        *,
        prompt_type: str,
        request_options: dict[str, Any] | None = None,
        generation_config: dict[str, Any] | None = None,
    ):
        response = None
        raw_text = ""
        try:
            response = self.model.generate_content(
                prompt,
                generation_config=generation_config,
                request_options=request_options,
            )
            raw_text = getattr(response, 'text', '') or ''
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

    def _log_interaction(
        self,
        prompt_type: str,
        prompt_text: str,
        response_text: str,
        response: Any,
        *,
        error_text: str | None,
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
