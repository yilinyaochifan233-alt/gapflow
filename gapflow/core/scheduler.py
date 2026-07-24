"""Scheduler: assigns prioritized tasks to free time slots with deadline awareness."""

from dataclasses import dataclass
from datetime import datetime, date, time, timedelta

from .models import (
    DayOfWeek,
    FixedEvent,
    FreeSlot,
    Task,
    ScheduledBlock,
    DailySchedule,
)
from .slots import detect_free_slots
from .priority import rank_tasks


# Duration categories — helps match task type to slot size
DURATION_CATEGORIES = {
    "short": (15, 30),     # flashcards, reading, small tasks
    "medium": (30, 60),    # revision, research, practice questions
    "long": (60, 120),     # coursework, coding, deep study
    "extended": (120, 480),  # large projects, exams prep
}

# Default planning window for future days (when no timetable data is available)
DEFAULT_DAILY_PLANNING_MINUTES = 14 * 60  # 08:00–22:00 = 840 minutes


@dataclass
class DeadlineWarning:
    """Warning for tasks at risk of missing their deadline."""
    task: Task
    available_minutes: int
    needed_minutes: int
    shortfall_minutes: int
    status: str  # "CRITICAL", "AT_RISK", "ON_TRACK", "FUTURE_NEEDS_PLANNING"


def _add_minutes_to_time(t: time, minutes: int) -> time:
    """Add minutes to a time object, returning a new time."""
    dt = datetime.combine(date.today(), t) + timedelta(minutes=minutes)
    return dt.time()


def _slot_available_before_deadline(slot: FreeSlot, slot_remaining: int, deadline: datetime) -> int:
    """
    Calculate how many minutes of a slot are available before a deadline.

    If the slot ends before the deadline, all remaining time is usable.
    If the slot spans the deadline, only the portion before the deadline counts.
    If the slot starts after the deadline, 0 minutes are usable.
    """
    slot_start_dt = datetime.combine(slot.date, slot.start_time)
    slot_end_dt = datetime.combine(slot.date, slot.end_time)

    if slot_start_dt >= deadline:
        return 0

    if slot_end_dt <= deadline:
        return slot_remaining

    # Slot spans the deadline — only count minutes before it
    minutes_before_deadline = int((deadline - slot_start_dt).total_seconds() / 60)
    # But we can't use more than the remaining capacity
    used_so_far = slot.duration_minutes - slot_remaining
    usable = max(0, minutes_before_deadline - used_so_far)
    return min(usable, slot_remaining)


def calculate_available_before_deadline(
    task: Task,
    free_slots: list[FreeSlot],
    slot_remaining: list[int] | None = None,
) -> int:
    """
    Calculate total available free minutes before a task's deadline
    using only the provided free slots (today's slots for scheduling).

    Args:
        task: The task to check.
        free_slots: Available free slots (typically today only).
        slot_remaining: Current remaining capacity per slot (if None, uses full capacity).

    Returns:
        Total available minutes in the given slots before the task's deadline.
    """
    if slot_remaining is None:
        slot_remaining = [slot.duration_minutes for slot in free_slots]

    total = 0
    for i, slot in enumerate(free_slots):
        total += _slot_available_before_deadline(slot, slot_remaining[i], task.deadline)
    return total


def estimate_total_available_before_deadline(
    task: Task,
    today_free_slots: list[FreeSlot],
    now: datetime,
    daily_planning_minutes: int = DEFAULT_DAILY_PLANNING_MINUTES,
) -> tuple[int, bool]:
    """
    Estimate TOTAL available minutes between now and the task's deadline,
    including future days (using a configurable daily planning window).

    This is used for deadline STATUS calculation (not for today's scheduling).

    Args:
        task: The task to evaluate.
        today_free_slots: Known free slots for today.
        now: Current datetime.
        daily_planning_minutes: Assumed available minutes per future day (default: 840 = 14h).

    Returns:
        Tuple of (estimated_total_minutes, is_estimate).
        is_estimate is True if future days had to be estimated (no timetable data).
    """
    # Today's available time (precise, from actual slots)
    today_available = calculate_available_before_deadline(task, today_free_slots)

    # How many full future days between tomorrow and the deadline?
    today_date = now.date()
    deadline_date = task.deadline.date()

    if deadline_date <= today_date:
        # Deadline is today or past — only today's slots matter
        return today_available, False

    # Count full planning days between tomorrow and the deadline date (exclusive)
    full_future_days = (deadline_date - today_date).days - 1  # days between tomorrow and deadline day
    full_future_days = max(0, full_future_days)

    # Deadline day: estimate partial day (from 08:00 to deadline time)
    deadline_time = task.deadline.time()
    day_start = time(8, 0)
    if deadline_time > day_start:
        deadline_day_minutes = int(
            (datetime.combine(deadline_date, deadline_time) -
             datetime.combine(deadline_date, day_start)).total_seconds() / 60
        )
    else:
        deadline_day_minutes = 0

    # Total estimate
    future_minutes = (full_future_days * daily_planning_minutes) + deadline_day_minutes
    total = today_available + future_minutes

    is_estimate = (full_future_days > 0) or (deadline_date > today_date)
    return total, is_estimate


def calculate_slack(task: Task, available_before_deadline: int) -> int:
    """
    Calculate slack = available time - remaining work.

    Negative slack means the task cannot be completed on time.
    """
    return available_before_deadline - task.remaining_minutes


def get_deadline_status(
    task: Task,
    free_slots: list[FreeSlot],
    now: datetime | None = None,
) -> DeadlineWarning:
    """
    Determine deadline status for a task using TOTAL available time (multi-day estimate).

    A task due tomorrow should NOT be marked CRITICAL just because today's slots
    cannot contain all its remaining work.

    Args:
        task: The task to evaluate.
        free_slots: Available free slots for today.
        now: Current datetime (defaults to datetime.now()).

    Returns:
        DeadlineWarning with status CRITICAL / AT_RISK / ON_TRACK / FUTURE_NEEDS_PLANNING.
    """
    if now is None:
        now = datetime.now()

    total_available, is_estimate = estimate_total_available_before_deadline(
        task, free_slots, now
    )
    needed = task.remaining_minutes
    shortfall = max(0, needed - total_available)
    slack = total_available - needed

    if slack < 0:
        if is_estimate:
            # Future estimate suggests not enough time, but we don't have precise data
            status = "CRITICAL"
        else:
            status = "CRITICAL"
    elif is_estimate and slack < needed * 0.5:
        # We're estimating future availability — be cautious but not alarming
        status = "FUTURE_NEEDS_PLANNING"
    elif slack < needed * 0.25:
        status = "AT_RISK"
    else:
        status = "ON_TRACK"

    return DeadlineWarning(
        task=task,
        available_minutes=total_available,
        needed_minutes=needed,
        shortfall_minutes=shortfall,
        status=status,
    )


def schedule_tasks(
    tasks: list[Task],
    free_slots: list[FreeSlot],
    now: datetime,
) -> list[ScheduledBlock]:
    """
    Deadline-aware greedy scheduler using Earliest Deadline First (EDF).

    Algorithm:
        1. Sort tasks by: (deadline, slack, -priority_score).
           Earliest deadline first. Ties broken by lower slack, then higher priority.
        2. For each task, only assign to slot time that falls BEFORE the task's deadline.
        3. Split tasks across multiple slots if needed.
        4. Never schedule a task after its deadline (hard constraint).

    This ensures a task due today always gets its required time before a
    later-deadline task can consume those same slots.

    Args:
        tasks: All pending tasks.
        free_slots: Available free slots (already detected, past filtered).
        now: Current datetime for priority calculation.

    Returns:
        List of ScheduledBlock assignments.
    """
    # Filter to tasks with remaining work
    active_tasks = [t for t in tasks if t.remaining_minutes > 0]

    if not active_tasks or not free_slots:
        return []

    # Get priority scores for tie-breaking (does NOT determine scheduling order)
    priority_scores = {}
    ranked = rank_tasks(active_tasks, now, free_slots)
    for task, score in ranked:
        priority_scores[task.id] = score

    # Track remaining time in each slot
    slot_remaining = [slot.duration_minutes for slot in free_slots]

    # Sort by: (deadline, slack, -priority)
    # Earliest deadline first → tightest slack → highest priority
    task_order: list[tuple[datetime, int, float, Task]] = []
    for task in active_tasks:
        available = calculate_available_before_deadline(task, free_slots, slot_remaining)
        slack = calculate_slack(task, available)
        priority = priority_scores.get(task.id, 0.0)
        task_order.append((task.deadline, slack, -priority, task))

    task_order.sort(key=lambda x: (x[0], x[1], x[2]))

    scheduled_blocks: list[ScheduledBlock] = []

    for _deadline, _slack, _neg_priority, task in task_order:
        remaining = task.remaining_minutes

        if remaining <= 0:
            continue

        for i, slot in enumerate(free_slots):
            if remaining <= 0:
                break

            available = slot_remaining[i]
            if available < 15:
                continue

            # HARD CONSTRAINT: only use slot time that falls before the task's deadline
            usable = _slot_available_before_deadline(slot, available, task.deadline)
            if usable < 15:
                continue

            # Allocate as much as possible (within deadline constraint)
            allocate = min(remaining, usable)

            # Calculate start time within the slot
            used_so_far = slot.duration_minutes - slot_remaining[i]
            block_start = _add_minutes_to_time(slot.start_time, used_so_far)
            block_end = _add_minutes_to_time(block_start, allocate)

            block = ScheduledBlock(
                task_id=task.id,
                task_name=task.name,
                day=slot.day,
                date=slot.date,
                start_time=block_start,
                end_time=block_end,
                allocated_minutes=allocate,
            )
            scheduled_blocks.append(block)

            slot_remaining[i] -= allocate
            remaining -= allocate

    # Sort blocks by date and start time for clean output
    scheduled_blocks.sort(key=lambda b: (b.date, b.start_time))

    return scheduled_blocks


def schedule_tasks_with_warnings(
    tasks: list[Task],
    free_slots: list[FreeSlot],
    now: datetime,
) -> tuple[list[ScheduledBlock], list[DeadlineWarning]]:
    """
    Schedule tasks and also return deadline warnings.

    Uses multi-day estimation for deadline status (not just today's slots).

    Args:
        tasks: All pending tasks.
        free_slots: Available free slots (today).
        now: Current datetime.

    Returns:
        Tuple of (scheduled blocks, list of deadline warnings for at-risk tasks).
    """
    # Calculate warnings using multi-day estimation
    warnings = []
    for task in tasks:
        if task.remaining_minutes <= 0:
            continue
        warning = get_deadline_status(task, free_slots, now)
        if warning.status not in ("ON_TRACK",):
            warnings.append(warning)

    # Schedule (today's slots only)
    blocks = schedule_tasks(tasks, free_slots, now)

    return blocks, warnings


def generate_daily_schedule(
    events: list[FixedEvent],
    tasks: list[Task],
    target_day: DayOfWeek,
    target_date: date,
    now: datetime,
) -> DailySchedule:
    """
    Generate a complete daily schedule for one day.

    Args:
        events: All fixed events in timetable.
        tasks: All pending tasks.
        target_day: Day of the week.
        target_date: The actual date.
        now: Current datetime.

    Returns:
        DailySchedule with fixed events and scheduled task blocks.
    """
    # Get free slots for this day
    free_slots = detect_free_slots(events, target_day, target_date, now=now)

    # Schedule tasks into the free slots
    blocks = schedule_tasks(tasks, free_slots, now)

    # Filter blocks for this specific day
    day_blocks = [b for b in blocks if b.date == target_date]

    # Get fixed events for this day
    day_events = [e for e in events if e.day == target_day]

    return DailySchedule(
        date=target_date,
        fixed_events=day_events,
        scheduled_blocks=day_blocks,
    )
