"""
GapFlow Core Test Script
========================
Demonstrates free-slot detection, priority scoring, and task scheduling
with a sample student timetable.
"""

from datetime import datetime, date, time

from gapflow.core.models import DayOfWeek, FixedEvent, Task, FreeSlot
from gapflow.core.slots import detect_free_slots
from gapflow.core.priority import rank_tasks
from gapflow.core.scheduler import schedule_tasks


def main():
    # --- Sample timetable for a Wednesday ---
    today = date(2026, 7, 23)  # A Thursday for demo, but we'll label it Wednesday
    day = DayOfWeek.WED
    now = datetime(2026, 7, 23, 8, 0)

    events = [
        FixedEvent(name="Linear Algebra", day=DayOfWeek.WED,
                   start_time=time(9, 0), end_time=time(10, 0)),
        FixedEvent(name="Physics Lab", day=DayOfWeek.WED,
                   start_time=time(11, 0), end_time=time(13, 0)),
        FixedEvent(name="English Seminar", day=DayOfWeek.WED,
                   start_time=time(14, 0), end_time=time(15, 30)),
        FixedEvent(name="Group Project Meeting", day=DayOfWeek.WED,
                   start_time=time(17, 0), end_time=time(18, 0)),
    ]

    # --- Sample tasks ---
    tasks = [
        Task(
            name="Finish calculus problem set",
            deadline=datetime(2026, 7, 24, 9, 0),  # Due tomorrow morning
            estimated_minutes=90,
            importance=5,
        ),
        Task(
            name="Read Chapter 7 for physics",
            deadline=datetime(2026, 7, 25, 11, 0),  # Due in 2 days
            estimated_minutes=45,
            importance=3,
        ),
        Task(
            name="Review flashcards for English vocab",
            deadline=datetime(2026, 7, 24, 14, 0),  # Due tomorrow afternoon
            estimated_minutes=20,
            importance=2,
        ),
        Task(
            name="Start coding assignment",
            deadline=datetime(2026, 7, 28, 23, 59),  # Due in 5 days
            estimated_minutes=120,
            importance=4,
        ),
        Task(
            name="Write lab report introduction",
            deadline=datetime(2026, 7, 25, 9, 0),  # Due in 2 days
            estimated_minutes=60,
            importance=4,
        ),
    ]

    # ===========================================
    # 1. Detect free slots
    # ===========================================
    print("=" * 60)
    print("FREE SLOTS DETECTED (Wednesday)")
    print("=" * 60)

    free_slots = detect_free_slots(events, day, today)

    for slot in free_slots:
        print(f"  {slot.start_time.strftime('%H:%M')} - "
              f"{slot.end_time.strftime('%H:%M')}  "
              f"({slot.duration_minutes} min)")

    total_free = sum(s.duration_minutes for s in free_slots)
    print(f"\n  Total free time: {total_free} minutes ({total_free / 60:.1f} hours)")

    # ===========================================
    # 2. Task priority scores
    # ===========================================
    print("\n" + "=" * 60)
    print("TASK PRIORITY SCORES")
    print("=" * 60)

    ranked = rank_tasks(tasks, now, free_slots)

    for i, (task, score) in enumerate(ranked, 1):
        deadline_str = task.deadline.strftime("%b %d %H:%M")
        print(f"  {i}. [{score:5.2f}] {task.name}")
        print(f"           Deadline: {deadline_str} | "
              f"Duration: {task.estimated_minutes} min | "
              f"Importance: {task.importance}/5")

    # ===========================================
    # 3. Generated schedule
    # ===========================================
    print("\n" + "=" * 60)
    print("GENERATED SCHEDULE")
    print("=" * 60)

    blocks = schedule_tasks(tasks, free_slots, now)

    if not blocks:
        print("  No blocks scheduled (no tasks or no free time).")
    else:
        current_slot_start = None
        for block in blocks:
            # Show which slot this block falls in
            print(f"  {block.start_time.strftime('%H:%M')} - "
                  f"{block.end_time.strftime('%H:%M')}  "
                  f"[{block.allocated_minutes:3d} min]  "
                  f"{block.task_name}")

    # Show unscheduled time
    scheduled_total = sum(b.allocated_minutes for b in blocks)
    print(f"\n  Scheduled: {scheduled_total} min / {total_free} min available")

    if scheduled_total < total_free:
        print(f"  Remaining free: {total_free - scheduled_total} min")

    # Show task completion status
    print("\n" + "-" * 60)
    print("TASK COVERAGE:")
    print("-" * 60)
    for task in tasks:
        allocated = sum(b.allocated_minutes for b in blocks if b.task_id == task.id)
        status = "COMPLETE" if allocated >= task.remaining_minutes else f"{allocated}/{task.remaining_minutes} min"
        print(f"  {task.name}: {status}")


if __name__ == "__main__":
    main()
