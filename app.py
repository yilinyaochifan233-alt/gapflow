"""
GapFlow — AI-Powered Student Schedule Optimizer
================================================
Streamlit MVP interface.

Launch:
    streamlit run app.py
"""

import streamlit as st
from datetime import datetime, date, time, timedelta

from gapflow.core.models import DayOfWeek, FixedEvent, Task, RecurringEvent, DAY_NAME_TO_ENUM, expand_recurring_events
from gapflow.core.slots import detect_free_slots
from gapflow.core.priority import rank_tasks
from gapflow.core.scheduler import schedule_tasks, schedule_tasks_with_warnings, get_deadline_status
from gapflow.core.replanner import replan_schedule
from gapflow.core.weekly_planner import generate_weekly_plan, WeeklyPlan
from gapflow.agent import create_agent, create_replan_agent, process_replan_request, parse_batch_tasks
from gapflow.tools.parse_task import get_parsed_tasks, clear_parsed_tasks


# ─────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="GapFlow",
    page_icon="📚",
    layout="wide",
)

st.title("GapFlow")
st.caption("AI-powered schedule optimizer for university students")

# ─────────────────────────────────────────────────────────────
# Session state initialization
# ─────────────────────────────────────────────────────────────
if "timetable" not in st.session_state:
    st.session_state.timetable = []

if "tasks" not in st.session_state:
    st.session_state.tasks = []

if "agent" not in st.session_state:
    st.session_state.agent = None

if "schedule_blocks" not in st.session_state:
    st.session_state.schedule_blocks = []

if "free_slots" not in st.session_state:
    st.session_state.free_slots = []

if "previous_schedule" not in st.session_state:
    st.session_state.previous_schedule = []

if "replan_explanation" not in st.session_state:
    st.session_state.replan_explanation = ""

if "replan_agent" not in st.session_state:
    st.session_state.replan_agent = None

if "deadline_warnings" not in st.session_state:
    st.session_state.deadline_warnings = []

if "recurring_events" not in st.session_state:
    st.session_state.recurring_events = []

if "weekly_plan" not in st.session_state:
    st.session_state.weekly_plan = None


# ─────────────────────────────────────────────────────────────
# Helper: map date to DayOfWeek enum
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


def date_to_day(d: date) -> DayOfWeek:
    return DAY_MAP[d.weekday()]


def get_all_events_for_date(target_date: date) -> list[FixedEvent]:
    """Get all fixed events for a date: one-off events + expanded recurring events."""
    # One-off events for this date
    events = [
        entry["event"]
        for entry in st.session_state.timetable
        if entry["date"] == target_date
    ]
    # Expand recurring events for this single date
    if st.session_state.recurring_events:
        expanded = expand_recurring_events(
            st.session_state.recurring_events, target_date, target_date
        )
        for evt, _ in expanded:
            events.append(evt)
    return events


# ─────────────────────────────────────────────────────────────
# Sidebar: App info
# ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("About")
    st.markdown(
        "GapFlow detects free time between your lectures and fills it "
        "with prioritized study tasks using AI."
    )
    st.divider()
    st.markdown(f"**Today:** {date.today().strftime('%A, %B %d, %Y')}")
    st.markdown(f"**Time:** {datetime.now().strftime('%H:%M')}")
    st.divider()
    st.markdown(
        f"**Events:** {len(st.session_state.timetable)}  \n"
        f"**Tasks:** {len(st.session_state.tasks)}"
    )


# ─────────────────────────────────────────────────────────────
# Section 1: Timetable
# ─────────────────────────────────────────────────────────────
st.header("1. My Timetable")

with st.expander("Add a fixed event", expanded=len(st.session_state.timetable) == 0):
    col1, col2 = st.columns(2)
    with col1:
        event_name = st.text_input("Event name", placeholder="e.g. Linear Algebra Lecture")
        event_date = st.date_input("Date", value=date.today())
    with col2:
        event_start = st.time_input("Start time", value=time(9, 0))
        event_end = st.time_input("End time", value=time(10, 0))

    if st.button("Add Event", type="primary"):
        if event_name and event_end > event_start:
            event = FixedEvent(
                name=event_name,
                day=date_to_day(event_date),
                start_time=event_start,
                end_time=event_end,
            )
            # Store event with its date for scheduling
            st.session_state.timetable.append({
                "event": event,
                "date": event_date,
            })
            st.success(f"Added: {event_name} ({event_start.strftime('%H:%M')}–{event_end.strftime('%H:%M')})")
            st.rerun()
        else:
            st.error("Please enter a valid event name and ensure end time is after start time.")

# CSV Import
with st.expander("Import timetable from CSV"):
    st.caption("Upload a CSV file with columns: `event_name`, `date`, `start_time`, `end_time`")

    uploaded_file = st.file_uploader("Choose a CSV file", type=["csv"], key="csv_upload")

    if uploaded_file is not None:
        import csv
        import io

        try:
            content = uploaded_file.read().decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(content))

            # Normalize column names: strip BOM, whitespace, lowercase
            raw_fieldnames = reader.fieldnames or []
            normalized_map = {}
            for fn in raw_fieldnames:
                clean = fn.replace("\ufeff", "").strip().lower()
                normalized_map[fn] = clean

            normalized_fieldnames = set(normalized_map.values())

            # Validate columns
            required_cols = {"event_name", "date", "start_time", "end_time"}
            if not required_cols.issubset(normalized_fieldnames):
                missing = required_cols - normalized_fieldnames
                st.error(f"Missing required columns: {', '.join(missing)}")
            else:
                # Build reverse lookup: normalized name -> original name
                norm_to_orig = {}
                for orig, norm in normalized_map.items():
                    if norm in required_cols:
                        norm_to_orig[norm] = orig

                parsed_rows = []
                errors = []

                for row_num, row in enumerate(reader, start=2):  # row 2+ (header is row 1)
                    try:
                        name = row[norm_to_orig["event_name"]].strip()
                        if not name:
                            errors.append(f"Row {row_num}: empty event_name")
                            continue

                        # Parse date
                        evt_date = datetime.strptime(row[norm_to_orig["date"]].strip(), "%Y-%m-%d").date()

                        # Parse times
                        start_t = datetime.strptime(row[norm_to_orig["start_time"]].strip(), "%H:%M").time()
                        end_t = datetime.strptime(row[norm_to_orig["end_time"]].strip(), "%H:%M").time()

                        if end_t <= start_t:
                            errors.append(f"Row {row_num}: end_time must be after start_time ({name})")
                            continue

                        parsed_rows.append({
                            "name": name,
                            "date": evt_date,
                            "start_time": start_t,
                            "end_time": end_t,
                        })
                    except (ValueError, KeyError) as e:
                        errors.append(f"Row {row_num}: {e}")

                # Show errors
                if errors:
                    st.warning("Some rows have issues:")
                    for err in errors:
                        st.caption(f"  - {err}")

                # Show preview
                if parsed_rows:
                    st.markdown(f"**Preview: {len(parsed_rows)} valid events**")
                    preview_data = [
                        {
                            "Event": r["name"],
                            "Date": r["date"].strftime("%Y-%m-%d"),
                            "Start": r["start_time"].strftime("%H:%M"),
                            "End": r["end_time"].strftime("%H:%M"),
                        }
                        for r in parsed_rows
                    ]
                    st.dataframe(preview_data, use_container_width=True)

                    # Import button
                    if st.button("Import All Events", type="primary"):
                        imported = 0
                        skipped = 0

                        for row_data in parsed_rows:
                            # Check for duplicates
                            is_duplicate = any(
                                entry["event"].name == row_data["name"]
                                and entry["date"] == row_data["date"]
                                and entry["event"].start_time == row_data["start_time"]
                                and entry["event"].end_time == row_data["end_time"]
                                for entry in st.session_state.timetable
                            )
                            if is_duplicate:
                                skipped += 1
                                continue

                            event = FixedEvent(
                                name=row_data["name"],
                                day=date_to_day(row_data["date"]),
                                start_time=row_data["start_time"],
                                end_time=row_data["end_time"],
                            )
                            st.session_state.timetable.append({
                                "event": event,
                                "date": row_data["date"],
                            })
                            imported += 1

                        msg = f"{imported} event(s) imported successfully."
                        if skipped > 0:
                            msg += f" {skipped} duplicate(s) skipped."
                        st.success(msg)
                        st.rerun()
                else:
                    st.warning("No valid events found in the CSV.")

        except Exception as e:
            st.error(f"Error reading CSV: {e}")

# Recurring (Semester) CSV Import
with st.expander("Import semester timetable (recurring weekly events)"):
    st.caption("Upload a CSV with columns: `event_name`, `day_of_week`, `start_time`, `end_time`, `start_date`, `end_date`")

    recurring_file = st.file_uploader("Choose a semester CSV file", type=["csv"], key="recurring_csv_upload")

    if recurring_file is not None:
        import csv
        import io

        try:
            content = recurring_file.read().decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(content))

            # Normalize column names
            raw_fieldnames = reader.fieldnames or []
            normalized_map = {}
            for fn in raw_fieldnames:
                clean = fn.replace("\ufeff", "").strip().lower()
                normalized_map[fn] = clean

            normalized_fieldnames = set(normalized_map.values())

            required_cols = {"event_name", "day_of_week", "start_time", "end_time", "start_date", "end_date"}
            if not required_cols.issubset(normalized_fieldnames):
                missing = required_cols - normalized_fieldnames
                st.error(f"Missing required columns: {', '.join(missing)}")
            else:
                norm_to_orig = {}
                for orig, norm in normalized_map.items():
                    if norm in required_cols:
                        norm_to_orig[norm] = orig

                parsed_recurring = []
                errors = []

                for row_num, row in enumerate(reader, start=2):
                    try:
                        name = row[norm_to_orig["event_name"]].strip()
                        if not name:
                            errors.append(f"Row {row_num}: empty event_name")
                            continue

                        day_str = row[norm_to_orig["day_of_week"]].strip().lower()
                        if day_str not in DAY_NAME_TO_ENUM:
                            errors.append(f"Row {row_num}: invalid day_of_week '{day_str}' ({name})")
                            continue
                        day_enum = DAY_NAME_TO_ENUM[day_str]

                        start_t = datetime.strptime(row[norm_to_orig["start_time"]].strip(), "%H:%M").time()
                        end_t = datetime.strptime(row[norm_to_orig["end_time"]].strip(), "%H:%M").time()

                        if end_t <= start_t:
                            errors.append(f"Row {row_num}: end_time must be after start_time ({name})")
                            continue

                        s_date = datetime.strptime(row[norm_to_orig["start_date"]].strip(), "%Y-%m-%d").date()
                        e_date = datetime.strptime(row[norm_to_orig["end_date"]].strip(), "%Y-%m-%d").date()

                        if e_date <= s_date:
                            errors.append(f"Row {row_num}: end_date must be after start_date ({name})")
                            continue

                        parsed_recurring.append({
                            "name": name,
                            "day_of_week": day_enum,
                            "start_time": start_t,
                            "end_time": end_t,
                            "start_date": s_date,
                            "end_date": e_date,
                        })
                    except (ValueError, KeyError) as e:
                        errors.append(f"Row {row_num}: {e}")

                if errors:
                    st.warning("Some rows have issues:")
                    for err in errors:
                        st.caption(f"  - {err}")

                if parsed_recurring:
                    st.markdown(f"**Preview: {len(parsed_recurring)} recurring events**")
                    preview_data = [
                        {
                            "Event": r["name"],
                            "Day": r["day_of_week"].value,
                            "Time": f"{r['start_time'].strftime('%H:%M')}–{r['end_time'].strftime('%H:%M')}",
                            "Semester": f"{r['start_date']} to {r['end_date']}",
                        }
                        for r in parsed_recurring
                    ]
                    st.dataframe(preview_data, use_container_width=True)

                    if st.button("Import Recurring Events", type="primary"):
                        imported = 0
                        skipped = 0

                        for row_data in parsed_recurring:
                            # Check for duplicates
                            is_duplicate = any(
                                existing.name == row_data["name"]
                                and existing.day_of_week == row_data["day_of_week"]
                                and existing.start_time == row_data["start_time"]
                                and existing.end_time == row_data["end_time"]
                                for existing in st.session_state.recurring_events
                            )
                            if is_duplicate:
                                skipped += 1
                                continue

                            recurring_event = RecurringEvent(
                                name=row_data["name"],
                                day_of_week=row_data["day_of_week"],
                                start_time=row_data["start_time"],
                                end_time=row_data["end_time"],
                                start_date=row_data["start_date"],
                                end_date=row_data["end_date"],
                            )
                            st.session_state.recurring_events.append(recurring_event)
                            imported += 1

                        msg = f"{imported} recurring event(s) imported successfully."
                        if skipped > 0:
                            msg += f" {skipped} duplicate(s) skipped."
                        st.success(msg)
                        st.rerun()
                else:
                    st.warning("No valid recurring events found in the CSV.")

        except Exception as e:
            st.error(f"Error reading CSV: {e}")

# Display current timetable
if st.session_state.timetable:
    st.subheader("One-Off Events")
    for i, entry in enumerate(st.session_state.timetable):
        evt = entry["event"]
        evt_date = entry["date"]
        col1, col2 = st.columns([5, 1])
        with col1:
            st.markdown(
                f"**{evt.name}** — {evt_date.strftime('%a %b %d')} | "
                f"{evt.start_time.strftime('%H:%M')} – {evt.end_time.strftime('%H:%M')}"
            )
        with col2:
            if st.button("Remove", key=f"rm_event_{i}"):
                st.session_state.timetable.pop(i)
                st.rerun()

if st.session_state.recurring_events:
    st.subheader("Weekly Recurring Events")
    for i, rec in enumerate(st.session_state.recurring_events):
        col1, col2 = st.columns([5, 1])
        with col1:
            st.markdown(
                f"**{rec.name}** — Every {rec.day_of_week.value} | "
                f"{rec.start_time.strftime('%H:%M')} – {rec.end_time.strftime('%H:%M')} | "
                f"_{rec.start_date.strftime('%b %d')} – {rec.end_date.strftime('%b %d, %Y')}_"
            )
        with col2:
            if st.button("Remove", key=f"rm_recurring_{i}"):
                st.session_state.recurring_events.pop(i)
                st.rerun()

if not st.session_state.timetable and not st.session_state.recurring_events:
    st.info("No events yet. Add your lectures and fixed commitments above.")


# ─────────────────────────────────────────────────────────────
# Section 2: Tasks (Natural Language Input via Agent)
# ─────────────────────────────────────────────────────────────
st.header("2. My Tasks")

st.markdown("Describe your task in natural language and the AI will extract the details.")

task_input = st.text_area(
    "Task description",
    placeholder='e.g. "I have a database coursework due tomorrow at 5pm. It will take about 3 hours and it is very important."',
    height=80,
)

if st.button("Parse Task with AI", type="primary"):
    if task_input.strip():
        with st.spinner("Parsing with AI..."):
            try:
                # Create agent on first use
                if st.session_state.agent is None:
                    st.session_state.agent = create_agent()

                # Clear the tool's store before parsing
                clear_parsed_tasks()

                # Send to agent
                st.session_state.agent(task_input)

                # Retrieve the parsed Task object
                new_tasks = get_parsed_tasks()
                if new_tasks:
                    for task in new_tasks:
                        st.session_state.tasks.append(task)
                    st.success(f"Parsed: **{new_tasks[0].name}** (due {new_tasks[0].deadline.strftime('%b %d %H:%M')}, {new_tasks[0].estimated_minutes} min, importance {new_tasks[0].importance}/5)")
                    st.rerun()
                else:
                    st.warning("Agent did not return a structured task. Try rephrasing.")
            except Exception as e:
                st.error(f"Error connecting to AI: {e}")
    else:
        st.warning("Please enter a task description.")

# Batch task input
with st.expander("Add Multiple Tasks"):
    st.caption("Paste multiple tasks at once. The AI will identify and parse each one separately.")

    batch_input = st.text_area(
        "Describe all your tasks",
        placeholder=(
            "I need to finish my Algorithms assignment by Monday at 6pm. "
            "It will take about 4 hours and it is very important.\n\n"
            "I have a Database Systems quiz this Friday at 10am. "
            "I need about 2 hours to prepare and it is very important.\n\n"
            "I need to review Machine Learning notes by Thursday at 8pm. "
            "It will take around 90 minutes and is moderately important."
        ),
        height=180,
        key="batch_task_input",
    )

    if st.button("Parse & Add All Tasks", type="primary", key="batch_parse_btn"):
        if batch_input.strip():
            with st.spinner("Parsing tasks with AI... (this may take a moment)"):
                try:
                    parsed_tasks, _response = parse_batch_tasks(batch_input)

                    if parsed_tasks:
                        st.session_state.batch_preview = parsed_tasks
                        st.success(f"{len(parsed_tasks)} task(s) detected and parsed.")
                    else:
                        st.warning("No tasks could be parsed. Try rephrasing or separating them more clearly.")
                except Exception as e:
                    st.error(f"Error parsing tasks: {e}")
        else:
            st.warning("Please enter at least one task description.")

    # Show preview and confirm button
    if "batch_preview" in st.session_state and st.session_state.batch_preview:
        preview_tasks = st.session_state.batch_preview

        st.markdown(f"**Preview: {len(preview_tasks)} task(s) ready to add**")
        preview_data = [
            {
                "Task": t.name,
                "Deadline": t.deadline.strftime("%b %d %H:%M"),
                "Duration": f"{t.estimated_minutes} min",
                "Importance": f"{'★' * t.importance}{'☆' * (5 - t.importance)}",
            }
            for t in preview_tasks
        ]
        st.dataframe(preview_data, use_container_width=True)

        col_add, col_cancel = st.columns(2)
        with col_add:
            if st.button("Add All Tasks", type="primary", key="batch_confirm_btn"):
                import random

                added = 0
                skipped = 0

                for task in preview_tasks:
                    # Duplicate check: same normalized name + same deadline
                    is_duplicate = any(
                        existing.name.lower().strip() == task.name.lower().strip()
                        and existing.deadline == task.deadline
                        for existing in st.session_state.tasks
                    )
                    if is_duplicate:
                        skipped += 1
                        continue

                    st.session_state.tasks.append(task)
                    added += 1

                # Easter egg: humorous complaint based on batch size
                if added >= 8:
                    quips = [
                        "Eight tasks at once. We need to talk about your life choices.",
                        "This is no longer a task list. This is an incident.",
                        "GapFlow is calculating... and mildly concerned.",
                        "I asked for tasks, not your entire academic crisis.",
                    ]
                    st.toast(random.choice(quips))
                elif added >= 5:
                    quips = [
                        "That's a lot of tasks to casually drop on me.",
                        "You brought the chaos. I'll bring the schedule.",
                        "Five-plus tasks at once? Fine. Challenge accepted.",
                        "Your calendar just filed a complaint.",
                    ]
                    st.toast(random.choice(quips))
                elif added >= 3:
                    quips = [
                        "A productive week, apparently.",
                        "Okay, that's a respectable amount of work.",
                        "GapFlow has seen worse. Probably.",
                    ]
                    st.toast(random.choice(quips))

                # Bonus: if any new task is CRITICAL, override with urgency message
                if added >= 3:
                    today_date_check = date.today()
                    today_day_check = date_to_day(today_date_check)
                    now_check = datetime.now()
                    check_events = get_all_events_for_date(today_date_check)
                    check_slots = detect_free_slots(check_events, today_day_check, today_date_check, now=now_check)
                    for task in preview_tasks:
                        status = get_deadline_status(task, check_slots, now_check)
                        if status.status == "CRITICAL":
                            st.toast("Okay, jokes aside. One of these is actually urgent.")
                            break

                msg = f"{added} task(s) added successfully."
                if skipped > 0:
                    msg += f" {skipped} duplicate(s) skipped."
                st.success(msg)
                st.session_state.batch_preview = []
                st.rerun()

        with col_cancel:
            if st.button("Cancel", key="batch_cancel_btn"):
                st.session_state.batch_preview = []
                st.rerun()

# Display current tasks with priority scores and deadline status
if st.session_state.tasks:
    st.subheader("Task List")

    now = datetime.now()
    today_date = date.today()
    today_day = date_to_day(today_date)

    # Get free slots for deadline status calculation
    today_events_for_status = get_all_events_for_date(today_date)
    status_free_slots = detect_free_slots(today_events_for_status, today_day, today_date, now=now)

    ranked = rank_tasks(st.session_state.tasks, now)

    for i, (task, score) in enumerate(ranked):
        # Get deadline status
        deadline_info = get_deadline_status(task, status_free_slots, now)
        status_colors = {
            "CRITICAL": "🔴",
            "AT_RISK": "🟡",
            "ON_TRACK": "🟢",
            "FUTURE_NEEDS_PLANNING": "🔵",
        }
        status_icon = status_colors.get(deadline_info.status, "⚪")

        col1, col2, col3, col4 = st.columns([4, 1, 1, 1])
        with col1:
            st.markdown(f"**{task.name}**")
            st.caption(
                f"Due: {task.deadline.strftime('%b %d %H:%M')} | "
                f"Duration: {task.estimated_minutes} min | "
                f"Importance: {'★' * task.importance}{'☆' * (5 - task.importance)}"
            )
        with col2:
            st.metric("Priority", f"{score:.1f}")
        with col3:
            st.markdown(f"{status_icon} **{deadline_info.status.replace('_', ' ')}**")
            if deadline_info.status == "CRITICAL":
                st.caption(f"Shortfall: {deadline_info.shortfall_minutes} min")
            elif deadline_info.status == "AT_RISK":
                slack = deadline_info.available_minutes - deadline_info.needed_minutes
                st.caption(f"Slack: {slack} min")
        with col4:
            if st.button("Remove", key=f"rm_task_{task.id}"):
                st.session_state.tasks = [t for t in st.session_state.tasks if t.id != task.id]
                st.rerun()
else:
    st.info("No tasks yet. Describe a task above and let the AI parse it.")


# ─────────────────────────────────────────────────────────────
# Section 3: Smart Schedule (7-Day Rolling Planner)
# ─────────────────────────────────────────────────────────────
st.header("3. Smart Schedule")

if st.button("Generate My Weekly Plan", type="primary", disabled=not st.session_state.tasks):
    now = datetime.now()

    # Generate 7-day rolling plan
    weekly_plan = generate_weekly_plan(
        one_off_events=st.session_state.timetable,
        recurring_events=st.session_state.recurring_events,
        tasks=st.session_state.tasks,
        now=now,
        num_days=7,
    )
    st.session_state.weekly_plan = weekly_plan

    # Also update legacy state for compatibility with replan section
    if weekly_plan.days:
        today_plan = weekly_plan.days[0]
        st.session_state.schedule_blocks = today_plan.scheduled_blocks
        st.session_state.free_slots = today_plan.free_slots
        st.session_state.deadline_warnings = weekly_plan.warnings

# Display weekly plan
if st.session_state.weekly_plan is not None:
    plan: WeeklyPlan = st.session_state.weekly_plan

    tab_today, tab_week, tab_deadlines = st.tabs(["Today", "This Week", "Upcoming Deadlines"])

    # ─── TODAY TAB ───
    with tab_today:
        if plan.days:
            today_plan = plan.days[0]
            st.subheader(f"{today_plan.date.strftime('%A, %B %d')}")

            # Unified timeline
            timeline = []
            for evt in today_plan.fixed_events:
                timeline.append({
                    "start": evt.start_time,
                    "end": evt.end_time,
                    "label": evt.name,
                    "type": "fixed",
                })
            for block in today_plan.scheduled_blocks:
                timeline.append({
                    "start": block.start_time,
                    "end": block.end_time,
                    "label": f"{block.task_name} ({block.allocated_minutes} min)",
                    "type": "study",
                })
            timeline.sort(key=lambda x: x["start"])

            if timeline:
                for item in timeline:
                    time_str = f"{item['start'].strftime('%H:%M')} – {item['end'].strftime('%H:%M')}"
                    if item["type"] == "fixed":
                        st.markdown(f"🏫 **{time_str}** — {item['label']}")
                    else:
                        st.markdown(f"📖 **{time_str}** — {item['label']}")
            else:
                st.info("No events or study blocks for today.")

            # Today metrics
            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Today Free", f"{today_plan.total_free_minutes} min")
            with col2:
                st.metric("Today Study", f"{today_plan.total_study_minutes} min")

    # ─── THIS WEEK TAB ───
    with tab_week:
        st.subheader(f"{plan.start_date.strftime('%b %d')} – {plan.end_date.strftime('%b %d, %Y')}")

        for day_plan in plan.days:
            day_label = f"{day_plan.date.strftime('%A %b %d')}"
            study_min = day_plan.total_study_minutes

            with st.expander(f"**{day_label}** — {study_min} min study", expanded=(day_plan.date == plan.start_date)):
                timeline = []
                for evt in day_plan.fixed_events:
                    timeline.append((evt.start_time, evt.end_time, "fixed", evt.name))
                for block in day_plan.scheduled_blocks:
                    timeline.append((block.start_time, block.end_time, "study",
                                     f"{block.task_name} ({block.allocated_minutes} min)"))
                timeline.sort(key=lambda x: x[0])

                if timeline:
                    for start, end, typ, label in timeline:
                        time_str = f"{start.strftime('%H:%M')} – {end.strftime('%H:%M')}"
                        if typ == "fixed":
                            st.markdown(f"🏫 {time_str} — {label}")
                        else:
                            st.markdown(f"📖 {time_str} — {label}")
                else:
                    st.caption("No events or study blocks.")

        # Weekly metrics
        st.divider()
        st.subheader("Weekly Metrics")

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Free", f"{plan.total_free_minutes} min")
        with col2:
            st.metric("Study Planned", f"{plan.total_study_minutes} min")
        with col3:
            tasks_full = sum(
                1 for t in st.session_state.tasks
                if t.remaining_minutes > 0 and
                sum(b.allocated_minutes for b in plan.all_blocks if b.task_id == t.id) >= t.remaining_minutes
            )
            st.metric("Tasks Fully Scheduled", f"{tasks_full}/{len(st.session_state.tasks)}")
        with col4:
            st.metric("At Risk", f"{len(plan.warnings)}")

        # Workload by day chart data
        st.subheader("Workload by Day")
        day_data = []
        for dp in plan.days:
            day_data.append({
                "Day": dp.date.strftime("%a %d"),
                "Study (min)": dp.total_study_minutes,
            })
        st.bar_chart(data={d["Day"]: d["Study (min)"] for d in day_data})

    # ─── UPCOMING DEADLINES TAB ───
    with tab_deadlines:
        st.subheader("Upcoming Deadlines")

        active_tasks = [t for t in st.session_state.tasks if t.remaining_minutes > 0]
        active_tasks_sorted = sorted(active_tasks, key=lambda t: t.deadline)

        if active_tasks_sorted:
            for task in active_tasks_sorted:
                allocated = sum(b.allocated_minutes for b in plan.all_blocks if b.task_id == task.id)
                pct = min(100, int((allocated / task.remaining_minutes) * 100)) if task.remaining_minutes > 0 else 100

                # Determine status
                warning_match = next((w for w in plan.warnings if w.task.id == task.id), None)
                if warning_match:
                    status_icon = "🔴" if warning_match.status == "CRITICAL" else "🟡"
                    status_text = warning_match.status.replace("_", " ")
                else:
                    status_icon = "🟢"
                    status_text = "ON TRACK"

                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(f"{status_icon} **{task.name}**")
                    st.caption(
                        f"Due: {task.deadline.strftime('%a %b %d %H:%M')} | "
                        f"Remaining: {task.remaining_minutes} min | "
                        f"Importance: {'★' * task.importance}{'☆' * (5 - task.importance)} | "
                        f"Status: {status_text}"
                    )
                with col2:
                    st.progress(pct / 100, text=f"{pct}%")
        else:
            st.info("No pending tasks.")

    # Deadline warnings (shown outside tabs)
    if plan.warnings:
        st.subheader("Deadline Warnings")
        for w in plan.warnings:
            if w.status == "CRITICAL":
                st.error(
                    f"🔴 **CRITICAL — {w.task.name}**  \n"
                    f"Needs {w.needed_minutes} min, but only {w.available_minutes} min available before deadline.  \n"
                    f"Shortfall: **{w.shortfall_minutes} min**."
                )
            elif w.status == "AT_RISK":
                slack = w.available_minutes - w.needed_minutes
                st.warning(
                    f"🟡 **AT RISK — {w.task.name}**  \n"
                    f"Needs {w.needed_minutes} min, with {w.available_minutes} min available.  \n"
                    f"Slack: **{slack} min** — avoid further interruptions."
                )

elif not st.session_state.tasks:
    st.info("Add some tasks first, then generate your schedule.")
else:
    st.info("Click 'Generate My Weekly Plan' to create your 7-day study plan.")


# ─────────────────────────────────────────────────────────────
# Section 4: Replan My Day
# ─────────────────────────────────────────────────────────────
st.header("4. Replan My Day")

st.markdown(
    "Something changed? Describe it below and GapFlow will rebuild your schedule."
)
st.caption(
    'Examples: "I have a new meeting from 4pm to 5pm" · '
    '"I finished my flashcards early" · '
    '"My coursework now needs 2 more hours"'
)

replan_input = st.text_area(
    "What changed?",
    placeholder='e.g. "I suddenly have a meeting from 16:00 to 17:30"',
    height=80,
    key="replan_input",
)

replan_disabled = not st.session_state.schedule_blocks and not st.session_state.tasks
if st.button("Replan My Day", type="primary", disabled=replan_disabled):
    if replan_input.strip():
        with st.spinner("Understanding your change and replanning..."):
            try:
                # Save previous schedule for comparison
                st.session_state.previous_schedule = list(st.session_state.schedule_blocks)

                # Process the change through the replan agent
                actions, explanation = process_replan_request(
                    replan_input,
                    tasks=st.session_state.tasks,
                )

                if not actions:
                    st.warning("Could not understand the change. Try rephrasing.")
                else:
                    # Gather current state
                    today_date = date.today()
                    today_day = date_to_day(today_date)
                    now = datetime.now()

                    # Get events (as a mutable list for replanner, one-off + recurring)
                    today_events = get_all_events_for_date(today_date)

                    # Apply actions and regenerate
                    result = replan_schedule(
                        actions,
                        today_events,
                        st.session_state.tasks,
                        today_day,
                        today_date,
                        now,
                    )

                    # Update session state with new schedule
                    st.session_state.schedule_blocks = result["new_schedule"]
                    st.session_state.free_slots = result["new_free_slots"]

                    # If a new fixed event was added, persist it to timetable
                    for action in actions:
                        if action["action_type"] in ("ADD_FIXED_EVENT", "BLOCK_TIME"):
                            new_evt_name = action.get("event_name", "New Event")
                            if action["action_type"] == "BLOCK_TIME":
                                new_evt_name = f"[Blocked] {new_evt_name}"
                            try:
                                start_t = time(*[int(x) for x in action["start_time"].split(":")])
                                end_t = time(*[int(x) for x in action["end_time"].split(":")])
                                new_event = FixedEvent(
                                    name=new_evt_name,
                                    day=today_day,
                                    start_time=start_t,
                                    end_time=end_t,
                                )
                                st.session_state.timetable.append({
                                    "event": new_event,
                                    "date": today_date,
                                })
                            except Exception:
                                pass

                    # Store explanation
                    st.session_state.replan_explanation = explanation

                    # Regenerate weekly plan with updated state
                    weekly_plan = generate_weekly_plan(
                        one_off_events=st.session_state.timetable,
                        recurring_events=st.session_state.recurring_events,
                        tasks=st.session_state.tasks,
                        now=now,
                        num_days=7,
                    )
                    st.session_state.weekly_plan = weekly_plan

                    st.success("Schedule updated!")
                    st.rerun()

            except Exception as e:
                st.error(f"Error during replanning: {e}")
    else:
        st.warning("Please describe what changed.")

# Display replan results (previous vs new + explanation)
if st.session_state.replan_explanation:
    st.subheader("What Changed")

    col_prev, col_new = st.columns(2)

    with col_prev:
        st.markdown("**Previous Schedule:**")
        if st.session_state.previous_schedule:
            for block in sorted(st.session_state.previous_schedule, key=lambda b: b.start_time):
                st.markdown(
                    f"📖 {block.start_time.strftime('%H:%M')} – "
                    f"{block.end_time.strftime('%H:%M')} — "
                    f"{block.task_name} ({block.allocated_minutes} min)"
                )
        else:
            st.caption("No previous schedule.")

    with col_new:
        st.markdown("**New Schedule:**")
        if st.session_state.schedule_blocks:
            for block in sorted(st.session_state.schedule_blocks, key=lambda b: b.start_time):
                st.markdown(
                    f"📖 {block.start_time.strftime('%H:%M')} – "
                    f"{block.end_time.strftime('%H:%M')} — "
                    f"{block.task_name} ({block.allocated_minutes} min)"
                )
        else:
            st.caption("No study blocks scheduled.")

    st.divider()
    st.markdown("**AI Explanation:**")
    st.info(st.session_state.replan_explanation)

elif replan_disabled:
    st.info("Generate a schedule first (Section 3), then you can replan.")
