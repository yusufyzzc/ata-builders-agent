from task_agent.agent import TaskExecutionAgent
from task_agent.interpreter import TaskInterpreter
from task_agent.models import TaskType


def test_coworking_search_without_clarification():
    agent = TaskExecutionAgent()
    state = agent.run("Find me 3 coworking spaces in Warsaw under $20/day", clarify=None)
    assert not state.blockers
    assert state.slots["city"] == "Warsaw"
    assert state.slots["budget"] == {"amount": 20, "currency": "USD"}
    assert state.tool_results[0].tool == "search_service"
    assert len(state.tool_results[0].data["results"]) == 3


def test_unknown_city_is_not_silently_dropped():
    interpreter = TaskInterpreter()
    state = interpreter.interpret("Find me 2 coworking spaces in Gliwice under 25 PLN/day")
    assert state.task_type == TaskType.COWORKING_SEARCH
    assert state.slots["city"] == "Gliwice"
    assert state.slots["budget"] == {"amount": 25, "currency": "PLN"}
    assert state.slots["count"] == 2
    assert "city" not in state.missing_fields


def test_missing_city_becomes_blocker_in_non_interactive_mode():
    agent = TaskExecutionAgent()
    state = agent.run("Book me a dentist appointment next week after 5pm", clarify=None)
    assert any("city" in blocker for blocker in state.blockers)


def test_appointment_with_clarification_books():
    agent = TaskExecutionAgent()
    answers = {"city": "Warsaw"}
    state = agent.run("Book me a dentist appointment next week after 5pm", clarify=lambda field, _: answers[field])
    assert not state.blockers
    assert any(result.tool == "calendar_check" for result in state.tool_results)
    assert any(result.tool == "booking_service" for result in state.tool_results)
    assert any(result.tool == "reminder_create" for result in state.tool_results)


def test_contextual_clarification_question_uses_known_data():
    agent = TaskExecutionAgent()
    questions: list[str] = []

    def clarify(field: str, question: str) -> str:
        questions.append(question)
        return {"city": "Warsaw"}[field]

    agent.run("Book me a dentist appointment next week after 5pm", clarify=clarify)
    assert "Known details" in questions[0]
    assert "service_type=dentist" in questions[0]
    assert "date_range" in questions[0]


def test_meeting_extracts_email_and_does_not_ask_for_it():
    agent = TaskExecutionAgent()
    state = agent.run("Schedule a meeting with John john@example.com next Tuesday afternoon", clarify=None)
    assert not state.blockers
    assert state.slots["attendee_email"] == "john@example.com"
    assert any(result.tool == "booking_service" for result in state.tool_results)


def test_meeting_asks_for_email_when_missing():
    agent = TaskExecutionAgent()
    seen_fields: list[str] = []

    def clarify(field: str, _question: str) -> str:
        seen_fields.append(field)
        return {"attendee_email": "john@example.com"}[field]

    state = agent.run("Schedule a meeting with John next Tuesday afternoon", clarify=clarify)
    assert seen_fields == ["attendee_email"]
    assert not state.blockers


def test_trip_budget_blocker_when_plan_exceeds_budget():
    agent = TaskExecutionAgent()
    state = agent.run("Plan a 2-day trip to Prague under €100", clarify=None)
    assert any("exceeds the budget" in blocker for blocker in state.blockers)


def test_no_results_are_reported_as_blocker():
    agent = TaskExecutionAgent()
    state = agent.run("Find me 3 coworking spaces in Warsaw under $5/day", clarify=None)
    assert any("no results" in blocker.lower() for blocker in state.blockers)


def test_tool_failure_is_reported_as_blocker():
    agent = TaskExecutionAgent()
    state = agent.run("Find me 3 coworking spaces in api failure under $20/day", clarify=lambda _field, _question: "Warsaw")
    assert any("search_service failed" in blocker for blocker in state.blockers)
