"""Priority scoring for tasks."""

from datetime import datetime

from .models import Task, FreeSlot


def calculate_priority(task: Task, now: datetime, available_minutes: int = 0) -> float:
    """
    Calculate priority score for a task (higher = more urgent).

    Formula:
        priority = urgency * 0.4 + importance_norm * 0.3 + overload * 0.3

    Components:
        - urgency: How close the deadline is (0–10 scale).
        - importance_norm: Task importance normalized to 0–10.
        - overload: Ratio of remaining work vs. available time before deadline (0–10).

    Args:
        task: The task to score.
        now: Current datetime for urgency calculation.
        available_minutes: Total free minutes available before the task's deadline.
                          If 0, defaults to remaining_minutes (assumes barely enough time).

    Returns:
        Priority score (float, higher = do first).
    """
    # --- Urgency: how close is the deadline? ---
    hours_until_deadline = max(0, (task.deadline - now).total_seconds() / 3600)
    # Scale: 10 = due now, 0 = due in 10+ days
    urgency = max(0.0, 10.0 - hours_until_deadline / 24.0)

    # --- Importance: normalize 1–5 to 0–10 ---
    importance_norm = (task.importance / 5.0) * 10.0

    # --- Overload: how tight is the schedule? ---
    if available_minutes <= 0:
        # Assume just enough time — moderate pressure
        available_minutes = task.remaining_minutes

    if available_minutes > 0:
        overload = min(10.0, (task.remaining_minutes / available_minutes) * 10.0)
    else:
        overload = 10.0  # No time left, maximum pressure

    # --- Weighted score ---
    priority = urgency * 0.4 + importance_norm * 0.3 + overload * 0.3

    return round(priority, 2)


def rank_tasks(
    tasks: list[Task],
    now: datetime,
    free_slots: list[FreeSlot] | None = None,
) -> list[tuple[Task, float]]:
    """
    Rank tasks by priority score (highest first).

    Args:
        tasks: List of tasks to rank.
        now: Current datetime.
        free_slots: Available free slots (used to estimate available time per task).

    Returns:
        List of (task, score) tuples sorted by descending priority.
    """
    # Calculate total available minutes from free slots
    total_available = 0
    if free_slots:
        total_available = sum(slot.duration_minutes for slot in free_slots)

    scored: list[tuple[Task, float]] = []
    for task in tasks:
        # Estimate available time before this task's deadline
        if free_slots:
            available_before_deadline = sum(
                slot.duration_minutes
                for slot in free_slots
                if datetime.combine(slot.date, slot.end_time) <= task.deadline
            )
        else:
            available_before_deadline = 0

        score = calculate_priority(task, now, available_before_deadline)
        scored.append((task, score))

    # Sort by score descending
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored
