from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from task_agent.models import ToolResult, ToolStatus


class MockTools:
    """Mock tools required by the assignment.

    These are deliberately deterministic: reviewers can run the same request and get
    predictable output without external accounts or paid services.
    """

    def calendar_check(self, date_range: str, time_preference: str | None = None) -> ToolResult:
        if "failure" in date_range.lower():
            return ToolResult("calendar_check", ToolStatus.FAILURE, message="Calendar provider timed out.")

        slots = [
            {"start": "2026-05-05 17:30", "end": "2026-05-05 18:00"},
            {"start": "2026-05-06 18:15", "end": "2026-05-06 18:45"},
            {"start": "2026-05-07 16:00", "end": "2026-05-07 16:30"},
        ]
        if time_preference == "morning":
            slots = [{"start": "2026-05-05 09:30", "end": "2026-05-05 10:00"}]
        elif time_preference == "afternoon":
            slots = [{"start": "2026-05-05 14:00", "end": "2026-05-05 14:30"}]
        elif time_preference and "after 17" in time_preference:
            slots = [slot for slot in slots if int(slot["start"].split()[1].split(":")[0]) >= 17]

        if not slots:
            return ToolResult("calendar_check", ToolStatus.NO_RESULTS, message="No free slots match the time preference.")

        return ToolResult(
            "calendar_check",
            ToolStatus.SUCCESS,
            data={"date_range": date_range, "available_slots": slots},
            message=f"Found {len(slots)} available slot(s).",
        )

    def search_service(self, query: str, constraints: dict[str, Any] | None = None) -> ToolResult:
        constraints = constraints or {}
        q = query.lower()
        if "api failure" in q:
            return ToolResult("search_service", ToolStatus.FAILURE, message="Search provider unavailable.")

        if "dentist" in q:
            city = constraints.get("city", "Warsaw")
            results = [
                {"id": "dent-1", "name": "SmileCare Dental", "city": city, "rating": 4.8, "slot": "2026-05-05 17:30", "price": "consultation 180 PLN"},
                {"id": "dent-2", "name": "Dental Point", "city": city, "rating": 4.6, "slot": "2026-05-06 18:15", "price": "consultation 160 PLN"},
            ]
        elif "coworking" in q:
            city = str(constraints.get("city", "Warsaw")).title()
            results = [
                {"id": "cow-1", "name": "WorkHub Central", "city": city, "price_per_day": 15, "currency": "USD", "features": ["Wi-Fi", "coffee", "phone booths"]},
                {"id": "cow-2", "name": "Focus Space", "city": city, "price_per_day": 18, "currency": "USD", "features": ["quiet zone", "meeting rooms"]},
                {"id": "cow-3", "name": "Startup Loft", "city": city, "price_per_day": 12, "currency": "USD", "features": ["community events", "24/7 access"]},
                {"id": "cow-4", "name": "Premium Desk", "city": city, "price_per_day": 29, "currency": "USD", "features": ["premium address"]},
            ]
            budget = constraints.get("budget") or {}
            amount = budget.get("amount") if isinstance(budget, dict) else None
            if amount:
                results = [item for item in results if item.get("price_per_day", 10**9) <= amount]
            count = int(constraints.get("count", 3))
            results = results[:count]
        elif "trip" in q or "itinerary" in q or "prague" in q:
            destination = constraints.get("destination", "Prague")
            results = [
                {"id": "stay-1", "type": "stay", "name": "Budget Guesthouse", "cost": 95, "currency": "EUR"},
                {"id": "transport-1", "type": "transport", "name": "Round-trip train", "cost": 70, "currency": "EUR"},
                {"id": "food-1", "type": "food", "name": "Local meals budget", "cost": 80, "currency": "EUR"},
                {"id": "act-1", "type": "activity", "name": f"{destination} Old Town walk", "cost": 0, "currency": "EUR"},
                {"id": "act-2", "type": "activity", "name": "Museum / castle ticket", "cost": 18, "currency": "EUR"},
            ]
        else:
            return ToolResult("search_service", ToolStatus.NO_RESULTS, message="No mock dataset matched the query.")

        if not results:
            return ToolResult("search_service", ToolStatus.NO_RESULTS, message="No result matched the constraints.")

        return ToolResult("search_service", ToolStatus.SUCCESS, data={"query": query, "results": results}, message=f"Found {len(results)} result(s).")

    def booking_service(self, option: dict[str, Any]) -> ToolResult:
        if not option:
            return ToolResult("booking_service", ToolStatus.FAILURE, message="No booking option was provided.")
        if option.get("id") == "unavailable":
            return ToolResult("booking_service", ToolStatus.NO_RESULTS, message="Selected option is no longer available.")

        confirmation_seed = f"{option.get('id')}:{datetime.now(UTC).date().isoformat()}"
        confirmation_code = hashlib.sha1(confirmation_seed.encode()).hexdigest()[:8].upper()
        return ToolResult(
            "booking_service",
            ToolStatus.SUCCESS,
            data={"confirmation_code": confirmation_code, "booked_option": option},
            message="Booking completed in mock mode.",
        )

    def reminder_create(self, details: dict[str, Any]) -> ToolResult:
        if not details.get("title"):
            return ToolResult("reminder_create", ToolStatus.FAILURE, message="Reminder title is required.")
        reminder_id = hashlib.md5(str(details).encode()).hexdigest()[:8]
        return ToolResult(
            "reminder_create",
            ToolStatus.SUCCESS,
            data={"reminder_id": reminder_id, "details": details},
            message="Reminder created in mock mode.",
        )
