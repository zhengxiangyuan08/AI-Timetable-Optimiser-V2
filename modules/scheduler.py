
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


def to_minutes(value):
    parsed = datetime.strptime(value, "%H:%M")
    return parsed.hour * 60 + parsed.minute


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

        for previous, current in zip(lessons, lessons[1:]):
            if to_minutes(current["start"]) < to_minutes(previous["end"]):
                conflicts.append(
                    f"{day}: {previous['name']} overlaps with "
                    f"{current['name']}"
                )

    return conflicts


def generate_schedule(
    classes,
    tasks,
    earliest_start,
    latest_end,
    daily_limit
):
    occupied = {day: set() for day in DAYS}

    # Mark fixed class times as unavailable.
    for lesson in classes:
        if lesson["day"] not in occupied:
            continue

        start = to_minutes(lesson["start"])
        end = to_minutes(lesson["end"])

        for slot in range(start, end, 30):
            occupied[lesson["day"]].add(slot)

    # Reserve lunch time.
    for day in DAYS:
        occupied[day].update(
            range(12 * 60, 13 * 60, 30)
        )

    # Sort tasks by deadline, priority and duration.
    task_list = sorted(
        [dict(task) for task in tasks],
        key=lambda x: (
            DAYS.index(x["deadline"]),
            PRIORITY_ORDER[x["priority"]],
            -x["duration"]
        )
    )

    daily_used = {day: 0 for day in DAYS}

    output = []
    unscheduled = []

    for task in task_list:
        remaining = int(task["duration"])
        deadline_index = DAYS.index(task["deadline"])

        for day in DAYS[:deadline_index + 1]:

            hour = earliest_start

            while (
                hour < latest_end
                and remaining > 0
                and daily_used[day] < daily_limit
            ):

                slot_start = hour * 60

                slots = [
                    slot_start,
                    slot_start + 30
                ]

                if (
                    slot_start + 60 <= latest_end * 60
                    and all(
                        s not in occupied[day]
                        for s in slots
                    )
                ):

                    output.append({
                        "Day": day,
                        "Time": (
                            f"{hour:02d}:00-"
                            f"{hour+1:02d}:00"
                        ),
                        "Task": task["name"],
                        "Hours": 1,
                        "Priority": task["priority"]
                    })

                    occupied[day].update(slots)
                    daily_used[day] += 1
                    remaining -= 1

                hour += 1

            if remaining == 0:
                break

        if remaining:
            unscheduled.append({
                "name": task["name"],
                "remaining": remaining
            })

    output.sort(
        key=lambda x: (
            DAYS.index(x["Day"]),
            x["Time"]
        )
    )

    return {
        "items": output,
        "unscheduled": unscheduled,
        "class_conflicts": check_class_conflicts(classes)
    }
