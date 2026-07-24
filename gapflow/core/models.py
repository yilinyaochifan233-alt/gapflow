"""GapFlow data models."""

from dataclasses import dataclass, field
from datetime import datetime, date, time
from enum import Enum
import uuid


class DayOfWeek(Enum):
    MON = "Monday"
    TUE = "Tuesday"
    WED = "Wednesday"
    THU = "Thursday"
    FRI = "Friday"
    SAT = "Saturday"
    SUN = "Sunday"


@dataclass
class FixedEvent:
    """A fixed event in the student's timetable (e.g., a lecture)."""
    name: str
    day: DayOfWeek
    start_time: time
    end_time: time

    @property
    def duration_minutes(self) -> int:
        start_dt = datetime.combine(date.today(), self.start_time)
        end_dt = datetime.combine(date.today(), self.end_time)
        return int((end_dt - start_dt).total_seconds() / 60)


@dataclass
class Task:
    """A task the student needs to complete."""
    name: str
    deadline: datetime
    estimated_minutes: int
    importance: int  # 1 (low) to 5 (high)
    remaining_minutes: int = 0
    id: str = ""

    def __post_init__(self):
        if not self.remaining_minutes:
            self.remaining_minutes = self.estimated_minutes
        if not self.id:
            self.id = str(uuid.uuid4())[:8]


@dataclass
class FreeSlot:
    """A detected free time slot between fixed events."""
    day: DayOfWeek
    date: date
    start_time: time
    end_time: time

    @property
    def duration_minutes(self) -> int:
        start_dt = datetime.combine(self.date, self.start_time)
        end_dt = datetime.combine(self.date, self.end_time)
        return int((end_dt - start_dt).total_seconds() / 60)


@dataclass
class ScheduledBlock:
    """A task allocated to a specific time block."""
    task_id: str
    task_name: str
    day: DayOfWeek
    date: date
    start_time: time
    end_time: time
    allocated_minutes: int


@dataclass
class DailySchedule:
    """Complete schedule for a single day."""
    date: date
    fixed_events: list[FixedEvent] = field(default_factory=list)
    scheduled_blocks: list[ScheduledBlock] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────
# Day-of-week lookup for recurring events
# ─────────────────────────────────────────────────────────────
DAY_NAME_TO_ENUM = {
    "monday": DayOfWeek.MON,
    "tuesday": DayOfWeek.TUE,
    "wednesday": DayOfWeek.WED,
    "thursday": DayOfWeek.THU,
    "friday": DayOfWeek.FRI,
    "saturday": DayOfWeek.SAT,
    "sunday": DayOfWeek.SUN,
}

DAY_ENUM_TO_WEEKDAY = {
    DayOfWeek.MON: 0,
    DayOfWeek.TUE: 1,
    DayOfWeek.WED: 2,
    DayOfWeek.THU: 3,
    DayOfWeek.FRI: 4,
    DayOfWeek.SAT: 5,
    DayOfWeek.SUN: 6,
}


@dataclass
class RecurringEvent:
    """A weekly recurring event (e.g., a lecture that repeats every week during the semester)."""
    name: str
    day_of_week: DayOfWeek
    start_time: time
    end_time: time
    start_date: date  # Semester start (first possible occurrence)
    end_date: date    # Semester end (last possible occurrence)
    id: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:8]

    @property
    def duration_minutes(self) -> int:
        start_dt = datetime.combine(date.today(), self.start_time)
        end_dt = datetime.combine(date.today(), self.end_time)
        return int((end_dt - start_dt).total_seconds() / 60)

    def expand(self, range_start: date, range_end: date) -> list[FixedEvent]:
        """
        Expand this recurring event into concrete FixedEvent instances
        for all occurrences within the given date range.

        Only generates events on the correct day_of_week that fall within
        both the semester dates AND the requested range.

        Args:
            range_start: Start of the range to generate events for.
            range_end: End of the range (inclusive).

        Returns:
            List of FixedEvent instances, one per occurrence.
        """
        from datetime import timedelta

        events: list[FixedEvent] = []

        # Effective range: intersection of semester dates and requested range
        effective_start = max(self.start_date, range_start)
        effective_end = min(self.end_date, range_end)

        if effective_start > effective_end:
            return events

        # Find the first occurrence of day_of_week on or after effective_start
        target_weekday = DAY_ENUM_TO_WEEKDAY[self.day_of_week]
        current = effective_start
        days_ahead = (target_weekday - current.weekday()) % 7
        current = current + timedelta(days=days_ahead)

        # Generate all weekly occurrences
        while current <= effective_end:
            events.append(FixedEvent(
                name=self.name,
                day=self.day_of_week,
                start_time=self.start_time,
                end_time=self.end_time,
            ))
            current += timedelta(weeks=1)

        return events


def expand_recurring_events(
    recurring_events: list[RecurringEvent],
    range_start: date,
    range_end: date,
) -> list[tuple[FixedEvent, date]]:
    """
    Expand all recurring events into concrete FixedEvent instances
    for the requested date range.

    Args:
        recurring_events: List of recurring weekly events.
        range_start: Start of the date range.
        range_end: End of the date range (inclusive).

    Returns:
        List of (FixedEvent, occurrence_date) tuples.
    """
    from datetime import timedelta

    results: list[tuple[FixedEvent, date]] = []

    for recurring in recurring_events:
        effective_start = max(recurring.start_date, range_start)
        effective_end = min(recurring.end_date, range_end)

        if effective_start > effective_end:
            continue

        target_weekday = DAY_ENUM_TO_WEEKDAY[recurring.day_of_week]
        current = effective_start
        days_ahead = (target_weekday - current.weekday()) % 7
        current = current + timedelta(days=days_ahead)

        while current <= effective_end:
            event = FixedEvent(
                name=recurring.name,
                day=recurring.day_of_week,
                start_time=recurring.start_time,
                end_time=recurring.end_time,
            )
            results.append((event, current))
            current += timedelta(weeks=1)

    return results
