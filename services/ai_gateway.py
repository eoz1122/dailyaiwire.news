"""
Shared Gemini gateway for structured DailyAIWire AI calls.
Centralizes model invocation, JSON cleanup, schema validation, and audit logging.
"""
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

from google import genai
from google.genai import types
from pydantic import TypeAdapter

import db


logger = logging.getLogger('ai_gateway')


AI_LOG_COLUMNS = {
    "prompt_tokens": "ALTER TABLE ai_logs ADD COLUMN prompt_tokens INTEGER",
    "output_tokens": "ALTER TABLE ai_logs ADD COLUMN output_tokens INTEGER",
    "thoughts_tokens": "ALTER TABLE ai_logs ADD COLUMN thoughts_tokens INTEGER",
    "total_tokens": "ALTER TABLE ai_logs ADD COLUMN total_tokens INTEGER",
    "cached_input_tokens": "ALTER TABLE ai_logs ADD COLUMN cached_input_tokens INTEGER",
    "prompt_char_count": "ALTER TABLE ai_logs ADD COLUMN prompt_char_count INTEGER",
    "response_char_count": "ALTER TABLE ai_logs ADD COLUMN response_char_count INTEGER",
    "request_status": "ALTER TABLE ai_logs ADD COLUMN request_status TEXT",
}


def _fallback_log_path() -> str:
    return os.getenv(
        "AI_LOG_FALLBACK_PATH",
        os.path.join(os.path.dirname(db.DB_PATH), "logs", "ai_logs_fallback.jsonl"),
    )


def _extract_usage_counts(response: Any) -> dict[str, Optional[int]]:
    usage = getattr(response, 'usage_metadata', None)
    prompt_tokens = 0
    output_tokens = 0
    thoughts_tokens = 0
    cached_input_tokens = 0
    token_total = None

    if usage is not None:
        prompt_tokens = int(getattr(usage, 'prompt_token_count', 0) or 0)
        output_tokens = int(getattr(usage, 'candidates_token_count', 0) or 0)
        thoughts_tokens = int(getattr(usage, 'thoughts_token_count', 0) or 0)
        cached_input_tokens = int(
            getattr(usage, 'cached_content_token_count', 0)
            or getattr(usage, 'cached_input_token_count', 0)
            or 0
        )
        token_total = getattr(usage, 'total_token_count', None)
        if token_total is None:
            token_total = prompt_tokens + output_tokens + thoughts_tokens
        token_total = int(token_total)

    return {
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "thoughts_tokens": thoughts_tokens,
        "cached_input_tokens": cached_input_tokens,
        "total_tokens": token_total,
    }


def _write_ai_log_fallback(
    *,
    model_name: str,
    prompt_type: str,
    prompt_text: str,
    response_text: str,
    request_status: str,
    usage_counts: dict[str, Optional[int]],
    db_error: str,
) -> None:
    fallback_path = _fallback_log_path()
    os.makedirs(os.path.dirname(fallback_path), exist_ok=True)

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model_name,
        "prompt_type": prompt_type,
        "request_status": request_status,
        "prompt_tokens": usage_counts["prompt_tokens"],
        "output_tokens": usage_counts["output_tokens"],
        "thoughts_tokens": usage_counts["thoughts_tokens"],
        "cached_input_tokens": usage_counts["cached_input_tokens"],
        "total_tokens": usage_counts["total_tokens"],
        "prompt_char_count": len(prompt_text or ""),
        "response_char_count": len(response_text or ""),
        "db_error": db_error,
    }

    with open(fallback_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")


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


def ensure_ai_logs_schema(cur: sqlite3.Cursor) -> None:
    cur.execute('''
        CREATE TABLE IF NOT EXISTS ai_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            model TEXT,
            prompt_type TEXT,
            prompt_text TEXT,
            response_text TEXT,
            cost_estimate REAL,
            prompt_tokens INTEGER,
            output_tokens INTEGER,
            thoughts_tokens INTEGER,
            total_tokens INTEGER,
            cached_input_tokens INTEGER,
            prompt_char_count INTEGER,
            response_char_count INTEGER,
            request_status TEXT
        )
    ''')

    existing_columns = {row[1] for row in cur.execute("PRAGMA table_info(ai_logs)").fetchall()}
    for column_name, ddl in AI_LOG_COLUMNS.items():
        if column_name not in existing_columns:
            cur.execute(ddl)


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
        usage_counts = _extract_usage_counts(response)
        stored_response = response_text
        if error_text:
            stored_response = f"ERROR: {error_text}\n\n{response_text}"

        request_status = "ERROR" if error_text else "SUCCESS"
        conn = None
        try:
            timeout = float(os.getenv("AI_LOG_DB_TIMEOUT_SECONDS", "30"))
            conn = db.get_db_connection(timeout=timeout)
            cur = conn.cursor()
            ensure_ai_logs_schema(cur)

            cur.execute(
                '''
                INSERT INTO ai_logs (
                    model,
                    prompt_type,
                    prompt_text,
                    response_text,
                    cost_estimate,
                    prompt_tokens,
                    output_tokens,
                    thoughts_tokens,
                    total_tokens,
                    cached_input_tokens,
                    prompt_char_count,
                    response_char_count,
                    request_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    self.model_name,
                    prompt_type,
                    prompt_text,
                    stored_response,
                    float(usage_counts["total_tokens"]) if usage_counts["total_tokens"] is not None else None,
                    usage_counts["prompt_tokens"],
                    usage_counts["output_tokens"],
                    usage_counts["thoughts_tokens"],
                    usage_counts["total_tokens"],
                    usage_counts["cached_input_tokens"],
                    len(prompt_text or ""),
                    len(response_text or ""),
                    request_status,
                ),
            )
            conn.commit()
        except Exception as exc:
            try:
                _write_ai_log_fallback(
                    model_name=self.model_name,
                    prompt_type=prompt_type,
                    prompt_text=prompt_text,
                    response_text=response_text,
                    request_status=request_status,
                    usage_counts=usage_counts,
                    db_error=str(exc),
                )
            except Exception as fallback_exc:
                self.logger.warning("Failed to write ai_logs fallback entry: %s", fallback_exc)
            self.logger.warning("Failed to write ai_logs entry: %s", exc)
        finally:
            if conn is not None:
                conn.close()
