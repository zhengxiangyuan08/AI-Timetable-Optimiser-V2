from datetime import datetime

DAYS = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday"
]

PRIORITY_ORDER = {
    "High": 0,
    "Medium": 1,
    "Low": 2
}

SLOT_MINUTES = 30


def to_minutes(value):
    parsed = datetime.strptime(value, "%H:%M")
    return parsed.hour * 60 + parsed.minute


def format_time(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def format_hours(minutes):
    return round(minutes / 60, 2)


def overlaps(start1, end1, start2, end2):
    return start1 < end2 and start2 < end1


def check_class_conflicts(classes):
    conflicts = []
    by_day = {}

    for item in classes:
        by_day.setdefault(item["day"], []).append(item)

    for day, lessons in by_day.items():
        lessons = sorted(
            lessons,
            key=lambda x: to_minutes(x["start"])
        )

        for i in range(len(lessons)):
            for j in range(i + 1, len(lessons)):
                previous = lessons[i]
                current = lessons[j]

                if to_minutes(current["start"]) < to_minutes(previous["end"]):
                    conflicts.append(
                        f"{day}: {previous['name']} overlaps with "
                        f"{current['name']}"
                    )

    return conflicts


def validate_inputs(
    classes,
    tasks,
    earliest_start,
    latest_end,
    daily_limit
):
    if earliest_start >= latest_end:
        raise ValueError(
            "Latest end time must be later than earliest start time."
        )

    if daily_limit <= 0:
        raise ValueError(
            "Daily limit must be greater than zero."
        )

    for lesson in classes:
        if lesson["day"] not in DAYS:
            raise ValueError(f"Invalid class day: {lesson['day']}")

        start = to_minutes(lesson["start"])
        end = to_minutes(lesson["end"])

        if start >= end:
            raise ValueError(f"Invalid class time: {lesson['name']}")

    for task in tasks:
        if task.get("deadline") not in DAYS:
            raise ValueError(
                f"Invalid deadline: {task.get('name', 'Unknown task')}"
            )

        if task.get("priority") not in PRIORITY_ORDER:
            raise ValueError(
                f"Invalid priority: {task.get('name', 'Unknown task')}"
            )

        duration = float(task.get("duration", 0))
        completed = float(task.get("completed_hours", 0))

        if duration <= 0:
            raise ValueError(
                f"Task duration must be positive: {task['name']}"
            )

        if completed < 0 or completed > duration:
            raise ValueError(
                f"Invalid completed hours: {task['name']}"
            )

        if abs(duration * 2 - round(duration * 2)) > 1e-8:
            raise ValueError(
                f"Task duration must use 0.5-hour increments: "
                f"{task['name']}"
            )

        if abs(completed * 2 - round(completed * 2)) > 1e-8:
            raise ValueError(
                f"Completed hours must use 0.5-hour increments: "
                f"{task['name']}"
            )


def get_free_runs(occupied, start, end):
    runs = []
    current_run = []

    for slot in range(start, end, SLOT_MINUTES):
        if slot not in occupied:
            current_run.append(slot)
        else:
            if current_run:
                runs.append(current_run)
                current_run = []

    if current_run:
        runs.append(current_run)

    return runs


def generate_schedule(
    classes,
    tasks,
    earliest_start,
    latest_end,
    daily_limit,
    existing_schedule=None
):
    """
    Generate a timetable for remaining task hours.

    Existing valid blocks are retained first when possible.
    Completed hours are not scheduled again.
    """

    validate_inputs(
        classes,
        tasks,
        earliest_start,
        latest_end,
        daily_limit
    )

    start_minutes = earliest_start * 60
    end_minutes = latest_end * 60
    daily_capacity = int(daily_limit * 60 / SLOT_MINUTES)

    occupied = {day: set() for day in DAYS}
    daily_used = {day: 0 for day in DAYS}

    # Reserve fixed classes.
    for lesson in classes:
        day = lesson["day"]
        lesson_start = to_minutes(lesson["start"])
        lesson_end = to_minutes(lesson["end"])

        for slot in range(0, 24 * 60, SLOT_MINUTES):
            if (
                slot < lesson_end
                and slot + SLOT_MINUTES > lesson_start
            ):
                occupied[day].add(slot)

    # Reserve lunch.
    for day in DAYS:
        occupied[day].update(
            range(12 * 60, 13 * 60, SLOT_MINUTES)
        )

    task_by_id = {
        str(task["id"]): task
        for task in tasks
        if task.get("id") is not None
    }

    remaining_slots = {}

    for task in tasks:
        task_id = str(task.get("id", task["name"]))
        total_slots = int(round(float(task["duration"]) * 2))
        completed_slots = int(
            round(float(task.get("completed_hours", 0)) * 2)
        )
        remaining_slots[task_id] = max(
            0,
            total_slots - completed_slots
        )

    output = []

    # First try to retain old valid blocks.
    if existing_schedule and isinstance(existing_schedule, dict):
        old_items = existing_schedule.get("items", [])

        for old in old_items:
            task_id = old.get("task_id")

            if task_id is None:
                # V2.5 compatibility: match only when the name is unique.
                matches = [
                    task for task in tasks
                    if task["name"] == old.get("Task")
                ]
                if len(matches) == 1:
                    task_id = str(matches[0].get("id", matches[0]["name"]))

            task_id = str(task_id) if task_id is not None else None

            if task_id not in task_by_id:
                continue

            task = task_by_id[task_id]

            if remaining_slots.get(task_id, 0) <= 0:
                continue

            day = old.get("Day")

            if day not in DAYS:
                continue

            try:
                old_start_text, old_end_text = old["Time"].split("-")
                block_start = to_minutes(old_start_text)
                block_end = to_minutes(old_end_text)
            except (ValueError, KeyError, TypeError):
                continue

            if (
                block_start % SLOT_MINUTES != 0
                or block_end % SLOT_MINUTES != 0
                or block_start < start_minutes
                or block_end > end_minutes
                or block_start >= block_end
            ):
                continue

            if block_start < 13 * 60 and block_end > 12 * 60:
                continue

            if DAYS.index(day) > DAYS.index(task["deadline"]):
                continue

            block_slots = int(
                (block_end - block_start) / SLOT_MINUTES
            )

            keep_slots = min(
                block_slots,
                remaining_slots[task_id]
            )

            # Retain only a continuous prefix of the old block.
            retained_end = block_start + keep_slots * SLOT_MINUTES

            if daily_used[day] + keep_slots > daily_capacity:
                continue

            slots = list(
                range(block_start, retained_end, SLOT_MINUTES)
            )

            if any(slot in occupied[day] for slot in slots):
                continue

            for slot in slots:
                occupied[day].add(slot)

            daily_used[day] += keep_slots
            remaining_slots[task_id] -= keep_slots

            output.append({
                "task_id": task_id,
                "Day": day,
                "Time": (
                    f"{format_time(block_start)}-"
                    f"{format_time(retained_end)}"
                ),
                "Task": task["name"],
                "Hours": format_hours(
                    keep_slots * SLOT_MINUTES
                ),
                "Priority": task["priority"]
            })

    # Schedule all remaining work.
    task_list = sorted(
        tasks,
        key=lambda task: (
            DAYS.index(task["deadline"]),
            PRIORITY_ORDER[task["priority"]],
            -float(task["duration"])
        )
    )

    unscheduled = []

    for task in task_list:
        task_id = str(task.get("id", task["name"]))
        remaining = remaining_slots.get(task_id, 0)

        deadline_index = DAYS.index(task["deadline"])

        for day in DAYS[:deadline_index + 1]:
            while (
                remaining > 0
                and daily_used[day] < daily_capacity
            ):
                available_capacity = (
                    daily_capacity - daily_used[day]
                )

                free_runs = get_free_runs(
                    occupied[day],
                    start_minutes,
                    end_minutes
                )

                if not free_runs:
                    break

                chosen_run = max(
                    free_runs,
                    key=len
                )

                block_size = min(
                    remaining,
                    len(chosen_run),
                    available_capacity
                )

                if block_size <= 0:
                    break

                block_start = chosen_run[0]
                block_end = (
                    block_start + block_size * SLOT_MINUTES
                )

                for slot in range(
                    block_start,
                    block_end,
                    SLOT_MINUTES
                ):
                    occupied[day].add(slot)

                daily_used[day] += block_size
                remaining -= block_size

                output.append({
                    "task_id": task_id,
                    "Day": day,
                    "Time": (
                        f"{format_time(block_start)}-"
                        f"{format_time(block_end)}"
                    ),
                    "Task": task["name"],
                    "Hours": format_hours(
                        block_size * SLOT_MINUTES
                    ),
                    "Priority": task["priority"]
                })

            if remaining == 0:
                break

        if remaining > 0:
            unscheduled.append({
                "task_id": task_id,
                "name": task["name"],
                "remaining": format_hours(
                    remaining * SLOT_MINUTES
                ),
                "reason": (
                    "Not enough available time before the deadline."
                )
            })

    output.sort(
        key=lambda item: (
            DAYS.index(item["Day"]),
            item["Time"]
        )
    )

    return {
        "items": output,
        "unscheduled": unscheduled,
        "class_conflicts": check_class_conflicts(classes)
    }