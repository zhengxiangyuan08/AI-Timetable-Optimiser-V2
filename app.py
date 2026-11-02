
import streamlit as st
import pandas as pd

from modules.scheduler import generate_schedule

st.set_page_config(
    page_title="AI Timetable Optimiser",
    page_icon="📅",
    layout="wide"
)

st.title("📅 AI Timetable Optimiser")
st.caption(
    "Version 1.0 — Rule-based prototype. "
    "This version does not connect to an AI API."
)

DAYS = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday"
]

if "classes" not in st.session_state:
    st.session_state.classes = []

if "tasks" not in st.session_state:
    st.session_state.tasks = []

if "schedule" not in st.session_state:
    st.session_state.schedule = None


tab1, tab2, tab3, tab4 = st.tabs([
    "1. Fixed classes",
    "2. Study tasks",
    "3. Preferences & generate",
    "4. Results"
])


# TAB 1: FIXED CLASSES

with tab1:

    st.subheader("Add your fixed classes")

    with st.form("class_form", clear_on_submit=True):

        c1, c2, c3, c4 = st.columns(4)

        day = c1.selectbox("Day", DAYS)

        name = c2.text_input(
            "Class name",
            placeholder="e.g. Mathematics"
        )

        start = c3.time_input(
            "Start time",
            value=pd.to_datetime("09:00").time()
        )

        end = c4.time_input(
            "End time",
            value=pd.to_datetime("11:00").time()
        )

        submitted = st.form_submit_button("Add class")

        if submitted:

            if not name.strip():
                st.error("Please enter a class name.")

            elif start >= end:
                st.error("End time must be later than start time.")

            else:

                st.session_state.classes.append({
                    "day": day,
                    "name": name.strip(),
                    "start": start.strftime("%H:%M"),
                    "end": end.strftime("%H:%M")
                })

                st.success("Class added.")

    if st.session_state.classes:

        st.dataframe(
            pd.DataFrame(st.session_state.classes),
            use_container_width=True,
            hide_index=True
        )

        if st.button("Clear all classes"):
            st.session_state.classes = []
            st.rerun()

    else:
        st.info("No fixed classes added yet.")


# TAB 2: STUDY TASKS

with tab2:

    st.subheader("Add study tasks")

    with st.form("task_form", clear_on_submit=True):

        t1, t2 = st.columns(2)

        task_name = t1.text_input(
            "Task name",
            placeholder="e.g. Programming assignment"
        )

        duration = t2.number_input(
            "Estimated hours",
            min_value=1,
            max_value=40,
            value=2,
            step=1
        )

        t3, t4 = st.columns(2)

        deadline = t3.selectbox(
            "Complete by",
            DAYS
        )

        priority = t4.selectbox(
            "Priority",
            ["High", "Medium", "Low"]
        )

        submitted_task = st.form_submit_button("Add task")

        if submitted_task:

            if not task_name.strip():
                st.error("Please enter a task name.")

            else:

                st.session_state.tasks.append({
                    "name": task_name.strip(),
                    "duration": int(duration),
                    "deadline": deadline,
                    "priority": priority
                })

                st.success("Task added.")

    if st.session_state.tasks:

        st.dataframe(
            pd.DataFrame(st.session_state.tasks),
            use_container_width=True,
            hide_index=True
        )

        if st.button("Clear all tasks"):
            st.session_state.tasks = []
            st.session_state.schedule = None
            st.rerun()

    else:
        st.info("No study tasks added yet.")


# TAB 3: PREFERENCES

with tab3:

    st.subheader("Set your scheduling preferences")

    p1, p2, p3 = st.columns(3)

    earliest = p1.selectbox(
        "Earliest start",
        list(range(6, 13)),
        index=3,
        format_func=lambda x: f"{x:02d}:00"
    )

    latest = p2.selectbox(
        "Latest finish",
        list(range(16, 24)),
        index=5,
        format_func=lambda x: f"{x:02d}:00"
    )

    daily_limit = p3.number_input(
        "Maximum study hours per day",
        min_value=1,
        max_value=12,
        value=4
    )

    if earliest >= latest:
        st.warning(
            "Latest finish must be later than earliest start."
        )

    if st.button(
        "Generate timetable",
        type="primary",
        disabled=(
            not st.session_state.tasks
            or earliest >= latest
        )
    ):

        st.session_state.schedule = generate_schedule(
            st.session_state.classes,
            st.session_state.tasks,
            earliest,
            latest,
            int(daily_limit)
        )

        st.success(
            "Timetable generated. Open the Results tab."
        )

    st.caption(
        "The prototype schedules one-hour study blocks, "
        "Monday to Friday, and reserves 12:00–13:00 for lunch."
    )


# TAB 4: RESULTS

with tab4:

    st.subheader("Your timetable")

    if st.session_state.schedule is None:

        st.info(
            "Add classes and tasks, then generate a timetable."
        )

    else:

        result = st.session_state.schedule

        if result["items"]:

            df = pd.DataFrame(result["items"])

            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True
            )

            st.download_button(
                "Download timetable as CSV",
                data=df.to_csv(
                    index=False
                ).encode("utf-8-sig"),
                file_name="my_timetable.csv",
                mime="text/csv"
            )

            daily = (
                df.groupby("Day")["Hours"]
                .sum()
                .reindex(DAYS, fill_value=0)
            )

            st.bar_chart(daily)

        else:

            st.warning(
                "No tasks could be scheduled with the current settings."
            )

        if result["unscheduled"]:

            st.warning(
                "Some tasks could not be fully scheduled:"
            )

            for item in result["unscheduled"]:

                st.write(
                    f"- **{item['name']}**: "
                    f"{item['remaining']} hour(s) remain unscheduled."
                )

        if result["class_conflicts"]:

            st.error(
                "There are overlaps between fixed classes:"
            )

            for conflict in result["class_conflicts"]:
                st.write(f"- {conflict}")

        else:

            st.success(
                "No overlaps detected between fixed classes."
            )
