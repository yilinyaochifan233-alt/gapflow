"""Strands tool for parsing natural-language task descriptions into structured Task data."""

import json
from datetime import datetime, timedelta
from strands import tool

from gapflow.core.models import Task


# Module-level store: collects Task objects created by the tool.
# This allows the integration layer to retrieve real Task objects after agent calls.
parsed_tasks: list[Task] = []


def clear_parsed_tasks():
    """Clear the parsed tasks store (call before a new session)."""
    parsed_tasks.clear()


def get_parsed_tasks() -> list[Task]:
    """Return all Task objects parsed so far."""
    return list(parsed_tasks)


@tool
def parse_task(
    task_name: str,
    deadline_description: str,
    estimated_minutes: int,
    importance: int,
) -> str:
    """Save a parsed task with structured fields extracted from the user's natural-language input.

    The agent should call this tool AFTER extracting the task details from the user's message.

    Args:
        task_name: A short, clear name for the task (e.g., "Database coursework").
        deadline_description: The deadline as an ISO datetime string (YYYY-MM-DDTHH:MM:SS).
        estimated_minutes: How long the task will take in minutes.
        importance: Importance level from 1 (low) to 5 (critical).
    """
    # Validate importance range
    importance = max(1, min(5, importance))

    # Parse deadline
    try:
        deadline = datetime.fromisoformat(deadline_description)
    except ValueError:
        # Fallback: if parsing fails, set deadline to 24h from now
        deadline = datetime.now() + timedelta(hours=24)

    # Create the Task object
    task = Task(
        name=task_name,
        deadline=deadline,
        estimated_minutes=estimated_minutes,
        importance=importance,
    )

    # Store the real Task object for retrieval by the integration layer
    parsed_tasks.append(task)

    # Return structured JSON so the agent can confirm to the user
    result = {
        "status": "success",
        "task": {
            "id": task.id,
            "name": task.name,
            "deadline": task.deadline.isoformat(),
            "estimated_minutes": task.estimated_minutes,
            "importance": task.importance,
        },
    }

    return json.dumps(result, indent=2)
