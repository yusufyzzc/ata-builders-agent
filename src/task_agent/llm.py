from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


class LLMClient:
    """Minimal OpenAI Responses API client using only the standard library.

    The agent is intentionally runnable without third-party packages. If OPENAI_API_KEY
    is missing or the API call fails, callers can fall back to deterministic parsing.
    """

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def extract_task_json(self, user_request: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None

        system_prompt = (
            "You are an intent and slot extraction module for a task execution agent. "
            "Return ONLY valid JSON. No markdown. "
            "Schema: {task_type: one of appointment,coworking_search,trip_planning,meeting,reminder,unknown, "
            "slots: object, missing_fields: array of strings, assumptions: array of strings}. "
            "Use null for unknown slot values. Be conservative: mark essential missing data."
        )
        payload = {
            "model": self.model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_request},
            ],
            "temperature": 0.0,
        }

        request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return None

        text = self._extract_text(response_payload)
        if not text:
            return None

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _extract_text(payload: dict[str, Any]) -> str | None:
        if isinstance(payload.get("output_text"), str):
            return payload["output_text"]

        # Responses API responses may contain nested content blocks.
        for output_item in payload.get("output", []):
            for content in output_item.get("content", []):
                if content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                    return content["text"]
        return None
