"""Weekly Planner: generates a 7-day rolling study plan across multiple days."""

from dataclasses import dataclass, field
from datetime import datetime, date, time, timedelta
from math import ceil

from .models import (
    DayOfWeek,
    FixedEvent,
    FreeSlot,
    Task,
    ScheduledBlock,
    RecurringEvent,
    expand_recurring_events,
    DAY_ENUM_TO_WEEKDAY,
)
from .slots import detect_free_slots, DEFAULT_DAY_START, DEFAULT_DAY_END
from .priority import rank_tasks
from .scheduler import (
    _add_minutes_to_time,
    _slot_available_before_deadline,
    calculate_available_before_deadline,
    DeadlineWarning,
)


# ─────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────

DAY_MAP = {
    0: DayOfWeek.MON,
    1: DayOfWeek.TUE,
    2: DayOfWeek.WED,
    3: DayOfWeek.THU,
    4: DayOfWeek.FRI,
    5: DayOfWeek.SAT,
    6: DayOfWeek.SUN,
}


@dataclass
class DayPlan:
    """Plan for a single day within the weekly schedule."""
    date: date
    day: DayOfWeek
    fixed_events: list[FixedEvent] = field(default_factory=list)
    scheduled_blocks: list[ScheduledBlock] = field(default_factory=list)
    free_slots: list[FreeSlot] = field(default_factory=list)

    @property
    def total_free_minutes(self) -> int:
        return sum(s.duration_minutes for s in self.free_slots)

    @property
    def total_study_minutes(self) -> int:
        return sum(b.allocated_minutes for b in self.scheduled_blocks)


@dataclass
class WeeklyPlan:
    """Complete 7-day rolling plan."""
    start_date: date
    end_date: date
    days: list[DayPlan] = field(default_factory=list)
    warnings: list[DeadlineWarning] = field(default_factory=list)

    @property
    def total_free_minutes(self) -> int:
        return sum(d.total_free_minutes for d in self.days)

    @property
    def total_study_minutes(self) -> int:
        return sum(d.total_study_minutes for d in self.days)

    @property
    def all_blocks(self) -> list[ScheduledBlock]:
        blocks = []
        for d in self.days:
            blocks.extend(d.scheduled_blocks)
        return blocks

    @property
    def all_free_slots(self) -> list[FreeSlot]:
        slots = []
        for d in self.days:
            slots.extend(d.free_slots)
        return slots


# ─────────────────────────────────────────────────────────────
# Multi-day free slot generation
# ─────────────────────────────────────────────────────────────

def generate_weekly_free_slots(
    one_off_events: list[dict],
    recurring_events: list[RecurringEvent],
    start_date: date,
    num_days: int = 7,
    now: datetime | None = None,
    day_start: time = DEFAULT_DAY_START,
    day_end: time = DEFAULT_DAY_END,
) -> list[DayPlan]:
    """
    Generate free slots for each day in a multi-day range.

    Args:
        one_off_events: List of {"event": FixedEvent, "date": date} dicts.
        recurring_events: List of RecurringEvent objects.
        start_date: First day of the range.
        num_days: Number of days to plan (default 7).
        now: Current datetime (for today's past filtering).
        day_start: Daily start time.
        day_end: Daily end time.

    Returns:
        List of DayPlan objects, one per day.
    """
    if now is None:
        now = datetime.now()

    end_date = start_date + timedelta(days=num_days - 1)

    # Expand recurring events for the full range
    expanded_recurring = expand_recurring_events(recurring_events, start_date, end_date)

    day_plans: list[DayPlan] = []

    for offset in range(num_days):
        current_date = start_date + timedelta(days=offset)
        current_day = DAY_MAP[current_date.weekday()]

        # Gather events for this day
        day_events: list[FixedEvent] = []

        # One-off events
        for entry in one_off_events:
            if entry["date"] == current_date:
                day_events.append(entry["event"])

        # Recurring events for this date
        for evt, evt_date in expanded_recurring:
            if evt_date == current_date:
                day_events.append(evt)

        # Detect free slots (filter past for today only)
        use_now = now if current_date == now.date() else None
        free_slots = detect_free_slots(
            day_events, current_day, current_date,
            day_start=day_start, day_end=day_end,
            now=use_now,
        )

        day_plans.append(DayPlan(
            date=current_date,
            day=current_day,
            fixed_events=day_events,
            free_slots=free_slots,
        ))

    return day_plans


# ─────────────────────────────────────────────────────────────
# Spread-aware multi-day scheduler
# ─────────────────────────────────────────────────────────────

def _calculate_daily_target(
    task: Task,
    days_until_deadline: int,
    slack_minutes: int,
) -> int:
    """
    Calculate ideal daily study allocation for a task to spread it evenly.

    If slack is high, spread across many days.
    If slack is low/negative, front-load aggressively.

    Returns target minutes per day.
    """
    if days_until_deadline <= 0:
        # Deadline is today or past — schedule everything now
        return task.remaining_minutes

    if slack_minutes < 0:
        # Negative slack: schedule as much as possible each day
        return task.remaining_minutes

    if slack_minutes < task.remaining_minutes * 0.25:
        # Low slack: front-load (use fewer days)
        spread_days = max(1, days_until_deadline // 2)
    else:
        # Good slack: spread evenly
        spread_days = days_until_deadline

    return max(30, ceil(task.remaining_minutes / spread_days))


def schedule_weekly(
    tasks: list[Task],
    day_plans: list[DayPlan],
    now: datetime,
) -> tuple[list[DayPlan], list[DeadlineWarning]]:
    """
    Multi-day deadline-aware scheduler with workload spreading.

    Algorithm:
        1. Sort tasks by (deadline, slack, -priority) — earliest deadline first.
        2. For each task, calculate a daily target to spread workload.
        3. Allocate slots day-by-day, respecting the daily target unless slack is low.
        4. Never schedule past a task's deadline (hard constraint).
        5. Track remaining slot capacity across all days.

    Args:
        tasks: All pending tasks.
        day_plans: List of DayPlan with free_slots populated.
        now: Current datetime.

    Returns:
        Tuple of (updated day_plans with scheduled_blocks, deadline warnings).
    """
    # Filter active tasks
    active_tasks = [t for t in tasks if t.remaining_minutes > 0]

    if not active_tasks:
        return day_plans, []

    # Collect all free slots across all days (ordered by date/time)
    all_slots: list[FreeSlot] = []
    slot_day_index: list[int] = []  # Maps slot index to day_plans index
    for day_idx, day_plan in enumerate(day_plans):
        for slot in day_plan.free_slots:
            all_slots.append(slot)
            slot_day_index.append(day_idx)

    if not all_slots:
        # No free time at all
        warnings = []
        for task in active_tasks:
            warnings.append(DeadlineWarning(
                task=task,
                available_minutes=0,
                needed_minutes=task.remaining_minutes,
                shortfall_minutes=task.remaining_minutes,
                status="CRITICAL",
            ))
        return day_plans, warnings

    # Track remaining capacity
    slot_remaining = [slot.duration_minutes for slot in all_slots]

    # Get priority scores for tie-breaking
    priority_scores = {}
    ranked = rank_tasks(active_tasks, now, all_slots)
    for task, score in ranked:
        priority_scores[task.id] = score

    # Calculate deadline warnings
    warnings: list[DeadlineWarning] = []
    for task in active_tasks:
        available = calculate_available_before_deadline(task, all_slots, slot_remaining)
        shortfall = max(0, task.remaining_minutes - available)
        slack = available - task.remaining_minutes

        if slack < 0:
            status = "CRITICAL"
        elif slack < task.remaining_minutes * 0.25:
            status = "AT_RISK"
        else:
            status = "ON_TRACK"

        if status != "ON_TRACK":
            warnings.append(DeadlineWarning(
                task=task,
                available_minutes=available,
                needed_minutes=task.remaining_minutes,
                shortfall_minutes=shortfall,
                status=status,
            ))

    # Sort tasks: (deadline, slack, -priority)
    task_order: list[tuple[datetime, int, float, Task]] = []
    for task in active_tasks:
        available = calculate_available_before_deadline(task, all_slots, slot_remaining)
        slack = available - task.remaining_minutes
        priority = priority_scores.get(task.id, 0.0)
        task_order.append((task.deadline, slack, -priority, task))

    task_order.sort(key=lambda x: (x[0], x[1], x[2]))

    # Schedule each task with spreading
    for _deadline, _slack, _neg_pri, task in task_order:
        remaining = task.remaining_minutes
        if remaining <= 0:
            continue

        # Calculate spread target
        today_date = now.date()
        days_until_deadline = max(0, (task.deadline.date() - today_date).days)
        available = calculate_available_before_deadline(task, all_slots, slot_remaining)
        slack = available - remaining
        daily_target = _calculate_daily_target(task, days_until_deadline, slack)

        # Track how much we've allocated per day
        allocated_per_day: dict[date, int] = {}

        for i, slot in enumerate(all_slots):
            if remaining <= 0:
                break

            avail = slot_remaining[i]
            if avail < 15:
                continue

            # Hard deadline constraint
            usable = _slot_available_before_deadline(slot, avail, task.deadline)
            if usable < 15:
                continue

            # Spread logic: respect daily target (unless slack is very low)
            slot_date = slot.date
            already_today = allocated_per_day.get(slot_date, 0)

            if slack > task.remaining_minutes * 0.25 and days_until_deadline > 1:
                # Good slack — respect daily target
                day_budget = max(0, daily_target - already_today)
                if day_budget < 15:
                    continue
                allocate = min(remaining, usable, day_budget)
            else:
                # Tight slack — allocate as much as possible
                allocate = min(remaining, usable)

            if allocate < 15:
                continue

            # Create block
            used_so_far = slot.duration_minutes - slot_remaining[i]
            block_start = _add_minutes_to_time(slot.start_time, used_so_far)
            block_end = _add_minutes_to_time(block_start, allocate)

            block = ScheduledBlock(
                task_id=task.id,
                task_name=task.name,
                day=slot.day,
                date=slot_date,
                start_time=block_start,
                end_time=block_end,
                allocated_minutes=allocate,
            )

            # Assign to the correct day plan
            day_idx = slot_day_index[i]
            day_plans[day_idx].scheduled_blocks.append(block)

            slot_remaining[i] -= allocate
            remaining -= allocate
            allocated_per_day[slot_date] = already_today + allocate

    # Sort blocks within each day
    for day_plan in day_plans:
        day_plan.scheduled_blocks.sort(key=lambda b: b.start_time)

    return day_plans, warnings


# ─────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────

def generate_weekly_plan(
    one_off_events: list[dict],
    recurring_events: list[RecurringEvent],
    tasks: list[Task],
    now: datetime | None = None,
    num_days: int = 7,
) -> WeeklyPlan:
    """
    Generate a complete 7-day rolling plan.

    Args:
        one_off_events: List of {"event": FixedEvent, "date": date} dicts.
        recurring_events: List of RecurringEvent objects.
        tasks: All pending tasks.
        now: Current datetime (defaults to now).
        num_days: Planning horizon in days (default 7).

    Returns:
        WeeklyPlan with all days populated.
    """
    if now is None:
        now = datetime.now()

    start_date = now.date()
    end_date = start_date + timedelta(days=num_days - 1)

    # Generate free slots for each day
    day_plans = generate_weekly_free_slots(
        one_off_events, recurring_events, start_date, num_days, now
    )

    # Schedule tasks across all days
    day_plans, warnings = schedule_weekly(tasks, day_plans, now)

    return WeeklyPlan(
        start_date=start_date,
        end_date=end_date,
        days=day_plans,
        warnings=warnings,
    )
