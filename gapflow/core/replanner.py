"""Replanner: applies structured change actions to the schedule state and regenerates."""

from datetime import datetime, date, time, timedelta
from difflib import SequenceMatcher

from .models import DayOfWeek, FixedEvent, Task, FreeSlot, ScheduledBlock
from .slots import detect_free_slots
from .scheduler import schedule_tasks


def _parse_time(t_str: str) -> time:
    """Parse HH:MM string into a time object."""
    parts = t_str.strip().split(":")
    return time(int(parts[0]), int(parts[1]))


def _fuzzy_match_task(task_name: str, tasks: list[Task]) -> Task | None:
    """Find the closest matching task by name (fuzzy)."""
    if not tasks:
        return None

    best_match = None
    best_score = 0.0

    task_name_lower = task_name.lower()

    for task in tasks:
        # Try exact substring match first
        if task_name_lower in task.name.lower() or task.name.lower() in task_name_lower:
            return task

        # Fuzzy match
        score = SequenceMatcher(None, task_name_lower, task.name.lower()).ratio()
        if score > best_score:
            best_score = score
            best_match = task

    # Only accept if reasonably similar
    if best_score >= 0.4:
        return best_match
    return None


def apply_replan_action(
    action: dict,
    events: list[FixedEvent],
    tasks: list[Task],
    target_day: DayOfWeek,
    target_date: date,
) -> dict:
    """
    Apply a single replan action to the current state.

    Args:
        action: Structured action dict from the replan tool.
        events: Current list of fixed events (will be modified in place).
        tasks: Current list of tasks (will be modified in place).
        target_day: Day of week for the schedule.
        target_date: Date for the schedule.

    Returns:
        Dict with 'success' bool and 'message' describing what was done.
    """
    action_type = action["action_type"]

    if action_type == "ADD_FIXED_EVENT":
        try:
            start = _parse_time(action["start_time"])
            end = _parse_time(action["end_time"])
            name = action["event_name"] or "New Event"

            new_event = FixedEvent(
                name=name,
                day=target_day,
                start_time=start,
                end_time=end,
            )
            events.append(new_event)
            return {"success": True, "message": f"Added fixed event: {name} ({action['start_time']}–{action['end_time']})"}
        except Exception as e:
            return {"success": False, "message": f"Failed to add event: {e}"}

    elif action_type == "BLOCK_TIME":
        try:
            start = _parse_time(action["start_time"])
            end = _parse_time(action["end_time"])
            name = action["event_name"] or "Blocked"

            # Treat blocked time as a fixed event (prevents scheduling there)
            block_event = FixedEvent(
                name=f"[Blocked] {name}",
                day=target_day,
                start_time=start,
                end_time=end,
            )
            events.append(block_event)
            return {"success": True, "message": f"Blocked time: {action['start_time']}–{action['end_time']} ({name})"}
        except Exception as e:
            return {"success": False, "message": f"Failed to block time: {e}"}

    elif action_type == "ADD_TASK":
        try:
            deadline_str = action["deadline"]
            deadline = datetime.fromisoformat(deadline_str) if deadline_str else datetime.now() + timedelta(hours=24)
            importance = action["importance"] or 3

            new_task = Task(
                name=action["task_name"] or "New Task",
                deadline=deadline,
                estimated_minutes=action["estimated_minutes"] or 60,
                importance=importance,
            )
            tasks.append(new_task)
            return {"success": True, "message": f"Added task: {new_task.name} ({new_task.estimated_minutes} min, importance {importance}/5)"}
        except Exception as e:
            return {"success": False, "message": f"Failed to add task: {e}"}

    elif action_type == "UPDATE_TASK":
        task_name = action["task_name"]
        matched = _fuzzy_match_task(task_name, tasks)
        if matched:
            extra = action["extra_minutes"]
            old_remaining = matched.remaining_minutes
            matched.remaining_minutes = max(0, matched.remaining_minutes + extra)
            matched.estimated_minutes = max(matched.estimated_minutes, matched.remaining_minutes)
            return {
                "success": True,
                "message": f"Updated '{matched.name}': remaining {old_remaining} → {matched.remaining_minutes} min"
            }
        else:
            return {"success": False, "message": f"Could not find task matching '{task_name}'"}

    elif action_type == "COMPLETE_TASK":
        task_name = action["task_name"]
        matched = _fuzzy_match_task(task_name, tasks)
        if matched:
            matched.remaining_minutes = 0
            return {"success": True, "message": f"Marked '{matched.name}' as complete"}
        else:
            return {"success": False, "message": f"Could not find task matching '{task_name}'"}

    else:
        return {"success": False, "message": f"Unknown action type: {action_type}"}


def replan_schedule(
    actions: list[dict],
    events: list[FixedEvent],
    tasks: list[Task],
    target_day: DayOfWeek,
    target_date: date,
    now: datetime,
) -> dict:
    """
    Apply all replan actions and regenerate the schedule.

    Args:
        actions: List of structured action dicts from the replan tool.
        events: Current fixed events (modified in place).
        tasks: Current tasks (modified in place).
        target_day: Day of week.
        target_date: Target date.
        now: Current datetime (past slots are filtered).

    Returns:
        Dict with:
            - 'action_results': list of apply results
            - 'new_free_slots': updated free slots
            - 'new_schedule': new scheduled blocks
            - 'active_tasks': tasks with remaining time > 0
    """
    # Apply each action
    action_results = []
    for action in actions:
        result = apply_replan_action(action, events, tasks, target_day, target_date)
        action_results.append(result)

    # Filter to only tasks with remaining work
    active_tasks = [t for t in tasks if t.remaining_minutes > 0]

    # Detect free slots (past time automatically filtered)
    free_slots = detect_free_slots(events, target_day, target_date, now=now)

    # Regenerate schedule
    new_blocks = schedule_tasks(active_tasks, free_slots, now)

    return {
        "action_results": action_results,
        "new_free_slots": free_slots,
        "new_schedule": new_blocks,
        "active_tasks": active_tasks,
    }
