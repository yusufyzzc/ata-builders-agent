from __future__ import annotations

from typing import Callable

from task_agent.interpreter import TaskInterpreter
from task_agent.models import TaskState, TaskType, ToolStatus
from task_agent.tools import MockTools

Clarifier = Callable[[str, str], str]


class TaskExecutionAgent:
    def __init__(self, interpreter: TaskInterpreter | None = None, tools: MockTools | None = None) -> None:
        self.interpreter = interpreter or TaskInterpreter()
        self.tools = tools or MockTools()

    def run(self, user_request: str, clarify: Clarifier | None = None) -> TaskState:
        state = self.interpreter.interpret(user_request)

        while state.missing_fields:
            if clarify is None:
                state.blockers.append("Missing required information: " + ", ".join(state.missing_fields))
                state.final_answer = self._format_final_answer(state)
                return state
            field_name = state.missing_fields[0]
            question = self._question_for(field_name, state)
            answer = clarify(field_name, question)
            self.interpreter.merge_clarification(state, field_name, answer)

        if state.task_type == TaskType.APPOINTMENT:
            self._run_appointment(state)
        elif state.task_type == TaskType.COWORKING_SEARCH:
            self._run_coworking_search(state)
        elif state.task_type == TaskType.TRIP_PLANNING:
            self._run_trip_planning(state)
        elif state.task_type == TaskType.MEETING:
            self._run_meeting(state)
        elif state.task_type == TaskType.REMINDER:
            self._run_reminder(state)
        else:
            state.blockers.append("Unknown task type. I need a clearer goal before using tools.")

        state.final_answer = self._format_final_answer(state)
        return state

    @staticmethod
    def _question_for(field_name: str, state: TaskState) -> str:
        questions = {
            "service_type": "What type of service do you want to book?",
            "city": "What city should I search in?",
            "date_range": "What date or date range should I use?",
            "time_preference": "What time preference should I use?",
            "budget": "What is your budget and currency?",
            "count": "How many options should I return?",
            "duration_days": "How many days should the plan cover?",
            "destination": "What destination should I plan for?",
            "attendee_name": "Who should the meeting be with?",
            "attendee_email": f"What is {state.slots.get('attendee_name', 'the attendee')}'s email address?",
            "reminder_text": "What should the reminder say?",
            "task_goal": "What exactly would you like the agent to do?",
        }
        return questions.get(field_name, f"Please provide: {field_name}")

    def _run_appointment(self, state: TaskState) -> None:
        calendar = self.tools.calendar_check(state.slots["date_range"], state.slots.get("time_preference"))
        state.add_tool_result(calendar)
        if calendar.status != ToolStatus.SUCCESS:
            return

        query = f"{state.slots['service_type']} appointment in {state.slots['city']}"
        search = self.tools.search_service(query, state.slots)
        state.add_tool_result(search)
        if search.status != ToolStatus.SUCCESS:
            return

        options = search.data["results"]
        available_starts = {slot["start"] for slot in calendar.data["available_slots"]}
        best = next((option for option in options if option.get("slot") in available_starts), options[0])
        booking = self.tools.booking_service(best)
        state.add_tool_result(booking)
        if booking.status != ToolStatus.SUCCESS:
            return

        reminder = self.tools.reminder_create({"title": f"Appointment: {best['name']}", "when": best.get("slot"), "location": state.slots.get("city")})
        state.add_tool_result(reminder)

    def _run_coworking_search(self, state: TaskState) -> None:
        search = self.tools.search_service(f"coworking spaces in {state.slots['city']}", state.slots)
        state.add_tool_result(search)

    def _run_trip_planning(self, state: TaskState) -> None:
        search = self.tools.search_service(f"trip itinerary for {state.slots['destination']}", state.slots)
        state.add_tool_result(search)
        if search.status != ToolStatus.SUCCESS:
            return

        total = sum(item.get("cost", 0) for item in search.data["results"])
        budget = state.slots.get("budget", {})
        amount = budget.get("amount") if isinstance(budget, dict) else None
        if amount and total > amount:
            state.blockers.append(f"Estimated cost is {total} {budget.get('currency', 'EUR')}, which exceeds the budget of {amount} {budget.get('currency', 'EUR')}.")
        else:
            state.assumptions.append(f"Estimated total cost: {total} {budget.get('currency', 'EUR') if isinstance(budget, dict) else 'EUR'}.")

    def _run_meeting(self, state: TaskState) -> None:
        calendar = self.tools.calendar_check(state.slots["date_range"], state.slots.get("time_preference"))
        state.add_tool_result(calendar)
        if calendar.status != ToolStatus.SUCCESS:
            return

        slot = calendar.data["available_slots"][0]
        booking = self.tools.booking_service({
            "id": "meeting-1",
            "type": "meeting",
            "attendee_name": state.slots["attendee_name"],
            "attendee_email": state.slots["attendee_email"],
            "slot": slot,
        })
        state.add_tool_result(booking)
        if booking.status == ToolStatus.SUCCESS:
            reminder = self.tools.reminder_create({"title": f"Meeting with {state.slots['attendee_name']}", "when": slot["start"]})
            state.add_tool_result(reminder)

    def _run_reminder(self, state: TaskState) -> None:
        reminder = self.tools.reminder_create({"title": state.slots["reminder_text"], "when": state.slots["date_range"]})
        state.add_tool_result(reminder)

    @staticmethod
    def _format_final_answer(state: TaskState) -> str:
        lines: list[str] = []
        lines.append("FINAL SUMMARY")
        lines.append(f"Intent: {state.task_type.value}")
        lines.append("")

        lines.append("Plan executed:")
        for index, step in enumerate(state.plan, 1):
            lines.append(f"{index}. {step}")
        lines.append("")

        if state.slots:
            lines.append("Collected information:")
            for key, value in state.slots.items():
                lines.append(f"- {key}: {value}")
            lines.append("")

        if state.tool_results:
            lines.append("Tool results:")
            for result in state.tool_results:
                lines.append(f"- {result.tool}: {result.status.value} — {result.message}")
                if result.data:
                    lines.append(f"  Data: {result.data}")
            lines.append("")

        if state.assumptions:
            lines.append("Assumptions:")
            for assumption in state.assumptions:
                lines.append(f"- {assumption}")
            lines.append("")

        if state.blockers:
            lines.append("Remaining blockers:")
            for blocker in state.blockers:
                lines.append(f"- {blocker}")
        else:
            lines.append("Remaining blockers: none")

        return "\n".join(lines)
