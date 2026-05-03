from __future__ import annotations

import argparse
import os
from pathlib import Path

from task_agent.agent import TaskExecutionAgent


def load_dotenv(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Task Execution AI Agent")
    parser.add_argument("request", nargs="*", help="User request, e.g. 'Find me 3 coworking spaces in Warsaw under $20/day'")
    parser.add_argument("--no-interactive", action="store_true", help="Do not ask clarifying questions; return blockers instead.")
    return parser


def main() -> None:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args()

    user_request = " ".join(args.request).strip()
    if not user_request:
        user_request = input("What would you like the agent to do?\n> ").strip()

    agent = TaskExecutionAgent()

    def clarify(_field_name: str, question: str) -> str:
        return input(f"{question}\n> ").strip()

    state = agent.run(user_request, clarify=None if args.no_interactive else clarify)
    print("\n" + state.final_answer)


if __name__ == "__main__":
    main()
