# ATA Builders Take-Home Assignment - Task Execution AI Agent

![Tests](https://github.com/yusufyzzc/ata-builders-agent/actions/workflows/tests.yml/badge.svg)
![Python](https://img.shields.io/badge/Python-3.11-blue)
![uv](https://img.shields.io/badge/package%20manager-uv-purple)

A small but production-minded task execution agent for the Junior AI Agentic Engineer internship assignment.

## Preview

https://github.com/user-attachments/assets/b89a54d0-c6ff-4f37-b7d4-3d857aeb7bab


The agent can:

- understand a user request,
- extract intent and missing information,
- ask clarifying questions,
- use the required tools,
- handle missing data, tool failures, and no-result cases,
- return a clear final summary with completed actions and blockers.

The project is intentionally runnable in two modes:

1. **Mock/offline mode** — works without API keys and demonstrates deterministic agent behavior.
2. **LLM-assisted mode** — if `OPENAI_API_KEY` is set, the agent uses the OpenAI Responses API for intent and slot extraction, then still performs explicit tool orchestration in Python.



## Why this design?

This assignment evaluates more than whether the code can call an LLM. I designed the project around a clear agent loop:

```text
User request
  -> intent and slot extraction
  -> missing information check
  -> clarification questions if needed
  -> plan creation
  -> tool execution
  -> failure/no-result handling
  -> final user-facing summary
```

The important product decision is that the LLM is **not trusted blindly**. It helps parse the request, but Python code owns:

- required fields,
- tool selection,
- execution order,
- error handling,
- final output structure.

This makes the agent easier to test and safer to extend.



## Required tools implemented

The assignment required these tools. They are implemented in `src/task_agent/tools.py` as deterministic mock tools:

| Tool | Purpose |
|---|---|
| `calendar_check(date_range)` | Finds available slots for appointments/meetings |
| `search_service(query)` | Searches mock datasets for dentists, coworking spaces, and trip planning |
| `booking_service(option)` | Books a selected mock option and returns a confirmation code |
| `reminder_create(details)` | Creates a mock reminder |

Mock tools were chosen because this keeps the repository easy to run for reviewers without needing paid external services, OAuth, calendar permissions, or booking accounts.



## Project structure

```text
agent-assignment/
├── pyproject.toml
├── uv.lock
├── .python-version
├── .env.example
├── README.md
├── main.py
├── src/
│   └── task_agent/
│       ├── __init__.py
│       ├── agent.py
│       ├── cli.py
│       ├── interpreter.py
│       ├── llm.py
│       ├── models.py
│       └── tools.py
└── tests/
    └── test_agent.py
```

---

## Setup

Install dependencies with `uv`:

```bash
uv sync
```

Run the agent:

```bash
uv run python main.py
```

Or pass a request directly:

```bash
uv run python main.py "Find me 3 coworking spaces in Warsaw under $20/day"
```

Run in non-interactive mode, where missing information becomes a blocker instead of a question:

```bash
uv run python main.py "Book me a dentist appointment next week after 5pm" --no-interactive
```


## Optional OpenAI setup

The app works without an API key. To enable LLM-assisted parsing:

```bash
cp .env.example .env
```

Then edit `.env`:

```env
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-4.1-mini
```

The agent uses the OpenAI Responses API only for intent/slot extraction. If the API key is missing or the API call fails, it falls back to deterministic heuristic parsing.


## Example 1: coworking search

Command:

```bash
uv run python main.py "Find me 3 coworking spaces in Warsaw under 20 USD /day"
```

Expected behavior:

- identifies intent as `coworking_search`,
- extracts city, budget, and result count,
- calls `search_service`,
- filters results under budget,
- returns a final summary with recommended options.



## Example 2: dentist booking with clarification

Command:

```bash
uv run python main.py "Book me a dentist appointment next week after 5pm"
```

Expected behavior:

- identifies intent as `appointment`,
- extracts service, date range, and time preference,
- notices that city is missing,
- asks: `What city should I search in?`,
- checks calendar availability,
- searches dentist options,
- books the best matching option in mock mode,
- creates a reminder,
- returns confirmation and remaining blockers.



## Example 3: meeting scheduling

Command:

```bash
uv run python main.py "Schedule a meeting with John next Tuesday afternoon"
```

Expected behavior:

- identifies intent as `meeting`,
- extracts attendee name, date range, and time preference,
- asks for John's email address,
- checks calendar availability,
- creates a mock meeting booking,
- creates a reminder,
- returns confirmation.



## Failure handling examples

### Missing information

```bash
uv run python main.py "Book me a dentist appointment next week after 5pm" --no-interactive
```

Returns a blocker explaining that `city` is required.

### No results

The search tool returns `no_results` when no mock dataset matches the query or constraints.

### Tool failure

The tools include deterministic failure branches, for example `api failure` in a search query triggers a mock search failure. This makes failure behavior easy to inspect and test.



## Tests

Run tests:

```bash
uv run pytest
```

The tests cover:

- successful coworking search,
- missing information in non-interactive mode,
- interactive clarification leading to a mock booking.

## Review feedback addressed

After the initial review, I improved the project in three areas:

1. **Parser robustness** — the heuristic parser no longer relies on a fixed city allow-list. It can extract user-provided cities such as Gliwice or Gdansk instead of silently dropping unknown locations.

2. **Context-aware clarifications** — clarification questions now include the task type and already collected information, so the agent asks only for missing data instead of repeating generic hard-coded questions.

3. **Broader test coverage** — the test suite now covers happy paths, missing information, generic city extraction, contextual clarification, no results, tool failure, meeting email handling, and trip budget overflow.

