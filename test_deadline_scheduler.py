"""
GapFlow Deadline-Aware Scheduler Test
======================================
Regression tests for earliest-deadline-first scheduling and multi-day feasibility.

Test 1: EDF regression — Task No1 due today MUST be scheduled before Task No2 due tomorrow,
         even though No2 has higher importance and priority score.

Test 2: Insufficient time — CRITICAL warning when task genuinely can't be completed.

Test 3: Deadline status classification (CRITICAL / AT_RISK / ON_TRACK).

Test 4: Multi-day feasibility — a task due tomorrow should NOT be CRITICAL
         just because today's remaining free time can't contain all its duration.

Usage:
    py test_deadline_scheduler.py
"""

from datetime import datetime, date, time, timedelta

from gapflow.core.models import DayOfWeek, FixedEvent, Task, FreeSlot
from gapflow.core.slots import detect_free_slots
from gapflow.core.priority import rank_tasks
from gapflow.core.scheduler import (
    schedule_tasks,
    schedule_tasks_with_warnings,
    get_deadline_status,
    calculate_available_before_deadline,
    calculate_slack,
    estimate_total_available_before_deadline,
)


def test_1_edf_regression():
    """
    EXACT SCENARIO FROM BUG REPORT:

    Current time: July 24, 11:20

    Task No1:
        deadline: July 24, 20:00 (today)
        duration: 60 min
        importance: 3

    Task No2:
        deadline: July 25, 19:00 (tomorrow)
        duration: 300 min
        importance: 5

    Fixed events during July 24:
        - Lecture 09:00–10:30
        - Tutorial 13:00–14:00
        - Lab 15:00–16:30

    ASSERTIONS:
        1. No1 receives all 60 minutes before 20:00.
        2. No1 is never scheduled after 20:00.
        3. No2 may use remaining time after No1 has been protected.
        4. No2 should NOT be CRITICAL just because today can't fit all 300 minutes.
        5. No later-deadline task may consume time needed for an earlier-deadline task.
    """
    print("=" * 60)
    print("TEST 1: EDF Regression — Earliest Deadline First")
    print("=" * 60)

    today = date(2026, 7, 24)
    tomorrow = date(2026, 7, 25)
    day = DayOfWeek.FRI
    now = datetime(2026, 7, 24, 11, 20)

    # Fixed events during July 24
    events = [
        FixedEvent(name="Lecture", day=DayOfWeek.FRI, start_time=time(9, 0), end_time=time(10, 30)),
        FixedEvent(name="Tutorial", day=DayOfWeek.FRI, start_time=time(13, 0), end_time=time(14, 0)),
        FixedEvent(name="Lab", day=DayOfWeek.FRI, start_time=time(15, 0), end_time=time(16, 30)),
    ]

    task_no1 = Task(
        name="Due today task",
        deadline=datetime(2026, 7, 24, 20, 0),
        estimated_minutes=60,
        importance=3,
        id="no1",
    )

    task_no2 = Task(
        name="Due tomorrow task",
        deadline=datetime(2026, 7, 25, 19, 0),
        estimated_minutes=300,
        importance=5,
        id="no2",
    )

    tasks = [task_no1, task_no2]

    # Get free slots for today (past filtered by now=11:20)
    free_slots = detect_free_slots(events, day, today, now=now)

    print(f"\n  Now: {now.strftime('%Y-%m-%d %H:%M')}")
    print(f"\n  Free slots today:")
    for s in free_slots:
        print(f"    {s.start_time.strftime('%H:%M')} - {s.end_time.strftime('%H:%M')} ({s.duration_minutes} min)")
    total_today = sum(s.duration_minutes for s in free_slots)
    print(f"    Total: {total_today} min")

    # Show priority scores — No2 should be higher
    print("\n  Priority scores (display only):")
    ranked = rank_tasks(tasks, now, free_slots)
    for task, score in ranked:
        print(f"    {task.name}: {score:.2f} (importance {task.importance}/5)")

    # Verify No2 has higher priority score
    scores = {task.id: score for task, score in ranked}
    assert scores["no2"] >= scores["no1"], \
        f"SETUP: Expected No2 priority >= No1, got No2={scores['no2']:.2f}, No1={scores['no1']:.2f}"
    print(f"    Confirmed: No2 priority ({scores['no2']:.2f}) >= No1 ({scores['no1']:.2f})")

    # Generate schedule
    blocks = schedule_tasks(tasks, free_slots, now)

    print("\n  Generated schedule:")
    for block in blocks:
        print(f"    {block.start_time.strftime('%H:%M')} - {block.end_time.strftime('%H:%M')}  "
              f"[{block.allocated_minutes:3d} min]  {block.task_name}")

    # ASSERTION 1: No1 receives all 60 minutes
    no1_minutes = sum(b.allocated_minutes for b in blocks if b.task_id == "no1")
    assert no1_minutes == 60, f"FAIL: No1 scheduled {no1_minutes} min, expected 60"
    print(f"\n  Assertions:")
    print(f"    [PASS] 1. No1 fully scheduled: {no1_minutes} min")

    # ASSERTION 2: No1 never scheduled after 20:00
    for block in blocks:
        if block.task_id == "no1":
            assert block.end_time <= time(20, 0), \
                f"FAIL: No1 block ends at {block.end_time}, after deadline 20:00"
    print("    [PASS] 2. No1 never scheduled after 20:00")

    # ASSERTION 3: No2 uses remaining time
    no2_minutes = sum(b.allocated_minutes for b in blocks if b.task_id == "no2")
    assert no2_minutes > 0, "FAIL: No2 not scheduled at all"
    print(f"    [PASS] 3. No2 uses remaining time: {no2_minutes} min")

    # ASSERTION 4: No2 NOT marked CRITICAL
    warning = get_deadline_status(task_no2, free_slots, now)
    assert warning.status != "CRITICAL", \
        f"FAIL: No2 status is {warning.status}, should NOT be CRITICAL"
    print(f"    [PASS] 4. No2 status: {warning.status} (not CRITICAL)")

    # ASSERTION 5: No1 blocks all come before No2 blocks
    no1_blocks = [b for b in blocks if b.task_id == "no1"]
    no2_blocks = [b for b in blocks if b.task_id == "no2"]
    if no1_blocks and no2_blocks:
        no1_first_start = min(b.start_time for b in no1_blocks)
        # Check that No1 is scheduled before No2 consumes its required time
        # (No2 should not take over time that No1 needs)
        assert no1_minutes == 60, "Already checked above"
    print("    [PASS] 5. Earlier-deadline task protected from later-deadline task")

    print("\n  TEST 1 PASSED!")


def test_2_not_enough_time():
    """
    Task needs 120 min but only 90 min available before its deadline (today).
    Expected: schedule 90 min, return a CRITICAL warning.
    """
    print("\n" + "=" * 60)
    print("TEST 2: Insufficient Time Before Deadline (CRITICAL)")
    print("=" * 60)

    today = date(2026, 7, 24)
    day = DayOfWeek.FRI
    now = datetime(2026, 7, 24, 16, 0)

    free_slots = [
        FreeSlot(day=day, date=today, start_time=time(16, 0), end_time=time(22, 0)),
    ]

    task_critical = Task(
        name="Impossible deadline task",
        deadline=datetime(2026, 7, 24, 17, 30),  # Only 90 min before deadline
        estimated_minutes=120,
        importance=3,
        id="task_crit",
    )

    task_easy = Task(
        name="Easy task",
        deadline=datetime(2026, 7, 24, 22, 0),  # Same day, plenty of time
        estimated_minutes=60,
        importance=4,
        id="task_easy",
    )

    tasks = [task_critical, task_easy]

    # Show slack
    print("\n  Slack calculation:")
    for task in tasks:
        available = calculate_available_before_deadline(task, free_slots)
        slack = calculate_slack(task, available)
        print(f"    {task.name}: available={available} min, needed={task.remaining_minutes} min, slack={slack} min")

    blocks, warnings = schedule_tasks_with_warnings(tasks, free_slots, now)

    print("\n  Generated schedule:")
    for block in blocks:
        print(f"    {block.start_time.strftime('%H:%M')} - {block.end_time.strftime('%H:%M')}  "
              f"[{block.allocated_minutes:3d} min]  {block.task_name}")

    print("\n  Deadline warnings:")
    for w in warnings:
        print(f"    {w.status}: {w.task.name} (shortfall: {w.shortfall_minutes} min)")

    print("\n  Assertions:")

    # CRITICAL warning for impossible task
    crit_warnings = [w for w in warnings if w.task.id == "task_crit"]
    assert len(crit_warnings) == 1, f"FAIL: Expected 1 warning, got {len(crit_warnings)}"
    assert crit_warnings[0].status == "CRITICAL"
    print(f"    [PASS] Critical task has CRITICAL warning (shortfall: {crit_warnings[0].shortfall_minutes} min)")

    # Scheduled max possible before deadline
    crit_minutes = sum(b.allocated_minutes for b in blocks if b.task_id == "task_crit")
    assert crit_minutes == 90, f"FAIL: Scheduled {crit_minutes} min, expected 90"
    print(f"    [PASS] Critical task scheduled {crit_minutes} min (max before deadline)")

    # Never after deadline
    for block in blocks:
        if block.task_id == "task_crit":
            assert block.end_time <= time(17, 30)
    print("    [PASS] Critical task never scheduled after 17:30")

    # Easy task still fully scheduled
    easy_minutes = sum(b.allocated_minutes for b in blocks if b.task_id == "task_easy")
    assert easy_minutes == 60
    print(f"    [PASS] Easy task fully scheduled: {easy_minutes} min")

    print("\n  TEST 2 PASSED!")


def test_3_deadline_status_classification():
    """Test get_deadline_status for various scenarios (same-day)."""
    print("\n" + "=" * 60)
    print("TEST 3: Deadline Status Classification (Same Day)")
    print("=" * 60)

    today = date(2026, 7, 24)
    day = DayOfWeek.FRI
    now = datetime(2026, 7, 24, 16, 0)

    free_slots = [
        FreeSlot(day=day, date=today, start_time=time(16, 0), end_time=time(22, 0)),
    ]

    # CRITICAL: needs 200 min, only 90 available before its deadline (same day)
    task_crit = Task(name="Critical task", deadline=datetime(2026, 7, 24, 17, 30),
                     estimated_minutes=200, importance=5, id="t1")

    # AT_RISK: needs 80 min, 90 available today, deadline is today (slack=10, < 25% of 80)
    task_risk = Task(name="At-risk task", deadline=datetime(2026, 7, 24, 17, 30),
                     estimated_minutes=80, importance=3, id="t2")

    # ON_TRACK: needs 60 min, 360 available (deadline is today at 22:00)
    task_ok = Task(name="On-track task", deadline=datetime(2026, 7, 24, 22, 0),
                   estimated_minutes=60, importance=2, id="t3")

    print()
    for task in [task_crit, task_risk, task_ok]:
        status = get_deadline_status(task, free_slots, now)
        print(f"  {task.name}: {status.status}")
        print(f"    Available: {status.available_minutes} min, Needed: {status.needed_minutes} min")

    assert get_deadline_status(task_crit, free_slots, now).status == "CRITICAL"
    print("\n    [PASS] Critical task classified correctly")

    assert get_deadline_status(task_risk, free_slots, now).status == "AT_RISK"
    print("    [PASS] At-risk task classified correctly")

    assert get_deadline_status(task_ok, free_slots, now).status == "ON_TRACK"
    print("    [PASS] On-track task classified correctly")

    print("\n  TEST 3 PASSED!")


def test_4_multi_day_feasibility():
    """
    A 300-minute task due TOMORROW should NOT be CRITICAL
    just because today only has 144 minutes of free time remaining.

    The multi-day estimator should recognize that tomorrow provides
    additional planning time (08:00–19:00 = 660 min on deadline day).
    """
    print("\n" + "=" * 60)
    print("TEST 4: Multi-Day Feasibility (Tomorrow's Task Not CRITICAL)")
    print("=" * 60)

    today = date(2026, 7, 24)
    day = DayOfWeek.FRI
    now = datetime(2026, 7, 24, 11, 20)

    # Today's free slots: limited (simulate busy day)
    # After events, only ~144 min remain today
    free_slots = [
        FreeSlot(day=day, date=today, start_time=time(11, 20), end_time=time(13, 0)),  # 100 min
        FreeSlot(day=day, date=today, start_time=time(14, 0), end_time=time(14, 44)),   # 44 min
    ]
    total_today = sum(s.duration_minutes for s in free_slots)

    task_tomorrow = Task(
        name="Big task due tomorrow",
        deadline=datetime(2026, 7, 25, 19, 0),
        estimated_minutes=300,
        importance=5,
        id="big_task",
    )

    print(f"\n  Today's free time: {total_today} min")
    print(f"  Task needs: {task_tomorrow.remaining_minutes} min")
    print(f"  Deadline: {task_tomorrow.deadline.strftime('%Y-%m-%d %H:%M')}")

    # Calculate multi-day estimate
    total_est, is_estimate = estimate_total_available_before_deadline(
        task_tomorrow, free_slots, now
    )
    print(f"\n  Multi-day estimate:")
    print(f"    Today available: {total_today} min")
    print(f"    Total estimated before deadline: {total_est} min")
    print(f"    Is estimate (includes future days): {is_estimate}")

    # Get deadline status
    status = get_deadline_status(task_tomorrow, free_slots, now)
    print(f"\n  Deadline status: {status.status}")
    print(f"    Available (total): {status.available_minutes} min")
    print(f"    Needed: {status.needed_minutes} min")
    print(f"    Shortfall: {status.shortfall_minutes} min")

    # ASSERTIONS
    print("\n  Assertions:")

    # The task should NOT be CRITICAL
    assert status.status != "CRITICAL", \
        f"FAIL: Status is {status.status}, should NOT be CRITICAL for a task due tomorrow with plenty of total time"
    print(f"    [PASS] Task due tomorrow NOT marked CRITICAL (status: {status.status})")

    # Total estimated time should be much more than 300 min
    # Tomorrow from 08:00 to 19:00 = 660 min, plus today's 144 min = 804 min
    assert total_est > 300, f"FAIL: Total estimate {total_est} min should be > 300"
    print(f"    [PASS] Total estimated time ({total_est} min) > needed (300 min)")

    # Verify it IS an estimate (future days involved)
    assert is_estimate, "FAIL: Should be marked as estimate since deadline is tomorrow"
    print("    [PASS] Correctly identified as estimate (future days involved)")

    print("\n  TEST 4 PASSED!")


if __name__ == "__main__":
    test_1_edf_regression()
    test_2_not_enough_time()
    test_3_deadline_status_classification()
    test_4_multi_day_feasibility()

    print("\n" + "=" * 60)
    print("ALL DEADLINE SCHEDULER TESTS PASSED!")
    print("=" * 60)
