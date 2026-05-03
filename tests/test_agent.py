from task_agent.agent import TaskExecutionAgent


def test_coworking_search_without_clarification():
    agent = TaskExecutionAgent()
    state = agent.run("Find me 3 coworking spaces in Warsaw under $20/day", clarify=None)
    assert not state.blockers
    assert state.tool_results[0].tool == "search_service"
    assert len(state.tool_results[0].data["results"]) == 3


def test_missing_city_becomes_blocker_in_non_interactive_mode():
    agent = TaskExecutionAgent()
    state = agent.run("Book me a dentist appointment next week after 5pm", clarify=None)
    assert any("city" in blocker for blocker in state.blockers)


def test_appointment_with_clarification_books():
    agent = TaskExecutionAgent()
    answers = {"city": "Warsaw"}
    state = agent.run("Book me a dentist appointment next week after 5pm", clarify=lambda field, _: answers[field])
    assert not state.blockers
    assert any(result.tool == "booking_service" for result in state.tool_results)
