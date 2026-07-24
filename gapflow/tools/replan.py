"""Strands tool for parsing natural-language schedule changes into structured replan actions."""

import json
from strands import tool


# Module-level store for replan actions (same pattern as parse_task.py)
replan_actions: list[dict] = []


def clear_replan_actions():
    """Clear the replan actions store."""
    replan_actions.clear()


def get_replan_actions() -> list[dict]:
    """Return all replan actions parsed so far."""
    return list(replan_actions)


@tool
def apply_schedule_change(
    action_type: str,
    event_name: str = "",
    start_time: str = "",
    end_time: str = "",
    task_name: str = "",
    deadline: str = "",
    estimated_minutes: int = 0,
    importance: int = 0,
    extra_minutes: int = 0,
    explanation: str = "",
) -> str:
    """Apply a schedule change based on the user's natural-language request.

    You MUST call this tool with the appropriate action_type after understanding the user's change.

    Action types:
    - ADD_FIXED_EVENT: A new fixed event/meeting that blocks time.
      Required: event_name, start_time (HH:MM), end_time (HH:MM)
    - ADD_TASK: A brand new task to add to the schedule.
      Required: task_name, deadline (ISO datetime), estimated_minutes, importance (1-5)
    - UPDATE_TASK: Modify an existing task's remaining duration.
      Required: task_name, extra_minutes (positive = needs more time, negative = needs less time)
    - COMPLETE_TASK: Mark a task as done (remove from scheduling).
      Required: task_name
    - BLOCK_TIME: Block a time range so nothing can be scheduled there.
      Required: start_time (HH:MM), end_time (HH:MM), event_name (reason)

    Always provide an explanation of what you understood and why the schedule needs to change.

    Args:
        action_type: One of ADD_FIXED_EVENT, ADD_TASK, UPDATE_TASK, COMPLETE_TASK, BLOCK_TIME.
        event_name: Name of the event or block reason.
        start_time: Start time in HH:MM format (for events/blocks).
        end_time: End time in HH:MM format (for events/blocks).
        task_name: Name of the task (for task-related actions).
        deadline: ISO datetime deadline (for ADD_TASK).
        estimated_minutes: Duration in minutes (for ADD_TASK).
        importance: Importance 1-5 (for ADD_TASK).
        extra_minutes: Additional minutes needed (for UPDATE_TASK, can be negative).
        explanation: Brief explanation of the change for the user.
    """
    valid_actions = ["ADD_FIXED_EVENT", "ADD_TASK", "UPDATE_TASK", "COMPLETE_TASK", "BLOCK_TIME"]

    if action_type not in valid_actions:
        return json.dumps({"status": "error", "message": f"Invalid action_type. Must be one of: {valid_actions}"})

    action = {
        "action_type": action_type,
        "event_name": event_name,
        "start_time": start_time,
        "end_time": end_time,
        "task_name": task_name,
        "deadline": deadline,
        "estimated_minutes": estimated_minutes,
        "importance": max(1, min(5, importance)) if importance else 0,
        "extra_minutes": extra_minutes,
        "explanation": explanation,
    }

    replan_actions.append(action)

    result = {
        "status": "success",
        "action": action,
    }

    return json.dumps(result, indent=2)
