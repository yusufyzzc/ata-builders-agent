from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from task_agent.llm import LLMClient
from task_agent.models import TaskState, TaskType


class TaskInterpreter:
    """Converts a natural-language request into a structured task state.

    The heuristic parser is intentionally conservative, but it should still use
    the data the user actually provides. In particular, it avoids a fixed city
    allow-list so requests for less common cities do not get silently dropped.
    """

    LOCATION_STOPWORDS = {
        "a",
        "an",
        "any",
        "appointment",
        "budget",
        "coworking",
        "day",
        "dentist",
        "doctor",
        "find",
        "for",
        "from",
        "in",
        "me",
        "meeting",
        "near",
        "next",
        "office",
        "plan",
        "schedule",
        "space",
        "spaces",
        "the",
        "this",
        "to",
        "trip",
        "under",
        "with",
    }

    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm or LLMClient()

    def interpret(self, raw_request: str) -> TaskState:
        state = TaskState(raw_request=raw_request)
        llm_data = self.llm.extract_task_json(raw_request)
        if llm_data:
            state.task_type = self._safe_task_type(llm_data.get("task_type"))
            state.slots = {k: v for k, v in (llm_data.get("slots") or {}).items() if v not in (None, "")}
            state.assumptions = list(llm_data.get("assumptions") or [])
            # Even when the LLM is used, lightly backfill obvious deterministic slots.
            self._backfill_obvious_slots(raw_request, state)
        else:
            state.task_type, state.slots, state.assumptions = self._heuristic_extract(raw_request)

        state.missing_fields = self._missing_fields(state.task_type, state.slots)
        state.plan = self._build_plan(state.task_type)
        return state

    def merge_clarification(self, state: TaskState, field_name: str, answer: str) -> TaskState:
        state.slots[field_name] = self._normalize_slot_value(field_name, answer)
        state.missing_fields = self._missing_fields(state.task_type, state.slots)
        return state

    @staticmethod
    def _safe_task_type(value: Any) -> TaskType:
        try:
            return TaskType(str(value))
        except ValueError:
            return TaskType.UNKNOWN

    def _backfill_obvious_slots(self, text: str, state: TaskState) -> None:
        lower = text.lower()
        if "budget" not in state.slots:
            budget = self._extract_budget(text)
            if budget:
                state.slots["budget"] = budget
        if "count" not in state.slots and state.task_type == TaskType.COWORKING_SEARCH:
            count = self._extract_count(lower)
            if count:
                state.slots["count"] = count
        if "city" not in state.slots and state.task_type in {TaskType.APPOINTMENT, TaskType.COWORKING_SEARCH}:
            city = self._extract_location_after_preposition(text)
            if city:
                state.slots["city"] = city

    def _heuristic_extract(self, text: str) -> tuple[TaskType, dict[str, Any], list[str]]:
        lower = text.lower()
        slots: dict[str, Any] = {}
        assumptions: list[str] = []

        if "coworking" in lower or "co-working" in lower:
            task_type = TaskType.COWORKING_SEARCH
        elif any(word in lower for word in ["dentist", "doctor", "appointment", "book me"]):
            task_type = TaskType.APPOINTMENT
            service_type = self._extract_service_type(lower)
            if service_type:
                slots["service_type"] = service_type
        elif any(word in lower for word in ["trip", "travel", "itinerary"]):
            task_type = TaskType.TRIP_PLANNING
        elif any(word in lower for word in ["meeting", "meet", "schedule"]):
            task_type = TaskType.MEETING
        elif "remind" in lower or "reminder" in lower:
            task_type = TaskType.REMINDER
        else:
            task_type = TaskType.UNKNOWN

        location = self._extract_location_after_preposition(text)
        if location and task_type in {TaskType.APPOINTMENT, TaskType.COWORKING_SEARCH}:
            slots["city"] = location

        destination = self._extract_destination(text)
        if destination and task_type == TaskType.TRIP_PLANNING:
            slots["destination"] = destination

        budget = self._extract_budget(text)
        if budget:
            slots["budget"] = budget

        duration = self._extract_duration(lower)
        if duration:
            slots["duration_days"] = duration

        count = self._extract_count(lower)
        if count and task_type == TaskType.COWORKING_SEARCH:
            slots["count"] = count

        person = self._extract_person(text)
        if person and task_type == TaskType.MEETING:
            slots["attendee_name"] = person

        email = self._extract_email(text)
        if email and task_type == TaskType.MEETING:
            slots["attendee_email"] = email

        reminder_text = self._extract_reminder_text(text)
        if reminder_text and task_type == TaskType.REMINDER:
            slots["reminder_text"] = reminder_text

        date_range = self._extract_date_range(lower)
        if date_range:
            slots["date_range"] = date_range

        time_pref = self._extract_time_preference(lower)
        if time_pref:
            slots["time_preference"] = time_pref

        if task_type == TaskType.COWORKING_SEARCH and "count" not in slots:
            slots["count"] = 3
            assumptions.append("Defaulting coworking result count to 3 because the user did not specify a number.")

        return task_type, slots, assumptions

    @classmethod
    def _extract_location_after_preposition(cls, text: str) -> str | None:
        """Extract user-provided locations without a hard-coded city allow-list."""
        patterns = [
            r"\b(?:in|near|around)\s+([A-Z][A-Za-zÀ-ž'\-]*(?:\s+[A-Z][A-Za-zÀ-ž'\-]*){0,2})",
            r"\b(?:in|near|around)\s+([a-z][a-zà-ž'\-]*(?:\s+[a-z][a-zà-ž'\-]*){0,2})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            candidate = cls._clean_location_candidate(match.group(1))
            if candidate:
                return candidate
        return None

    @classmethod
    def _clean_location_candidate(cls, candidate: str) -> str | None:
        words = []
        for raw_word in re.split(r"\s+", candidate.strip()):
            word = re.sub(r"[^A-Za-zÀ-ž'\-]", "", raw_word)
            if not word:
                continue
            if word.lower() in cls.LOCATION_STOPWORDS:
                break
            words.append(word)
        if not words:
            return None
        return " ".join(word[:1].upper() + word[1:] for word in words)

    @staticmethod
    def _extract_service_type(lower: str) -> str | None:
        if "dentist" in lower:
            return "dentist"
        if "doctor" in lower:
            return "doctor"
        match = re.search(r"book\s+(?:me\s+)?(?:a|an)?\s*([a-z\- ]+?)\s+appointment", lower)
        if match:
            return match.group(1).strip()
        return None

    @staticmethod
    def _extract_destination(text: str) -> str | None:
        patterns = [
            r"\btrip\s+to\s+([A-Z][A-Za-zÀ-ž'\-]*(?:\s+[A-Z][A-Za-zÀ-ž'\-]*){0,2})",
            r"\btravel\s+to\s+([A-Z][A-Za-zÀ-ž'\-]*(?:\s+[A-Z][A-Za-zÀ-ž'\-]*){0,2})",
            r"\bitinerary\s+for\s+([A-Z][A-Za-zÀ-ž'\-]*(?:\s+[A-Z][A-Za-zÀ-ž'\-]*){0,2})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return TaskInterpreter._clean_location_candidate(match.group(1))
        return None

    @staticmethod
    def _extract_budget(text: str) -> dict[str, Any] | None:
        # Supports: "$20/day", "under 20 dollars", "less than 300 EUR", "under 80".
        match = re.search(
            r"(?:under|below|up to|less than|max(?:imum)?)?\s*([€$£])\s?(\d+)"
            r"|(?:under|below|up to|less than|max(?:imum)?)\s?(\d+)\s?(eur|euro|euros|usd|dollar|dollars|gbp|pln|zloty|zł)?",
            text,
            re.I,
        )
        if not match:
            return None
        symbol_amount = match.group(2)
        word_amount = match.group(3)
        amount = int(symbol_amount or word_amount)
        currency_raw = (match.group(1) or match.group(4) or "").lower()
        currency = {
            "€": "EUR",
            "$": "USD",
            "£": "GBP",
            "eur": "EUR",
            "euro": "EUR",
            "euros": "EUR",
            "usd": "USD",
            "dollar": "USD",
            "dollars": "USD",
            "gbp": "GBP",
            "pln": "PLN",
            "zloty": "PLN",
            "zł": "PLN",
        }.get(currency_raw, "UNSPECIFIED")
        return {"amount": amount, "currency": currency}

    @staticmethod
    def _extract_duration(lower: str) -> int | None:
        match = re.search(r"(\d+)\s*[- ]?day", lower)
        return int(match.group(1)) if match else None

    @staticmethod
    def _extract_count(lower: str) -> int | None:
        match = re.search(r"(?:find|show|return|give)\s+(?:me\s+)?(\d+)", lower)
        return int(match.group(1)) if match else None

    @staticmethod
    def _extract_person(text: str) -> str | None:
        match = re.search(r"(?:with|meet)\s+([A-Z][a-zA-Z]+)", text)
        return match.group(1) if match else None

    @staticmethod
    def _extract_email(text: str) -> str | None:
        match = re.search(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", text)
        return match.group(0) if match else None

    @staticmethod
    def _extract_reminder_text(text: str) -> str | None:
        match = re.search(r"remind\s+me\s+to\s+(.+?)(?:\s+(?:tomorrow|next\s+\w+|at\s+\d+|on\s+\w+)|$)", text, re.I)
        return match.group(1).strip() if match else None

    @staticmethod
    def _extract_date_range(lower: str) -> str | None:
        today = date.today()
        if "tomorrow" in lower:
            return (today + timedelta(days=1)).isoformat()
        if "next week" in lower:
            start = today + timedelta(days=(7 - today.weekday()))
            end = start + timedelta(days=6)
            return f"{start.isoformat()} to {end.isoformat()}"
        weekdays = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }
        for name, number in weekdays.items():
            if name in lower:
                days_ahead = (number - today.weekday()) % 7 or 7
                target = today + timedelta(days=days_ahead)
                return target.isoformat()
        return None

    @staticmethod
    def _extract_time_preference(lower: str) -> str | None:
        explicit_time = re.search(r"(?:at|after|before)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", lower)
        if explicit_time:
            hour = int(explicit_time.group(1))
            minute = explicit_time.group(2) or "00"
            meridiem = explicit_time.group(3)
            if meridiem == "pm" and hour < 12:
                hour += 12
            if "after" in explicit_time.group(0):
                return f"after {hour:02d}:{minute}"
            if "before" in explicit_time.group(0):
                return f"before {hour:02d}:{minute}"
            return f"at {hour:02d}:{minute}"
        if "afternoon" in lower:
            return "afternoon"
        if "morning" in lower:
            return "morning"
        if "evening" in lower:
            return "evening"
        return None

    @staticmethod
    def _normalize_slot_value(field_name: str, answer: str) -> Any:
        text = answer.strip()
        if field_name in {"count", "duration_days"}:
            match = re.search(r"\d+", text)
            return int(match.group()) if match else text
        if field_name == "budget":
            budget = TaskInterpreter._extract_budget(text)
            return budget or text
        if field_name in {"city", "destination"}:
            cleaned = TaskInterpreter._clean_location_candidate(text)
            return cleaned or text
        return text

    @staticmethod
    def _missing_fields(task_type: TaskType, slots: dict[str, Any]) -> list[str]:
        required: dict[TaskType, list[str]] = {
            TaskType.APPOINTMENT: ["service_type", "city", "date_range", "time_preference"],
            TaskType.COWORKING_SEARCH: ["city", "budget", "count"],
            TaskType.TRIP_PLANNING: ["destination", "duration_days", "budget"],
            TaskType.MEETING: ["attendee_name", "attendee_email", "date_range", "time_preference"],
            TaskType.REMINDER: ["reminder_text", "date_range"],
            TaskType.UNKNOWN: ["task_goal"],
        }
        return [field for field in required.get(task_type, []) if not slots.get(field)]

    @staticmethod
    def _build_plan(task_type: TaskType) -> list[str]:
        plans = {
            TaskType.APPOINTMENT: [
                "Extract appointment constraints",
                "Ask only for missing appointment details",
                "Check calendar availability",
                "Search matching services",
                "Book the best available option",
                "Create a reminder",
                "Summarize confirmation and blockers",
            ],
            TaskType.COWORKING_SEARCH: [
                "Extract city, budget and result count",
                "Ask only for missing search constraints",
                "Search coworking spaces",
                "Filter by price and rank options",
                "Summarize recommendations and limitations",
            ],
            TaskType.TRIP_PLANNING: [
                "Extract destination, duration and budget",
                "Search transport, stay and activities",
                "Build itinerary under budget",
                "Summarize plan and trade-offs",
            ],
            TaskType.MEETING: [
                "Extract attendee and timing constraints",
                "Ask for missing attendee details",
                "Check calendar availability",
                "Create meeting booking",
                "Create reminder",
                "Summarize schedule and blockers",
            ],
            TaskType.REMINDER: ["Extract reminder details", "Create reminder", "Summarize result"],
            TaskType.UNKNOWN: ["Ask for the user's goal and required constraints"],
        }
        return plans.get(task_type, plans[TaskType.UNKNOWN])
