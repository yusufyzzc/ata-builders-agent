from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from task_agent.llm import LLMClient
from task_agent.models import TaskState, TaskType


class TaskInterpreter:
    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm or LLMClient()

    def interpret(self, raw_request: str) -> TaskState:
        state = TaskState(raw_request=raw_request)
        llm_data = self.llm.extract_task_json(raw_request)
        if llm_data:
            state.task_type = self._safe_task_type(llm_data.get("task_type"))
            state.slots = {k: v for k, v in (llm_data.get("slots") or {}).items() if v not in (None, "")}
            state.assumptions = list(llm_data.get("assumptions") or [])
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

    def _heuristic_extract(self, text: str) -> tuple[TaskType, dict[str, Any], list[str]]:
        lower = text.lower()
        slots: dict[str, Any] = {}
        assumptions: list[str] = []

        if any(word in lower for word in ["dentist", "doctor", "appointment", "book me"]):
            task_type = TaskType.APPOINTMENT
            if "dentist" in lower:
                slots["service_type"] = "dentist"
        elif "coworking" in lower or "co-working" in lower:
            task_type = TaskType.COWORKING_SEARCH
        elif any(word in lower for word in ["trip", "travel", "itinerary"]):
            task_type = TaskType.TRIP_PLANNING
        elif any(word in lower for word in ["meeting", "meet", "schedule"]):
            task_type = TaskType.MEETING
        elif "remind" in lower or "reminder" in lower:
            task_type = TaskType.REMINDER
        else:
            task_type = TaskType.UNKNOWN

        city = self._extract_known_city(lower)
        if city:
            slots["city"] = city

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

        date_range = self._extract_date_range(lower)
        if date_range:
            slots["date_range"] = date_range

        time_pref = self._extract_time_preference(lower)
        if time_pref:
            slots["time_preference"] = time_pref

        if task_type == TaskType.COWORKING_SEARCH and "count" not in slots:
            slots["count"] = 3
            assumptions.append("Defaulting coworking result count to 3.")

        return task_type, slots, assumptions

    @staticmethod
    def _extract_known_city(lower: str) -> str | None:
        cities = ["warsaw", "krakow", "berlin", "prague", "wroclaw", "poznan"]
        for city in cities:
            if city in lower:
                return city.title()
        return None

    @staticmethod
    def _extract_destination(text: str) -> str | None:
        match = re.search(r"(?:to|in)\s+([A-Z][a-zA-Z]+)", text)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def _extract_budget(text: str) -> dict[str, Any] | None:
        match = re.search(r"(?:under|below|up to|less than)?\s*([€$£])\s?(\d+)|(?:under|below|up to|less than)\s?(\d+)\s?(eur|euro|usd|dollars?)", text, re.I)
        if not match:
            return None
        symbol_amount = match.group(2)
        word_amount = match.group(3)
        amount = int(symbol_amount or word_amount)
        currency_raw = (match.group(1) or match.group(4) or "").lower()
        currency = {"€": "EUR", "$": "USD", "£": "GBP", "eur": "EUR", "euro": "EUR", "usd": "USD", "dollar": "USD", "dollars": "USD"}.get(currency_raw, "EUR")
        return {"amount": amount, "currency": currency}

    @staticmethod
    def _extract_duration(lower: str) -> int | None:
        match = re.search(r"(\d+)\s*[- ]?day", lower)
        return int(match.group(1)) if match else None

    @staticmethod
    def _extract_count(lower: str) -> int | None:
        match = re.search(r"find\s+(?:me\s+)?(\d+)", lower)
        return int(match.group(1)) if match else None

    @staticmethod
    def _extract_person(text: str) -> str | None:
        match = re.search(r"(?:with|meet)\s+([A-Z][a-zA-Z]+)", text)
        return match.group(1) if match else None

    @staticmethod
    def _extract_date_range(lower: str) -> str | None:
        today = date.today()
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
        if "after 5" in lower or "after 5pm" in lower or "after 17" in lower:
            return "after 17:00"
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
            match = re.search(r"(\d+)", text)
            if match:
                currency = "USD" if "$" in text else "EUR" if "€" in text or "eur" in text.lower() else "PLN" if "pln" in text.lower() else "EUR"
                return {"amount": int(match.group(1)), "currency": currency}
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
                "Check calendar availability",
                "Search matching services",
                "Book the best available option",
                "Create a reminder",
                "Summarize confirmation and blockers",
            ],
            TaskType.COWORKING_SEARCH: [
                "Extract city, budget and result count",
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
                "Check calendar availability",
                "Create meeting booking",
                "Create reminder",
                "Summarize schedule and blockers",
            ],
            TaskType.REMINDER: ["Extract reminder details", "Create reminder", "Summarize result"],
            TaskType.UNKNOWN: ["Ask for the user's goal and required constraints"],
        }
        return plans.get(task_type, plans[TaskType.UNKNOWN])
