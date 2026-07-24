"""
GapFlow Replan Test Script
==========================
Tests the dynamic replanning pipeline:
  1. Build an initial schedule
  2. Send a natural-language change to the Strands Agent
  3. Apply the change and regenerate the schedule
  4. Compare before vs. after

Prerequisites:
    - AWS credentials configured
    - Model access enabled in Amazon Bedrock
    - pip install strands-agents boto3

Usage:
    py test_replan.py
"""

from datetime import datetime, date, time

from gapflow.core.models import DayOfWeek, FixedEvent, Task
from gapflow.core.slots import detect_free_slots
from gapflow.core.scheduler import schedule_tasks
from gapflow.core.replanner import replan_schedule
from gapflow.agent import create_replan_agent, process_replan_request


def print_schedule(blocks, events, label="SCHEDULE"):
    """Print a schedule in a readable format."""
    timeline = []

    for evt in events:
        timeline.append({
            "start": evt.start_time,
            "end": evt.end_time,
            "label": evt.name,
            "type": "fixed",
        })

    for block in blocks:
        timeline.append({
            "start": block.start_time,
            "end": block.end_time,
            "label": f"{block.task_name} ({block.allocated_minutes} min)",
            "type": "study",
        })

    timeline.sort(key=lambda x: x["start"])

    print(f"\n  {label}:")
    for item in timeline:
        icon = "  [FIXED]" if item["type"] == "fixed" else "  [STUDY]"
        print(f"    {item['start'].strftime('%H:%M')} - {item['end'].strftime('%H:%M')} {icon} {item['label']}")


def main():
    print("=" * 60)
    print("GAPFLOW REPLAN TEST")
    print("=" * 60)

    # ─────────────────────────────────────────────────────────
    # Setup: fixed timetable and tasks
    # ─────────────────────────────────────────────────────────
    today = date.today()
    day = DayOfWeek.THU
    # Simulate "now" as 14:00 so we have afternoon slots to work with
    now = datetime.combine(today, time(14, 0))

    events = [
        FixedEvent(name="Data Structures Lecture", day=DayOfWeek.THU,
                   start_time=time(9, 0), end_time=time(10, 30)),
        FixedEvent(name="Lunch", day=DayOfWeek.THU,
                   start_time=time(12, 0), end_time=time(13, 0)),
    ]

    tasks = [
        Task(
            name="Database coursework",
            deadline=datetime.combine(today, time(23, 59)),
            estimated_minutes=120,
            importance=5,
        ),
        Task(
            name="Biology flashcards",
            deadline=datetime.combine(today, time(22, 0)),
            estimated_minutes=25,
            importance=2,
        ),
        Task(
            name="Group project report",
            deadline=datetime(today.year, today.month, today.day + 2, 17, 0),
            estimated_minutes=90,
            importance=4,
        ),
    ]

    # ─────────────────────────────────────────────────────────
    # Step 1: Generate ORIGINAL schedule
    # ─────────────────────────────────────────────────────────
    print("\n" + "-" * 60)
    print("STEP 1: ORIGINAL SCHEDULE (now = 14:00)")
    print("-" * 60)

    free_slots = detect_free_slots(events, day, today, now=now)
    print("\n  Free slots:")
    for s in free_slots:
        print(f"    {s.start_time.strftime('%H:%M')} - {s.end_time.strftime('%H:%M')} ({s.duration_minutes} min)")

    original_blocks = schedule_tasks(tasks, free_slots, now)
    print_schedule(original_blocks, events, "ORIGINAL SCHEDULE")

    # ─────────────────────────────────────────────────────────
    # Step 2: User describes a change
    # ─────────────────────────────────────────────────────────
    change_text = "I suddenly have a meeting from 16:00 to 17:30."

    print("\n" + "-" * 60)
    print("STEP 2: USER CHANGE")
    print("-" * 60)
    print(f"\n  User says: \"{change_text}\"")
    print("\n  Sending to Strands Agent...")

    actions, explanation = process_replan_request(change_text, tasks=tasks)

    print(f"\n  Agent parsed {len(actions)} action(s):")
    for action in actions:
        print(f"    - {action['action_type']}: {action.get('event_name', '')} "
              f"{action.get('start_time', '')}–{action.get('end_time', '')}")

    print(f"\n  Agent explanation:")
    for line in explanation.split("\n"):
        print(f"    {line}")

    # ─────────────────────────────────────────────────────────
    # Step 3: Apply change and regenerate schedule
    # ─────────────────────────────────────────────────────────
    print("\n" + "-" * 60)
    print("STEP 3: REPLANNED SCHEDULE")
    print("-" * 60)

    result = replan_schedule(actions, events, tasks, day, today, now)

    print("\n  Action results:")
    for r in result["action_results"]:
        status = "OK" if r["success"] else "FAIL"
        print(f"    [{status}] {r['message']}")

    print("\n  Updated free slots:")
    for s in result["new_free_slots"]:
        print(f"    {s.start_time.strftime('%H:%M')} - {s.end_time.strftime('%H:%M')} ({s.duration_minutes} min)")

    print_schedule(result["new_schedule"], events, "NEW SCHEDULE")

    # ─────────────────────────────────────────────────────────
    # Step 4: Compare
    # ─────────────────────────────────────────────────────────
    print("\n" + "-" * 60)
    print("COMPARISON")
    print("-" * 60)

    print(f"\n  Original study blocks: {len(original_blocks)}")
    print(f"  New study blocks:      {len(result['new_schedule'])}")
    print(f"  Original total study:  {sum(b.allocated_minutes for b in original_blocks)} min")
    print(f"  New total study:       {sum(b.allocated_minutes for b in result['new_schedule'])} min")

    # Task coverage
    print("\n  Task coverage after replan:")
    for task in tasks:
        allocated = sum(b.allocated_minutes for b in result["new_schedule"] if b.task_id == task.id)
        status = "DONE" if task.remaining_minutes == 0 else f"{allocated}/{task.remaining_minutes} min"
        print(f"    {task.name}: {status}")

    print("\n" + "=" * 60)
    print("REPLAN TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
