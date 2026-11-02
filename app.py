import streamlit as st
import pandas as pd
import json
import uuid

from datetime import datetime, time
from modules.scheduler import (
    generate_schedule,
    DAYS,
    PRIORITY_ORDER
)

st.set_page_config(
    page_title="AI Timetable Optimiser V2.8",
    page_icon="📅",
    layout="wide"
)

st.title("📅 AI Timetable Optimiser")
st.caption(
    "Version 2.8 — Smart Rescheduling, Progress Tracking & Advanced Analytics"
)

PRIORITIES = ["High", "Medium", "Low"]
DURATION_OPTIONS = [x / 2 for x in range(1, 81)]
SLOT_MINUTES = 30


# ==========================================
# SESSION STATE
# ==========================================

defaults = {
    "classes": [],
    "tasks": [],
    "schedule": None,
    "earliest": 9,
    "latest": 21,
    "daily_limit": 4,
    "ui_revision": 0,
    "backup_message": None
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


def new_id():
    return str(uuid.uuid4())


def normalize_tasks(tasks):
    """Add V2.8 task fields to old tasks."""
    normalized = []

    for original in tasks:
        task = dict(original)

        if not task.get("id"):
            task["id"] = new_id()

        task["duration"] = float(task["duration"])
        task["completed_hours"] = float(
            task.get("completed_hours", 0)
        )

        task["completed_hours"] = max(
            0.0,
            min(task["duration"], task["completed_hours"])
        )

        normalized.append(task)

    return normalized


def task_status(task):
    completed = float(task.get("completed_hours", 0))
    duration = float(task["duration"])

    if completed >= duration:
        return "Completed"
    if completed > 0:
        return "In Progress"
    return "Not Started"


def remaining_hours(task):
    return max(
        0.0,
        float(task["duration"]) -
        float(task.get("completed_hours", 0))
    )


def invalidate_schedule():
    st.session_state.schedule = None


def to_minutes(value):
    parsed = datetime.strptime(value, "%H:%M")
    return parsed.hour * 60 + parsed.minute


def format_time(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def overlaps(start1, end1, start2, end2):
    return start1 < end2 and start2 < end1


def get_task_by_id(task_id):
    for task in st.session_state.tasks:
        if str(task.get("id")) == str(task_id):
            return task
    return None


def task_for_schedule_item(item):
    task_id = item.get("task_id")

    if task_id:
        return get_task_by_id(task_id)

    matches = [
        task for task in st.session_state.tasks
        if task["name"] == item.get("Task")
    ]

    return matches[0] if len(matches) == 1 else None


# ==========================================
# BACKUP / RESTORE
# ==========================================

def build_backup():
    return {
        "app": "AI Timetable Optimiser",
        "version": "2.8",
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "classes": st.session_state.classes,
        "tasks": st.session_state.tasks,
        "preferences": {
            "earliest": st.session_state.earliest,
            "latest": st.session_state.latest,
            "daily_limit": st.session_state.daily_limit
        },
        "schedule": st.session_state.schedule
    }


def validate_backup(data):
    if not isinstance(data, dict):
        raise ValueError("Invalid JSON structure.")

    if data.get("app") != "AI Timetable Optimiser":
        raise ValueError("This is not an AI Timetable Optimiser backup.")

    if not isinstance(data.get("classes"), list):
        raise ValueError("Invalid classes data.")

    if not isinstance(data.get("tasks"), list):
        raise ValueError("Invalid tasks data.")

    preferences = data.get("preferences")

    if not isinstance(preferences, dict):
        raise ValueError("Invalid preferences data.")

    for lesson in data["classes"]:
        if not isinstance(lesson, dict):
            raise ValueError("Invalid fixed class.")

        if not all(
            key in lesson
            for key in ["day", "name", "start", "end"]
        ):
            raise ValueError("A fixed class is missing required fields.")

        if lesson["day"] not in DAYS:
            raise ValueError("Invalid class day.")

        start = datetime.strptime(lesson["start"], "%H:%M")
        end = datetime.strptime(lesson["end"], "%H:%M")

        if start >= end:
            raise ValueError("Invalid fixed class time.")

    for task in data["tasks"]:
        if not isinstance(task, dict):
            raise ValueError("Invalid study task.")

        required = ["name", "duration", "deadline", "priority"]

        if not all(key in task for key in required):
            raise ValueError("A study task is missing required fields.")

        if task["deadline"] not in DAYS:
            raise ValueError("Invalid task deadline.")

        if task["priority"] not in PRIORITIES:
            raise ValueError("Invalid task priority.")

        duration = float(task["duration"])
        completed = float(task.get("completed_hours", 0))

        if duration <= 0 or completed < 0 or completed > duration:
            raise ValueError("Invalid task duration or progress.")

        if abs(duration * 2 - round(duration * 2)) > 1e-8:
            raise ValueError("Task duration must use 30-minute increments.")

        if abs(completed * 2 - round(completed * 2)) > 1e-8:
            raise ValueError("Completed hours must use 30-minute increments.")

    earliest = int(preferences["earliest"])
    latest = int(preferences["latest"])
    daily_limit = int(preferences["daily_limit"])

    if not 6 <= earliest <= 12:
        raise ValueError("Invalid earliest start time.")

    if not 16 <= latest <= 23 or earliest >= latest:
        raise ValueError("Invalid latest finish time.")

    if not 1 <= daily_limit <= 12:
        raise ValueError("Invalid daily study limit.")

    schedule = data.get("schedule")

    if schedule is not None:
        if not isinstance(schedule, dict):
            raise ValueError("Invalid schedule data.")

        for key in ["items", "unscheduled", "class_conflicts"]:
            if not isinstance(schedule.get(key), list):
                raise ValueError("Invalid schedule lists.")

        for item in schedule["items"]:
            if not isinstance(item, dict):
                raise ValueError("Invalid scheduled item.")

            for key in ["Day", "Time", "Task", "Hours", "Priority"]:
                if key not in item:
                    raise ValueError("Incomplete scheduled item.")

            if item["Day"] not in DAYS:
                raise ValueError("Invalid scheduled day.")

            if item["Priority"] not in PRIORITIES:
                raise ValueError("Invalid scheduled priority.")

            start_text, end_text = item["Time"].split("-")
            start = datetime.strptime(start_text, "%H:%M")
            end = datetime.strptime(end_text, "%H:%M")

            if start >= end or float(item["Hours"]) <= 0:
                raise ValueError("Invalid scheduled time or duration.")

    return True


def restore_backup(data):
    validate_backup(data)

    st.session_state.classes = data["classes"]
    st.session_state.tasks = normalize_tasks(data["tasks"])

    preferences = data["preferences"]

    st.session_state.earliest = int(preferences["earliest"])
    st.session_state.latest = int(preferences["latest"])
    st.session_state.daily_limit = int(preferences["daily_limit"])

    schedule = data.get("schedule")

    if schedule is not None:
        schedule = dict(schedule)
        schedule["items"] = [
            dict(item) for item in schedule.get("items", [])
        ]

        # Add task IDs to old V2.5 schedule entries where possible.
        for item in schedule["items"]:
            if item.get("task_id"):
                continue

            matches = [
                task for task in st.session_state.tasks
                if task["name"] == item.get("Task")
            ]

            if len(matches) == 1:
                item["task_id"] = matches[0]["id"]

        st.session_state.schedule = schedule
    else:
        st.session_state.schedule = None

    st.session_state.ui_revision += 1


# ==========================================
# SCHEDULING
# ==========================================

def run_scheduling():
    st.session_state.tasks = normalize_tasks(
        st.session_state.tasks
    )

    active_tasks = [
        task for task in st.session_state.tasks
        if remaining_hours(task) > 0
    ]

    if not active_tasks:
        st.session_state.schedule = {
            "items": [],
            "unscheduled": [],
            "class_conflicts": []
        }
        return

    st.session_state.schedule = generate_schedule(
        st.session_state.classes,
        active_tasks,
        int(st.session_state.earliest),
        int(st.session_state.latest),
        int(st.session_state.daily_limit),
        existing_schedule=st.session_state.schedule
    )


# ==========================================
# MANUAL ADJUSTMENT
# ==========================================

def validate_manual_change(index, new_day, new_start):
    items = st.session_state.schedule["items"]
    item = items[index]

    task = task_for_schedule_item(item)

    if task is None:
        return "The task linked to this timetable block could not be found."

    if task_status(task) == "Completed":
        return "Completed tasks cannot be moved."

    duration_minutes = int(round(float(item["Hours"]) * 60))
    start_minutes = to_minutes(new_start)
    end_minutes = start_minutes + duration_minutes

    if start_minutes % SLOT_MINUTES != 0:
        return "Start time must be on a 30-minute boundary."

    if start_minutes < st.session_state.earliest * 60:
        return "The task starts before your allowed start time."

    if end_minutes > st.session_state.latest * 60:
        return "The task ends after your allowed finish time."

    if start_minutes < 13 * 60 and end_minutes > 12 * 60:
        return "The task overlaps with the reserved lunch break."

    if DAYS.index(new_day) > DAYS.index(task["deadline"]):
        return "This change would place the task after its deadline."

    for lesson in st.session_state.classes:
        if lesson["day"] != new_day:
            continue

        if overlaps(
            start_minutes,
            end_minutes,
            to_minutes(lesson["start"]),
            to_minutes(lesson["end"])
        ):
            return f"Conflict with fixed class: {lesson['name']}."

    for i, other in enumerate(items):
        if i == index or other["Day"] != new_day:
            continue

        other_start, other_end = other["Time"].split("-")

        if overlaps(
            start_minutes,
            end_minutes,
            to_minutes(other_start),
            to_minutes(other_end)
        ):
            return f"Conflict with another study block: {other['Task']}."

    daily_total = duration_minutes / 60

    for i, other in enumerate(items):
        if i != index and other["Day"] == new_day:
            daily_total += float(other["Hours"])

    if daily_total > st.session_state.daily_limit:
        return (
            f"Daily study limit exceeded: "
            f"{daily_total:.1f} hours."
        )

    return None


# ==========================================
# TOP SUMMARY
# ==========================================

total_tasks = len(st.session_state.tasks)
completed_tasks = sum(
    1 for task in st.session_state.tasks
    if task_status(task) == "Completed"
)

total_hours = sum(
    float(task["duration"])
    for task in st.session_state.tasks
)

completed_hours = sum(
    float(task.get("completed_hours", 0))
    for task in st.session_state.tasks
)

overall_progress = (
    completed_hours / total_hours * 100
    if total_hours else 0
)

summary1, summary2, summary3, summary4 = st.columns(4)

summary1.metric("Study tasks", total_tasks)
summary2.metric("Completed tasks", completed_tasks)
summary3.metric("Completed hours", f"{completed_hours:.1f} h")
summary4.metric("Overall progress", f"{overall_progress:.1f}%")

st.progress(min(overall_progress / 100, 1.0))

st.divider()


# ==========================================
# TABS
# ==========================================

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "1. Fixed classes",
    "2. Study tasks",
    "3. Preferences & generate",
    "4. Results & analysis",
    "5. Manual adjustment",
    "6. Save & Load",
    "7. Progress Tracking"
])


# ==========================================
# TAB 1: FIXED CLASSES
# ==========================================

with tab1:
    st.subheader("Add a new fixed class")

    with st.form("class_form", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns(4)

        day = c1.selectbox("Day", DAYS)
        class_name = c2.text_input(
            "Class name",
            placeholder="e.g. Mathematics"
        )
        start = c3.time_input("Start time", value=time(9, 0))
        end = c4.time_input("End time", value=time(11, 0))

        submitted = st.form_submit_button("Add class")

        if submitted:
            if not class_name.strip():
                st.error("Please enter a class name.")
            elif start >= end:
                st.error("End time must be later than start time.")
            else:
                st.session_state.classes.append({
                    "day": day,
                    "name": class_name.strip(),
                    "start": start.strftime("%H:%M"),
                    "end": end.strftime("%H:%M")
                })
                st.success("Class added. Generate the timetable again to apply the change.")
                st.rerun()

    st.divider()
    st.subheader("Your fixed classes")

    if not st.session_state.classes:
        st.info("No fixed classes added yet.")
    else:
        st.dataframe(
            pd.DataFrame(st.session_state.classes),
            use_container_width=True,
            hide_index=True
        )

        revision = st.session_state.ui_revision

        selected_class_index = st.selectbox(
            "Select a class to manage",
            options=list(range(len(st.session_state.classes))),
            format_func=lambda i: (
                f"{st.session_state.classes[i]['name']} "
                f"({st.session_state.classes[i]['day']}, "
                f"{st.session_state.classes[i]['start']}-"
                f"{st.session_state.classes[i]['end']})"
            ),
            key=f"class_select_{revision}"
        )

        selected_class = st.session_state.classes[selected_class_index]

        with st.form(f"edit_class_form_{revision}"):
            new_class_name = st.text_input(
                "Class name",
                value=selected_class["name"]
            )

            ec1, ec2, ec3 = st.columns(3)

            new_class_day = ec1.selectbox(
                "Day",
                DAYS,
                index=DAYS.index(selected_class["day"])
            )

            new_class_start = ec2.time_input(
                "Start time",
                value=datetime.strptime(
                    selected_class["start"], "%H:%M"
                ).time()
            )

            new_class_end = ec3.time_input(
                "End time",
                value=datetime.strptime(
                    selected_class["end"], "%H:%M"
                ).time()
            )

            save_class = st.form_submit_button("Save class changes")

            if save_class:
                if not new_class_name.strip():
                    st.error("Class name cannot be empty.")
                elif new_class_start >= new_class_end:
                    st.error("End time must be later than start time.")
                else:
                    st.session_state.classes[selected_class_index] = {
                        "day": new_class_day,
                        "name": new_class_name.strip(),
                        "start": new_class_start.strftime("%H:%M"),
                        "end": new_class_end.strftime("%H:%M")
                    }
                    st.session_state.ui_revision += 1
                    st.success("Class updated.")
                    st.rerun()

        if st.button("Delete selected class", key=f"delete_class_{revision}"):
            st.session_state.classes.pop(selected_class_index)
            st.session_state.ui_revision += 1
            st.rerun()

        if st.button("Clear all classes", key=f"clear_classes_{revision}"):
            st.session_state.classes = []
            st.session_state.ui_revision += 1
            st.rerun()


# ==========================================
# TAB 2: STUDY TASKS
# ==========================================

with tab2:
    st.subheader("Add a new study task")

    with st.form("task_form", clear_on_submit=True):
        t1, t2 = st.columns(2)

        task_name = t1.text_input(
            "Task name",
            placeholder="e.g. Programming assignment"
        )

        duration = t2.selectbox(
            "Estimated hours",
            DURATION_OPTIONS,
            index=3,
            format_func=lambda x: f"{x:.1f} hours"
        )

        t3, t4 = st.columns(2)

        deadline = t3.selectbox("Complete by", DAYS)
        priority = t4.selectbox("Priority", PRIORITIES)

        submitted_task = st.form_submit_button("Add task")

        if submitted_task:
            if not task_name.strip():
                st.error("Please enter a task name.")
            else:
                st.session_state.tasks.append({
                    "id": new_id(),
                    "name": task_name.strip(),
                    "duration": float(duration),
                    "completed_hours": 0.0,
                    "deadline": deadline,
                    "priority": priority
                })
                st.success("Task added. Generate the timetable to include it.")
                st.rerun()

    st.divider()
    st.subheader("Task management")

    if not st.session_state.tasks:
        st.info("No study tasks available.")
    else:
        task_table = []

        for task in st.session_state.tasks:
            task_table.append({
                "Task": task["name"],
                "Estimated hours": task["duration"],
                "Completed hours": task.get("completed_hours", 0),
                "Remaining hours": remaining_hours(task),
                "Deadline": task["deadline"],
                "Priority": task["priority"],
                "Status": task_status(task)
            })

        st.dataframe(
            pd.DataFrame(task_table),
            use_container_width=True,
            hide_index=True
        )

        revision = st.session_state.ui_revision

        selected_index = st.selectbox(
            "Select a task to manage",
            options=list(range(len(st.session_state.tasks))),
            format_func=lambda i: (
                f"{st.session_state.tasks[i]['name']} "
                f"({st.session_state.tasks[i]['duration']:.1f} hours)"
            ),
            key=f"task_select_{revision}"
        )

        selected_task = st.session_state.tasks[selected_index]

        duration_index = int(
            round(float(selected_task["duration"]) * 2)
        ) - 1

        duration_index = max(
            0,
            min(duration_index, len(DURATION_OPTIONS) - 1)
        )

        with st.form(f"edit_task_form_{revision}"):
            new_name = st.text_input(
                "Task name",
                value=selected_task["name"]
            )

            new_duration = st.selectbox(
                "Estimated hours",
                DURATION_OPTIONS,
                index=duration_index,
                format_func=lambda x: f"{x:.1f} hours"
            )

            new_deadline = st.selectbox(
                "Complete by",
                DAYS,
                index=DAYS.index(selected_task["deadline"])
            )

            new_priority = st.selectbox(
                "Priority",
                PRIORITIES,
                index=PRIORITIES.index(selected_task["priority"])
            )

            save_task = st.form_submit_button("Save task changes")

            if save_task:
                completed = float(
                    selected_task.get("completed_hours", 0)
                )

                if not new_name.strip():
                    st.error("Task name cannot be empty.")
                elif new_duration < completed:
                    st.error(
                        "Estimated duration cannot be less than "
                        "the hours already completed."
                    )
                else:
                    selected_task.update({
                        "name": new_name.strip(),
                        "duration": float(new_duration),
                        "deadline": new_deadline,
                        "priority": new_priority
                    })
                    st.session_state.ui_revision += 1
                    st.success("Task updated.")
                    st.rerun()

        if st.button("Delete selected task", key=f"delete_task_{revision}"):
            task_id = str(selected_task["id"])
            st.session_state.tasks.pop(selected_index)

            if st.session_state.schedule:
                st.session_state.schedule["items"] = [
                    item for item in st.session_state.schedule["items"]
                    if str(item.get("task_id")) != task_id
                ]

            st.session_state.ui_revision += 1
            st.rerun()


# ==========================================
# TAB 3: PREFERENCES & GENERATE
# ==========================================

with tab3:
    st.subheader("Scheduling preferences")

    revision = st.session_state.ui_revision

    p1, p2, p3 = st.columns(3)

    earliest = p1.selectbox(
        "Earliest start",
        list(range(6, 13)),
        index=list(range(6, 13)).index(
            st.session_state.earliest
        ),
        format_func=lambda x: f"{x:02d}:00",
        key=f"earliest_widget_{revision}"
    )

    latest = p2.selectbox(
        "Latest finish",
        list(range(16, 24)),
        index=list(range(16, 24)).index(
            st.session_state.latest
        ),
        format_func=lambda x: f"{x:02d}:00",
        key=f"latest_widget_{revision}"
    )

    daily_limit = p3.number_input(
        "Maximum self-study hours per day",
        min_value=1,
        max_value=12,
        value=int(st.session_state.daily_limit),
        step=1,
        key=f"daily_limit_widget_{revision}"
    )

    st.session_state.earliest = earliest
    st.session_state.latest = latest
    st.session_state.daily_limit = int(daily_limit)

    st.caption(
        "Study tasks use 30-minute blocks. "
        "Lunch time (12:00–13:00) is reserved."
    )

    if earliest >= latest:
        st.warning("Latest finish must be later than earliest start time.")

    st.divider()

    st.markdown("#### Generate or update your timetable")

    st.write(
        "The scheduler first attempts to retain valid existing study blocks. "
        "It then allocates remaining task hours."
    )

    if st.button(
        "Generate / Smart reschedule",
        type="primary",
        disabled=(
            not st.session_state.tasks
            or earliest >= latest
        )
    ):
        try:
            run_scheduling()
            st.success("Timetable generated successfully.")
            st.rerun()
        except (ValueError, KeyError, TypeError) as error:
            st.error(f"Unable to generate timetable: {error}")

    if st.session_state.schedule is not None:
        st.info(
            "A timetable is available. If you change classes, tasks or "
            "preferences, generate it again to apply those changes."
        )


# ==========================================
# TAB 4: RESULTS & ANALYSIS
# ==========================================

with tab4:
    st.subheader("Your timetable")

    if st.session_state.schedule is None:
        st.info(
            "Add classes and tasks, then generate a timetable."
        )
    else:
        result = st.session_state.schedule

        st.subheader("🗓️ Weekly Calendar")

        calendar_columns = st.columns(5)

        for day_index, day in enumerate(DAYS):
            with calendar_columns[day_index]:
                st.markdown(f"**{day}**")

                events = []

                for lesson in st.session_state.classes:
                    if lesson["day"] == day:
                        events.append({
                            "type": "Class",
                            "name": lesson["name"],
                            "time": (
                                f"{lesson['start']}-{lesson['end']}"
                            ),
                            "sort_time": lesson["start"]
                        })

                for item in result["items"]:
                    if item["Day"] == day:
                        events.append({
                            "type": "Study",
                            "name": item["Task"],
                            "time": item["Time"],
                            "sort_time": item["Time"].split("-")[0],
                            "priority": item["Priority"]
                        })

                events.sort(key=lambda x: x["sort_time"])

                if not events:
                    st.info("No activities")
                else:
                    for event in events:
                        with st.container(border=True):
                            if event["type"] == "Class":
                                st.markdown("📘 **CLASS**")
                            else:
                                st.markdown("📝 **STUDY TASK**")

                            st.write(event["name"])
                            st.caption(event["time"])

                            if event["type"] == "Study":
                                st.caption(
                                    f"Priority: {event['priority']}"
                                )

        st.divider()
        st.subheader("📊 Overall Results Analysis")

        total_required = sum(
            float(task["duration"])
            for task in st.session_state.tasks
        )

        total_scheduled = sum(
            float(item["Hours"])
            for item in result["items"]
        )

        total_remaining = sum(
            float(item["remaining"])
            for item in result["unscheduled"]
        )

        total_actual_completed = sum(
            float(task.get("completed_hours", 0))
            for task in st.session_state.tasks
        )

        coverage = (
            total_scheduled / sum(
                remaining_hours(task)
                for task in st.session_state.tasks
            ) * 100
            if sum(remaining_hours(task) for task in st.session_state.tasks) > 0
            else 100
        )

        metrics = st.columns(5)

        metrics[0].metric("Total task hours", f"{total_required:.1f} h")
        metrics[1].metric("Actually completed", f"{total_actual_completed:.1f} h")
        metrics[2].metric("Currently scheduled", f"{total_scheduled:.1f} h")
        metrics[3].metric("Unscheduled remaining", f"{total_remaining:.1f} h")
        metrics[4].metric("Remaining coverage", f"{coverage:.1f}%")

        st.caption(
            "Remaining coverage measures how much outstanding work has "
            "been allocated. It is not the same as actual completion."
        )

        st.divider()
        st.subheader("📅 Daily Workload Analysis")

        if result["items"]:
            df = pd.DataFrame(result["items"])
            daily_hours = (
                df.groupby("Day")["Hours"]
                .sum()
                .reindex(DAYS, fill_value=0)
            )
        else:
            df = pd.DataFrame(
                columns=[
                    "Day", "Time", "Task", "Hours", "Priority"
                ]
            )
            daily_hours = pd.Series(0.0, index=DAYS)

        d1, d2, d3 = st.columns(3)

        d1.metric(
            "Average daily scheduled",
            f"{daily_hours.mean():.1f} h"
        )

        d2.metric(
            "Busiest day",
            daily_hours.idxmax(),
            f"{daily_hours.max():.1f} hours"
        )

        d3.metric(
            "Lightest day",
            daily_hours.idxmin(),
            f"{daily_hours.min():.1f} hours"
        )

        st.bar_chart(daily_hours)

        st.divider()
        st.subheader("🎯 Priority Analysis")

        priority_rows = []

        for priority_name in PRIORITIES:
            required = sum(
                remaining_hours(task)
                for task in st.session_state.tasks
                if task["priority"] == priority_name
            )

            scheduled = sum(
                float(item["Hours"])
                for item in result["items"]
                if item["Priority"] == priority_name
            )

            remaining = max(required - scheduled, 0)

            rate = (
                scheduled / required * 100
                if required > 0 else 100
            )

            priority_rows.append({
                "Priority": priority_name,
                "Remaining required hours": round(required, 1),
                "Scheduled hours": round(scheduled, 1),
                "Unscheduled hours": round(remaining, 1),
                "Coverage": f"{rate:.1f}%"
            })

        priority_df = pd.DataFrame(priority_rows)

        st.dataframe(
            priority_df,
            use_container_width=True,
            hide_index=True
        )

        st.bar_chart(
            priority_df.set_index("Priority")[["Scheduled hours"]]
        )

        st.divider()
        st.subheader("Scheduled Task Details")

        if result["items"]:
            st.dataframe(
                df.drop(columns=["task_id"], errors="ignore"),
                use_container_width=True,
                hide_index=True
            )

            st.download_button(
                "Download timetable as CSV",
                data=df.drop(
                    columns=["task_id"],
                    errors="ignore"
                ).to_csv(index=False).encode("utf-8-sig"),
                file_name="my_timetable.csv",
                mime="text/csv"
            )
        else:
            st.info("No remaining study blocks are scheduled.")

        st.divider()
        st.subheader("⚠️ Unscheduled Tasks")

        if result["unscheduled"]:
            unscheduled_df = pd.DataFrame(
                result["unscheduled"]
            ).rename(columns={
                "name": "Task",
                "remaining": "Remaining hours",
                "reason": "Reason"
            })

            st.dataframe(
                unscheduled_df.drop(
                    columns=["task_id"],
                    errors="ignore"
                ),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.success("All remaining task hours have been allocated.")

        st.divider()
        st.subheader("Schedule Validation")

        if result["class_conflicts"]:
            st.error("Overlaps were detected between fixed classes.")
            for conflict in result["class_conflicts"]:
                st.write(f"- {conflict}")
        else:
            st.success("No overlaps detected between fixed classes.")


# ==========================================
# TAB 5: MANUAL ADJUSTMENT
# ==========================================

with tab5:
    st.subheader("Manual Timetable Adjustment")

    if st.session_state.schedule is None:
        st.info("Generate a timetable first.")
    elif not st.session_state.schedule["items"]:
        st.info("There are no scheduled study blocks to adjust.")
    else:
        items = st.session_state.schedule["items"]
        revision = st.session_state.ui_revision

        selected_block = st.selectbox(
            "Select a scheduled study block",
            options=list(range(len(items))),
            format_func=lambda i: (
                f"{items[i]['Task']} — {items[i]['Day']} "
                f"{items[i]['Time']} ({items[i]['Hours']} hours)"
            ),
            key=f"selected_block_{revision}"
        )

        current_item = items[selected_block]
        linked_task = task_for_schedule_item(current_item)

        if linked_task is None:
            st.error("Could not identify the task for this block.")
        elif task_status(linked_task) == "Completed":
            st.info("This task is completed and cannot be moved.")
        else:
            st.markdown("#### Current arrangement")

            st.write(f"**Task:** {current_item['Task']}")
            st.write(
                f"**Current time:** {current_item['Day']} "
                f"{current_item['Time']}"
            )
            st.write(f"**Duration:** {current_item['Hours']} hours")

            st.divider()
            st.markdown("#### New arrangement")

            new_day = st.selectbox(
                "Move to day",
                DAYS,
                index=DAYS.index(current_item["Day"]),
                key=f"manual_day_{revision}"
            )

            old_start = current_item["Time"].split("-")[0]

            start_options = [
                format_time(x)
                for x in range(
                    st.session_state.earliest * 60,
                    st.session_state.latest * 60,
                    SLOT_MINUTES
                )
            ]

            start_index = (
                start_options.index(old_start)
                if old_start in start_options else 0
            )

            new_start = st.selectbox(
                "New start time",
                start_options,
                index=start_index,
                key=f"manual_start_{revision}"
            )

            duration_minutes = int(
                round(float(current_item["Hours"]) * 60)
            )

            new_end = format_time(
                to_minutes(new_start) + duration_minutes
            )

            st.caption(
                f"New time block: {new_start}–{new_end}"
            )

            if st.button(
                "Validate and save adjustment",
                type="primary"
            ):
                error = validate_manual_change(
                    selected_block,
                    new_day,
                    new_start
                )

                if error:
                    st.error(error)
                else:
                    current_item["Day"] = new_day
                    current_item["Time"] = f"{new_start}-{new_end}"

                    current_item["task_id"] = str(
                        linked_task["id"]
                    )

                    st.session_state.schedule["items"].sort(
                        key=lambda x: (
                            DAYS.index(x["Day"]),
                            x["Time"]
                        )
                    )

                    st.success("Manual adjustment saved.")
                    st.rerun()

        st.caption(
            "Manual changes apply to the current timetable. "
            "A later smart rescheduling operation may move a block "
            "if it no longer fits the updated constraints."
        )


# ==========================================
# TAB 6: SAVE & LOAD
# ==========================================

with tab6:
    st.subheader("💾 Save your timetable")

    st.write(
        "Export fixed classes, study tasks, progress, preferences "
        "and the current timetable into a JSON backup."
    )

    backup_json = json.dumps(
        build_backup(),
        ensure_ascii=False,
        indent=4
    )

    st.download_button(
        "Download timetable backup (JSON)",
        data=backup_json.encode("utf-8"),
        file_name="ai_timetable_backup_v2.8.json",
        mime="application/json",
        type="primary"
    )

    st.divider()
    st.subheader("📂 Load an existing timetable")

    uploaded_file = st.file_uploader(
        "Upload a V2.5 or V2.8 JSON backup",
        type=["json"],
        key=f"backup_uploader_{st.session_state.ui_revision}"
    )

    if uploaded_file is not None:
        try:
            uploaded_data = json.loads(
                uploaded_file.getvalue().decode("utf-8")
            )

            validate_backup(uploaded_data)

            st.success("Backup file passed validation.")

            preview1, preview2, preview3 = st.columns(3)

            preview1.metric(
                "Fixed classes",
                len(uploaded_data["classes"])
            )

            preview2.metric(
                "Study tasks",
                len(uploaded_data["tasks"])
            )

            preview3.metric(
                "Saved schedule",
                "Yes" if uploaded_data.get("schedule") else "No"
            )

            st.caption(
                f"Backup version: {uploaded_data.get('version', 'Unknown')}"
            )

            st.caption(
                f"Saved at: {uploaded_data.get('saved_at', 'Unknown')}"
            )

            st.warning(
                "Importing this backup will replace your current "
                "classes, tasks, preferences, progress and timetable."
            )

            confirm_import = st.checkbox(
                "I understand that importing will replace my current data.",
                key=f"confirm_import_{st.session_state.ui_revision}"
            )

            if st.button(
                "Confirm import",
                type="primary",
                disabled=not confirm_import,
                key=f"confirm_import_button_{st.session_state.ui_revision}"
            ):
                try:
                    restore_backup(uploaded_data)
                    st.session_state.backup_message = (
                        "Backup imported successfully."
                    )
                    st.rerun()
                except (ValueError, KeyError, TypeError) as error:
                    st.error(f"Unable to import backup: {error}")

        except (
            json.JSONDecodeError,
            UnicodeDecodeError,
            ValueError,
            KeyError,
            TypeError,
            AttributeError
        ) as error:
            st.error(f"Unable to read backup: {error}")

    if st.session_state.backup_message:
        st.success(st.session_state.backup_message)
        st.session_state.backup_message = None


# ==========================================
# TAB 7: PROGRESS TRACKING
# ==========================================

with tab7:
    st.subheader("📈 Study Progress Tracking")

    if not st.session_state.tasks:
        st.info("Add study tasks first.")
    else:
        st.write(
            "Record the hours you have actually completed. "
            "The remaining hours will be used by smart rescheduling."
        )

        progress_rows = []

        for task in st.session_state.tasks:
            duration = float(task["duration"])
            completed = float(task.get("completed_hours", 0))
            remaining = remaining_hours(task)
            percent = (
                completed / duration * 100
                if duration else 0
            )

            progress_rows.append({
                "Task": task["name"],
                "Priority": task["priority"],
                "Deadline": task["deadline"],
                "Estimated hours": duration,
                "Completed hours": completed,
                "Remaining hours": remaining,
                "Progress": f"{percent:.0f}%",
                "Status": task_status(task)
            })

        st.dataframe(
            pd.DataFrame(progress_rows),
            use_container_width=True,
            hide_index=True
        )

        st.divider()
        st.markdown("#### Update task progress")

        revision = st.session_state.ui_revision

        selected_progress_task = st.selectbox(
            "Select a task",
            options=list(range(len(st.session_state.tasks))),
            format_func=lambda i: (
                f"{st.session_state.tasks[i]['name']} "
                f"— {task_status(st.session_state.tasks[i])}"
            ),
            key=f"progress_task_{revision}"
        )

        selected_task = st.session_state.tasks[selected_progress_task]

        st.write(
            f"Estimated duration: **{selected_task['duration']:.1f} hours**"
        )

        current_completed = float(
            selected_task.get("completed_hours", 0)
        )

        completed_input = st.number_input(
            "Actual completed hours",
            min_value=0.0,
            max_value=float(selected_task["duration"]),
            value=current_completed,
            step=0.5,
            key=f"completed_hours_{revision}"
        )

        if st.button(
            "Save progress",
            type="primary",
            key=f"save_progress_{revision}"
        ):
            if abs(completed_input * 2 - round(completed_input * 2)) > 1e-8:
                st.error("Please use 30-minute increments.")
            else:
                selected_task["completed_hours"] = float(
                    completed_input
                )

                try:
                    run_scheduling()
                    st.session_state.ui_revision += 1
                    st.success(
                        "Progress saved and remaining work rescheduled."
                    )
                    st.rerun()
                except (ValueError, KeyError, TypeError) as error:
                    st.error(
                        f"Progress saved, but rescheduling failed: {error}"
                    )

        st.divider()
        st.markdown("#### Progress overview")

        total_estimated = sum(
            float(task["duration"])
            for task in st.session_state.tasks
        )

        total_done = sum(
            float(task.get("completed_hours", 0))
            for task in st.session_state.tasks
        )

        total_left = max(total_estimated - total_done, 0)

        progress_percent = (
            total_done / total_estimated * 100
            if total_estimated else 0
        )

        a, b, c = st.columns(3)

        a.metric("Estimated hours", f"{total_estimated:.1f} h")
        b.metric("Completed hours", f"{total_done:.1f} h")
        c.metric("Remaining hours", f"{total_left:.1f} h")

        st.metric(
            "Overall completion",
            f"{progress_percent:.1f}%"
        )

        st.progress(min(progress_percent / 100, 1.0))

        status_counts = {
            "Not Started": 0,
            "In Progress": 0,
            "Completed": 0
        }

        for task in st.session_state.tasks:
            status_counts[task_status(task)] += 1

        st.markdown("#### Task status distribution")

        st.dataframe(
            pd.DataFrame([
                {"Status": status, "Number of tasks": count}
                for status, count in status_counts.items()
            ]),
            use_container_width=True,
            hide_index=True
        )

        st.bar_chart(
            pd.Series(
                status_counts,
                name="Number of tasks"
            )
        )