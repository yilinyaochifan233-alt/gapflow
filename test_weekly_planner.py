"""
GapFlow Weekly Planner Test
============================
Tests the 7-day rolling planner with multi-day scheduling.

Scenario:
- Recurring university timetable Mon-Fri
- 4 tasks with different deadlines
- One 5-hour task requiring multiple sessions
- One urgent task due tomorrow
- One low-priority task due next week

Assertions:
1. No scheduled block occurs after its task's deadline.
2. No scheduled block overlaps a fixed event.
3. Today's blocks are never in the past.
4. Long tasks can be split across several days.
5. Earlier deadlines are protected (urgent task fully scheduled).
6. Recurring timetable events are expanded correctly.
7. Total allocated minutes never exceed task remaining workload.

Usage:
    py test_weekly_planner.py
"""

from datetime import datetime, date, time, timedelta

from gapflow.core.models import (
    DayOfWeek,
    FixedEvent,
    Task,
    RecurringEvent,
)
from gapflow.core.weekly_planner import generate_weekly_plan, WeeklyPlan


def build_test_scenario():
    """Build a realistic test scenario."""
    # "Today" is Monday July 27, 2026 at 10:00
    now = datetime(2026, 7, 27, 10, 0)
    today = now.date()

    # Recurring university timetable (Mon-Fri, semester Sep-Dec but we expand for this week)
    # We'll set semester to cover this week for testing
    semester_start = date(2026, 7, 20)
    semester_end = date(2026, 8, 10)

    recurring_events = [
        RecurringEvent(
            name="Algorithms Lecture",
            day_of_week=DayOfWeek.MON,
            start_time=time(9, 0),
            end_time=time(10, 0),
            start_date=semester_start,
            end_date=semester_end,
        ),
        RecurringEvent(
            name="Database Systems",
            day_of_week=DayOfWeek.TUE,
            start_time=time(11, 0),
            end_time=time(12, 30),
            start_date=semester_start,
            end_date=semester_end,
        ),
        RecurringEvent(
            name="AI Lab",
            day_of_week=DayOfWeek.WED,
            start_time=time(14, 0),
            end_time=time(16, 0),
            start_date=semester_start,
            end_date=semester_end,
        ),
        RecurringEvent(
            name="Software Engineering",
            day_of_week=DayOfWeek.THU,
            start_time=time(9, 0),
            end_time=time(10, 30),
            start_date=semester_start,
            end_date=semester_end,
        ),
        RecurringEvent(
            name="Research Seminar",
            day_of_week=DayOfWeek.FRI,
            start_time=time(13, 0),
            end_time=time(14, 0),
            start_date=semester_start,
            end_date=semester_end,
        ),
    ]

    # One-off events
    one_off_events = [
        {
            "event": FixedEvent(name="Group Meeting", day=DayOfWeek.WED,
                                start_time=time(10, 0), end_time=time(11, 0)),
            "date": date(2026, 7, 29),  # Wednesday
        },
    ]

    # Tasks
    tasks = [
        # Urgent: due tomorrow (Tuesday) at 17:00, 60 min
        Task(
            name="Urgent homework",
            deadline=datetime(2026, 7, 28, 17, 0),
            estimated_minutes=60,
            importance=4,
            id="urgent01",
        ),
        # Large: 5 hours, due Friday 23:59
        Task(
            name="Database coursework",
            deadline=datetime(2026, 7, 31, 23, 59),
            estimated_minutes=300,
            importance=5,
            id="large01",
        ),
        # Medium: 90 min, due Thursday 18:00
        Task(
            name="AI revision notes",
            deadline=datetime(2026, 7, 30, 18, 0),
            estimated_minutes=90,
            importance=3,
            id="medium01",
        ),
        # Low priority: due next Sunday, 45 min
        Task(
            name="Read optional paper",
            deadline=datetime(2026, 8, 2, 22, 0),
            estimated_minutes=45,
            importance=1,
            id="low01",
        ),
    ]

    return now, one_off_events, recurring_events, tasks


def main():
    now, one_off_events, recurring_events, tasks = build_test_scenario()
    today = now.date()

    print("=" * 60)
    print("GAPFLOW WEEKLY PLANNER TEST")
    print("=" * 60)
    print(f"\n  Now: {now.strftime('%Y-%m-%d %H:%M')} (Monday)")
    print(f"  Planning: {today} to {today + timedelta(days=6)}")
    print(f"  Tasks: {len(tasks)}")
    print(f"  Recurring events: {len(recurring_events)}")

    # Generate the weekly plan
    plan = generate_weekly_plan(
        one_off_events=one_off_events,
        recurring_events=recurring_events,
        tasks=tasks,
        now=now,
        num_days=7,
    )

    # Print the plan
    print("\n" + "-" * 60)
    print("GENERATED WEEKLY PLAN:")
    print("-" * 60)

    for day_plan in plan.days:
        day_label = f"{day_plan.date.strftime('%a %b %d')} ({day_plan.day.value})"
        print(f"\n  {day_label}")
        print(f"  {'─' * 40}")

        # Unified timeline
        timeline = []
        for evt in day_plan.fixed_events:
            timeline.append((evt.start_time, "FIXED", evt.name, evt.end_time))
        for block in day_plan.scheduled_blocks:
            timeline.append((block.start_time, "STUDY", f"{block.task_name} ({block.allocated_minutes}m)", block.end_time))
        timeline.sort(key=lambda x: x[0])

        if timeline:
            for start, typ, label, end in timeline:
                icon = "  [F]" if typ == "FIXED" else "  [S]"
                print(f"    {start.strftime('%H:%M')}-{end.strftime('%H:%M')} {icon} {label}")
        else:
            print("    (no events or study blocks)")

        print(f"    Free: {day_plan.total_free_minutes} min | Study: {day_plan.total_study_minutes} min")

    # Weekly summary
    print("\n" + "-" * 60)
    print("WEEKLY METRICS:")
    print("-" * 60)
    print(f"  Total free time: {plan.total_free_minutes} min ({plan.total_free_minutes / 60:.1f} h)")
    print(f"  Total study scheduled: {plan.total_study_minutes} min ({plan.total_study_minutes / 60:.1f} h)")
    print(f"  Warnings: {len(plan.warnings)}")
    for w in plan.warnings:
        print(f"    {w.status}: {w.task.name} (shortfall: {w.shortfall_minutes} min)")

    # ─────────────────────────────────────────────────────────
    # ASSERTIONS
    # ─────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("ASSERTIONS:")
    print("=" * 60)

    all_blocks = plan.all_blocks

    # 1. No scheduled block occurs after its task's deadline
    task_map = {t.id: t for t in tasks}
    for block in all_blocks:
        task = task_map[block.task_id]
        block_end_dt = datetime.combine(block.date, block.end_time)
        assert block_end_dt <= task.deadline, \
            f"FAIL: '{block.task_name}' block ends {block_end_dt} after deadline {task.deadline}"
    print("  1. [PASS] No block scheduled after its deadline")

    # 2. No scheduled block overlaps a fixed event
    for day_plan in plan.days:
        for block in day_plan.scheduled_blocks:
            for evt in day_plan.fixed_events:
                # Overlap: block.start < evt.end AND block.end > evt.start
                overlaps = block.start_time < evt.end_time and block.end_time > evt.start_time
                assert not overlaps, \
                    f"FAIL: Block '{block.task_name}' ({block.start_time}-{block.end_time}) " \
                    f"overlaps event '{evt.name}' ({evt.start_time}-{evt.end_time}) on {day_plan.date}"
    print("  2. [PASS] No block overlaps a fixed event")

    # 3. Today's blocks are never in the past
    today_plan = plan.days[0]
    for block in today_plan.scheduled_blocks:
        assert block.start_time >= now.time(), \
            f"FAIL: Today's block '{block.task_name}' starts at {block.start_time}, before now ({now.time()})"
    print("  3. [PASS] Today's blocks are never in the past")

    # 4. Long tasks can be split across several days
    large_task_days = set()
    for block in all_blocks:
        if block.task_id == "large01":
            large_task_days.add(block.date)
    assert len(large_task_days) >= 2, \
        f"FAIL: Large task (300 min) only on {len(large_task_days)} day(s), expected >= 2"
    print(f"  4. [PASS] Large task split across {len(large_task_days)} days")

    # 5. Earlier deadlines are protected (urgent task fully scheduled)
    urgent_total = sum(b.allocated_minutes for b in all_blocks if b.task_id == "urgent01")
    assert urgent_total >= 60, \
        f"FAIL: Urgent task only got {urgent_total} min, needs 60"
    print(f"  5. [PASS] Urgent task fully scheduled: {urgent_total} min")

    # 6. Recurring timetable events are expanded correctly
    # Monday should have "Algorithms Lecture" as a fixed event
    monday_plan = plan.days[0]
    monday_event_names = [e.name for e in monday_plan.fixed_events]
    assert "Algorithms Lecture" in monday_event_names, \
        f"FAIL: Monday missing 'Algorithms Lecture'. Events: {monday_event_names}"
    # Tuesday should have "Database Systems"
    tuesday_plan = plan.days[1]
    tuesday_event_names = [e.name for e in tuesday_plan.fixed_events]
    assert "Database Systems" in tuesday_event_names, \
        f"FAIL: Tuesday missing 'Database Systems'. Events: {tuesday_event_names}"
    print("  6. [PASS] Recurring events expanded correctly (Mon: Algorithms, Tue: DB)")

    # 7. Total allocated minutes never exceed task remaining workload
    for task in tasks:
        allocated = sum(b.allocated_minutes for b in all_blocks if b.task_id == task.id)
        assert allocated <= task.remaining_minutes, \
            f"FAIL: Task '{task.name}' allocated {allocated} min but only needs {task.remaining_minutes} min"
    print("  7. [PASS] No task over-allocated")

    # Bonus: task coverage summary
    print("\n" + "-" * 60)
    print("TASK COVERAGE:")
    print("-" * 60)
    for task in tasks:
        allocated = sum(b.allocated_minutes for b in all_blocks if b.task_id == task.id)
        pct = int((allocated / task.remaining_minutes) * 100) if task.remaining_minutes > 0 else 100
        status = "FULL" if allocated >= task.remaining_minutes else f"{allocated}/{task.remaining_minutes} min"
        print(f"  {task.name}: {status} ({pct}%)")

    print("\n" + "=" * 60)
    print("ALL WEEKLY PLANNER ASSERTIONS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    main()
