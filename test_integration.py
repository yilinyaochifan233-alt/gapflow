"""
GapFlow Integration Test
========================
End-to-end pipeline:
  1. Parse natural-language tasks via Strands Agent (Bedrock)
  2. Detect free time slots from a fixed timetable
  3. Calculate priority scores
  4. Generate a schedule using the core scheduler

Prerequisites:
    - AWS credentials configured
    - Model access enabled in Amazon Bedrock
    - pip install strands-agents boto3

Usage:
    py test_integration.py
"""

from datetime import datetime, date, time

from gapflow.agent import create_agent, parse_tasks_from_texts
from gapflow.core.models import DayOfWeek, FixedEvent
from gapflow.core.slots import detect_free_slots
from gapflow.core.priority import rank_tasks
from gapflow.core.scheduler import schedule_tasks


def main():
    # =========================================================
    # 1. Define a fixed timetable (Thursday)
    # =========================================================
    today = date.today()
    day = DayOfWeek.THU
    now = datetime.now()

    timetable = [
        FixedEvent(name="Data Structures Lecture", day=DayOfWeek.THU,
                   start_time=time(9, 0), end_time=time(10, 30)),
        FixedEvent(name="Algorithms Tutorial", day=DayOfWeek.THU,
                   start_time=time(11, 0), end_time=time(12, 0)),
        FixedEvent(name="Lunch Break", day=DayOfWeek.THU,
                   start_time=time(12, 0), end_time=time(13, 0)),
        FixedEvent(name="Software Engineering Lab", day=DayOfWeek.THU,
                   start_time=time(14, 0), end_time=time(16, 0)),
    ]

    # =========================================================
    # 2. Natural-language task descriptions (sent to the agent)
    # =========================================================
    task_descriptions = [
        "I have a database coursework due tomorrow at 5pm. It will take about 3 hours and it is very important.",
        "Need to review my biology flashcards before Friday's exam at 9am. Should take about 25 minutes, moderately important.",
        "I have to write the introduction for my group project report. Deadline is next Monday at midnight. Probably 2 hours of work, it's important.",
    ]

    print("=" * 60)
    print("GAPFLOW INTEGRATION TEST")
    print("=" * 60)
    print(f"\nToday: {today} ({day.value})")
    print(f"Now:   {now.strftime('%H:%M')}")

    # =========================================================
    # 3. Parse tasks through the Strands Agent
    # =========================================================
    print("\n" + "=" * 60)
    print("STEP 1: PARSING TASKS VIA STRANDS AGENT")
    print("=" * 60)

    print("\nConnecting to Amazon Bedrock...")
    agent = create_agent()

    tasks = parse_tasks_from_texts(task_descriptions, agent=agent)

    print(f"\nParsed {len(tasks)} tasks:\n")
    for i, task in enumerate(tasks, 1):
        print(f"  {i}. {task.name}")
        print(f"     Deadline: {task.deadline.strftime('%Y-%m-%d %H:%M')}")
        print(f"     Duration: {task.estimated_minutes} min")
        print(f"     Importance: {task.importance}/5")
        print(f"     ID: {task.id}")
        print()

    # =========================================================
    # 4. Detect free time slots
    # =========================================================
    print("=" * 60)
    print("STEP 2: FREE SLOTS DETECTED")
    print("=" * 60)

    free_slots = detect_free_slots(timetable, day, today)

    print()
    for slot in free_slots:
        print(f"  {slot.start_time.strftime('%H:%M')} - "
              f"{slot.end_time.strftime('%H:%M')}  "
              f"({slot.duration_minutes} min)")

    total_free = sum(s.duration_minutes for s in free_slots)
    print(f"\n  Total free time: {total_free} min ({total_free / 60:.1f} hours)")

    # =========================================================
    # 5. Calculate priority scores
    # =========================================================
    print("\n" + "=" * 60)
    print("STEP 3: PRIORITY SCORES")
    print("=" * 60)

    ranked = rank_tasks(tasks, now, free_slots)

    print()
    for i, (task, score) in enumerate(ranked, 1):
        print(f"  {i}. [{score:5.2f}] {task.name}")
        print(f"           Due: {task.deadline.strftime('%b %d %H:%M')} | "
              f"{task.estimated_minutes} min | "
              f"Importance: {task.importance}/5")

    # =========================================================
    # 6. Generate schedule
    # =========================================================
    print("\n" + "=" * 60)
    print("STEP 4: GENERATED SCHEDULE")
    print("=" * 60)

    blocks = schedule_tasks(tasks, free_slots, now)

    print()
    if not blocks:
        print("  No blocks scheduled.")
    else:
        for block in blocks:
            print(f"  {block.start_time.strftime('%H:%M')} - "
                  f"{block.end_time.strftime('%H:%M')}  "
                  f"[{block.allocated_minutes:3d} min]  "
                  f"{block.task_name}")

    # Summary
    scheduled_total = sum(b.allocated_minutes for b in blocks)
    print(f"\n  Scheduled: {scheduled_total} min / {total_free} min available")

    if scheduled_total < total_free:
        print(f"  Remaining free: {total_free - scheduled_total} min")

    # Task coverage
    print("\n" + "-" * 60)
    print("TASK COVERAGE:")
    print("-" * 60)
    for task in tasks:
        allocated = sum(b.allocated_minutes for b in blocks if b.task_id == task.id)
        if allocated >= task.remaining_minutes:
            status = "FULLY SCHEDULED"
        else:
            status = f"{allocated}/{task.remaining_minutes} min scheduled"
        print(f"  {task.name}: {status}")

    print("\n" + "=" * 60)
    print("INTEGRATION TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
