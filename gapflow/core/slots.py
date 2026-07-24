"""Free-slot detection: finds gaps between fixed events in a day."""

from datetime import time, date, datetime

from .models import DayOfWeek, FixedEvent, FreeSlot


# Default active hours for a student's day
DEFAULT_DAY_START = time(8, 0)
DEFAULT_DAY_END = time(22, 0)


def detect_free_slots(
    events: list[FixedEvent],
    target_day: DayOfWeek,
    target_date: date,
    day_start: time = DEFAULT_DAY_START,
    day_end: time = DEFAULT_DAY_END,
    min_slot_minutes: int = 15,
    now: datetime | None = None,
) -> list[FreeSlot]:
    """
    Detect free time slots on a given day between fixed events.

    Args:
        events: All fixed events in the timetable.
        target_day: The day of the week to analyze.
        target_date: The actual date (for the FreeSlot output).
        day_start: Earliest time the student is available.
        day_end: Latest time the student is available.
        min_slot_minutes: Minimum gap (in minutes) to count as a free slot.
        now: Current datetime. If the target_date is today, slots before now are trimmed.

    Returns:
        List of FreeSlot objects sorted by start time.
    """
    # Filter events for the target day and sort by start time
    day_events = sorted(
        [e for e in events if e.day == target_day],
        key=lambda e: e.start_time,
    )

    free_slots: list[FreeSlot] = []
    current_time = day_start

    for event in day_events:
        # If there's a gap before this event
        if event.start_time > current_time:
            slot = FreeSlot(
                day=target_day,
                date=target_date,
                start_time=current_time,
                end_time=event.start_time,
            )
            if slot.duration_minutes >= min_slot_minutes:
                free_slots.append(slot)

        # Move current_time past this event
        if event.end_time > current_time:
            current_time = event.end_time

    # Check for gap after the last event until day_end
    if current_time < day_end:
        slot = FreeSlot(
            day=target_day,
            date=target_date,
            start_time=current_time,
            end_time=day_end,
        )
        if slot.duration_minutes >= min_slot_minutes:
            free_slots.append(slot)

    # --- Filter out past slots if target_date is today ---
    if now is None:
        now = datetime.now()

    if target_date == now.date():
        current_t = now.time()
        filtered: list[FreeSlot] = []
        for slot in free_slots:
            if slot.end_time <= current_t:
                # Entire slot is in the past — skip it
                continue
            elif slot.start_time < current_t:
                # Slot partially in the past — trim to start from now
                trimmed = FreeSlot(
                    day=slot.day,
                    date=slot.date,
                    start_time=current_t,
                    end_time=slot.end_time,
                )
                if trimmed.duration_minutes >= min_slot_minutes:
                    filtered.append(trimmed)
            else:
                # Slot is entirely in the future — keep it
                filtered.append(slot)
        free_slots = filtered

    return free_slots


def detect_all_free_slots(
    events: list[FixedEvent],
    target_date: date,
    days: list[DayOfWeek] | None = None,
    day_start: time = DEFAULT_DAY_START,
    day_end: time = DEFAULT_DAY_END,
    min_slot_minutes: int = 15,
) -> list[FreeSlot]:
    """
    Detect free slots across multiple days.

    Args:
        events: All fixed events.
        target_date: The Monday of the week (or any reference date).
        days: Which days to scan. Defaults to Mon–Fri.
        day_start: Earliest available time.
        day_end: Latest available time.
        min_slot_minutes: Minimum gap to count.

    Returns:
        All free slots across the specified days.
    """
    if days is None:
        days = [DayOfWeek.MON, DayOfWeek.TUE, DayOfWeek.WED,
                DayOfWeek.THU, DayOfWeek.FRI]

    all_slots: list[FreeSlot] = []
    for day in days:
        slots = detect_free_slots(
            events, day, target_date, day_start, day_end, min_slot_minutes
        )
        all_slots.extend(slots)

    return all_slots
