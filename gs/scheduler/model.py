import enum
import re
import itertools
from datetime import datetime, timedelta, timezone
from string import ascii_lowercase
from typing import Optional, List

from sortedcontainers import SortedList

from porthouse.gs.tracking.orbit_tracker import OrbitTracker
from porthouse.gs.tracking.utils import parse_time


class TaskStatus(enum.Enum):
    """ Task states """
    NOT_SCHEDULED = 0
    SCHEDULED = 1
    ONGOING = 2
    EXECUTED = 3
    CANCELLED = 4


class Task:
    (STORAGE_MAIN, STORAGE_MISC) = range(2)

    def __init__(self):
        self.task_name = None
        self.start_time = None
        self.end_time = None
        self.rotators = None
        self.auto_scheduled = True
        self.status = TaskStatus.SCHEDULED
        self.process_name = None

        # if provided, overrides corresponding process fields when sent with the task.start event
        self.process_overrides = {}

        # used to determine where to save the task, parameter itself not saved
        self.storage = Task.STORAGE_MAIN

    def to_dict(self):
        return {
            "task_name": self.task_name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "rotators": self.rotators,
            "auto_scheduled": self.auto_scheduled,
            "status": self.status.name,
            "process_name": self.process_name,
            "process_overrides": self.process_overrides,
        }

    @staticmethod
    def from_dict(data, storage=STORAGE_MAIN):
        task = Task()
        task.task_name = data.get("task_name", "unnamed task")
        task.start_time = parse_time(data["start_time"]).utc_datetime()
        task.end_time = parse_time(data["end_time"]).utc_datetime()
        task.rotators = data["rotators"]
        task.auto_scheduled = data.get("auto_scheduled", False)
        task.status = TaskStatus[data.get("status", "SCHEDULED")]
        task.process_name = data.get("process_name", "unnamed process")
        task.process_overrides = data.get("process_overrides", {})
        task.storage = storage
        return task

    def get_task_data(self, process: 'Process' = None):
        task_data = {} if process is None else process.to_dict()
        task_data.update(self.process_overrides)
        task_data.update(self.to_dict())
        task_data.pop('process_overrides', None)
        task_data.setdefault('process_name', self.process_name)
        return task_data

    def apply_limits(self, process: 'Process', time_used_s: int = 0):
        process_data = self.get_task_data(process)

        if process_data['duration'] is not None and isinstance(process_data['duration'], str) and \
                process_data['duration'].strip():
            limits = process_data['duration'].split("|")    # min|Optional[max]
            if len(limits) > 1 and limits[1].strip():
                self.end_time = self.start_time + timedelta(seconds=int(limits[1])) - timedelta(seconds=int(time_used_s))

    def is_valid(self, process: 'Process'):
        process_data = self.get_task_data(process)
        valid = self.end_time > self.start_time

        if valid and process_data['duration'] is not None:
            min_duration = None
            if isinstance(process_data['duration'], str) and process_data['duration'].strip():
                min_duration, *_ = process_data['duration'].split("|")    # min|Optional[max]
                min_duration = int(min_duration)
            elif isinstance(process_data['duration'], (int, float)):
                min_duration = int(process_data['duration'])
            if min_duration is not None:
                valid &= self.end_time - self.start_time >= timedelta(seconds=min_duration)

        if valid and process_data['daily_windows'] is not None and len(process_data['daily_windows']) > 0:
            # TODO: limit duration instead of filter, possibly split into multiple tasks
            limits = [w.split("|") for w in process_data['daily_windows'] if "|" in w]
            within_limits = False
            for start, end in limits:
                start = datetime.strptime(start, "%H:%M:%S")
                end = datetime.strptime(end, "%H:%M:%S")
                if start.time() <= self.start_time.time() <= end.time() \
                        and start.time() <= self.end_time.time() <= end.time():
                    within_limits = True
            valid &= within_limits

        if valid and process_data['date_ranges'] is not None and len(process_data['date_ranges']) > 0:
            # TODO: limit duration instead of filter, possibly split into multiple tasks
            limits = [w.split("|") for w in process_data['date_ranges'] if "|" in w]
            within_limits = False
            for start, end in limits:
                start = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc) if start.strip() else \
                    datetime.now(timezone.utc)
                end = datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc) if end.strip() else None
                if start <= self.start_time and (end is None or self.start_time <= end) \
                        and start <= self.end_time and (end is None or self.end_time <= end):
                    within_limits = True
            valid &= within_limits

        return valid

    def get_process_name(self):
        return self.process_overrides.get("process_name", self.process_name) or "unnamed"

    def copy(self):
        task = Task()
        task.task_name = self.task_name
        task.start_time = self.start_time
        task.end_time = self.end_time
        task.rotators = self.rotators.copy()
        task.auto_scheduled = self.auto_scheduled
        task.status = self.status
        task.process_name = self.process_name
        task.process_overrides = self.process_overrides.copy()
        task.storage = self.storage
        return task

    def split(self, holes):
        """ Splits task into multiple tasks by holes. """
        if len(holes) == 0:
            return [self]

        # merge overlapping holes so that following logic is simpler to understand
        holes = sorted(holes)       # sort first on start time, then end time
        merged_holes = []
        for hole in holes:
            if not merged_holes or merged_holes[-1][1] <= hole[0]:
                merged_holes.append(hole)
            else:
                merged_holes[-1] = (merged_holes[-1][0], hole[1])

        tasks = []
        for hole_start_time, hole_end_time in merged_holes:
            if hole_start_time <= self.start_time:
                # shift start of remaining task to the end of the hole
                self.start_time = hole_end_time + timedelta(seconds=1)
            else:
                # split period between the start of remaining task and the start of the hole into a new task
                # remaining task is shortened so that it starts at the start of the hole
                task = self.copy()
                task.end_time = hole_start_time - timedelta(seconds=1)
                self.start_time = hole_end_time + timedelta(seconds=1)
                tasks.append(task)

            if hole_end_time >= self.end_time:
                # if a hole ends after the end of the remaining task, we have reached the end, adjust remaining task
                # end time to the start of the hole, make a copy of it
                self.end_time = hole_start_time - timedelta(seconds=1)
                tasks.append(self.copy())
                break

        # update task names if ended up with multiple tasks
        if len(tasks) > 1:
            for lbl, task in zip(iter_all_strings(), tasks):
                task.task_name += " " + lbl

        return tasks

    def is_outside(self, other: 'Task'):
        """ Checks if self is outside other task. """
        if not set(other.rotators).intersection(self.rotators):
            return True
        return self.end_time <= other.start_time or other.end_time <= self.start_time

    def is_inside(self, other: 'Task'):
        """ Checks if self is inside other task. """
        if not set(other.rotators).intersection(self.rotators):
            return False
        return other.start_time <= self.start_time and self.end_time <= other.end_time

    def is_encompassing(self, other: 'Task'):
        """ Checks if self begins before and ends after other task. """
        if not set(other.rotators).intersection(self.rotators):
            return False
        return self.start_time <= other.start_time and self.end_time >= other.end_time

    def is_reaching_into(self, other: 'Task'):
        """ Checks if self begins before and ends inside other task. """
        if not set(other.rotators).intersection(self.rotators):
            return False
        return self.start_time < other.start_time < self.end_time < other.end_time

    def is_reaching_out(self, other: 'Task'):
        """ Checks if self begins inside and ends after other task. """
        if not set(other.rotators).intersection(self.rotators):
            return False
        return other.start_time <= self.start_time <= other.end_time <= self.end_time

    def __hash__(self):
        return hash((self.task_name,))

    def __str__(self):
        return f"{self.task_name} ({datetime.isoformat(self.start_time)} - {datetime.isoformat(self.end_time)})"

    def __repr__(self):
        return str(self)


class Process:
    (STORAGE_MAIN, STORAGE_MISC) = range(2)

    def __init__(self):
        self.process_name = None    # needs to be unique
        self.priority = None   # low value means high priority, can also be negative
        self.enabled = None    # low value means high priority, can also be negative
        self.rotators = None   # uhf, sband, uhf-b

        self.tracker = None    # orbit, gnss, misc, other?
        self.target = None     # tle name, gnss specs, ephem specs
        self.preaos_time = None     # in seconds
        self.min_elevation = None   # in degrees
        self.min_max_elevation = None   # in degrees
        self.sun_max_elevation = None   # in degrees, set to e.g. -20 for dark observation conditions
        self.obj_sunlit = None      # True|False|None, should tracked object be sunlit
        self.duration = None        # in seconds "min|max", max is optional
        self.daily_windows = None   # list of "HH:MM:SS|HH:MM:SS" [start|end], both are required
        self.date_ranges = None     # list of "YYYY-MM-DD|YYYY-MM-DD" [start|end], both are optional

        self.extra = {}    # stores extra data that is passed in the task.start event
        self.storage = Process.STORAGE_MAIN    # storage type

    def to_dict(self):
        return dict(process_name=self.process_name,
                    priority=self.priority,
                    enabled=self.enabled,
                    rotators=self.rotators,
                    tracker=self.tracker,
                    target=self.target,
                    preaos_time=self.preaos_time,
                    min_elevation=self.min_elevation,
                    min_max_elevation=self.min_max_elevation,
                    sun_max_elevation=self.sun_max_elevation,
                    obj_sunlit=self.obj_sunlit,
                    duration=self.duration,
                    daily_windows=self.daily_windows,
                    date_ranges=self.date_ranges,
                    **self.extra)

    @staticmethod
    def from_dict(data, storage=STORAGE_MAIN):
        process = Process()
        process.process_name = data["process_name"]
        process.priority = data.get("priority", 100)
        process.enabled = data.get("enabled", True)
        process.rotators = data["rotators"]
        process.tracker = data["tracker"]
        process.target = data["target"]
        process.preaos_time = data.get("preaos_time", OrbitTracker.DEFAULT_PREAOS_TIME)
        process.min_elevation = data.get("min_elevation", 0)
        process.min_max_elevation = data.get("min_max_elevation", 0)
        process.sun_max_elevation = data.get("sun_max_elevation", None)
        process.obj_sunlit = data.get("obj_sunlit", None)
        process.duration = data.get("duration", None)
        process.daily_windows = data.get("daily_windows", None)
        process.date_ranges = data.get("date_ranges", None)
        process.extra = {k: v for k, v in data.items() if k not in process.__dict__}
        process.storage = storage
        return process

    def expired(self):
        # TODO: expire MISC storage processes after some time that it was last valid?
        return False


class Schedule:
    TASK_NAME_REGEX = re.compile(r"^(.*?)(\s#(\d+))?(\s\w+)?")

    def __init__(self, scheduler, iterable=None):
        self.scheduler = scheduler
        self.start_times = SortedList(key=lambda t: t if isinstance(t, datetime) else t.start_time)
        self.end_times = SortedList(key=lambda t: t if isinstance(t, datetime) else t.end_time)
        self.tasks = {}  # task_name -> Task
        self.max_task_no = {}  # process_name -> max_task_no
        self.deleted_tasks = SortedList(key=lambda t: t if isinstance(t, datetime) else t.start_time)

        if iterable is not None:
            for task in iterable:
                self.add(task)

    def add(self, task: Task, apply_limits=False) -> bool:
        if task.status in (TaskStatus.EXECUTED, TaskStatus.CANCELLED):
            self.update_task_numbering(task.task_name)
            self.deleted_tasks.add(task)
            return False

        if task.task_name is None:
            process_name = task.get_process_name()
            if not process_name or '#' in process_name:
                raise ValueError(f"process_name cannot be empty or have '#' character in it: {process_name}")
            task.task_name = self.new_task_name(process_name)

        if task.task_name in self.tasks:
            raise ValueError(f"Task {task.task_name} already exists")

        process = self.scheduler.processes.get(task.process_name, None)
        if apply_limits:
            tmp = task.start_time.replace(hour=12, minute=0, second=0, microsecond=0)
            prev_noon = tmp - timedelta(days=1) if task.start_time < tmp else tmp
            next_noon = prev_noon + timedelta(days=1)
            time_used_s = sum((t.end_time - t.start_time).total_seconds()
                              for t in list(self.tasks.values())
                                       + [d for d in self.deleted_tasks if d.status == TaskStatus.EXECUTED]
                              if t.process_name == task.process_name and prev_noon < t.start_time < next_noon)
            task.apply_limits(process, time_used_s=int(time_used_s))
            if not task.is_valid(process):
                return False

        elif task.start_time > task.end_time:
            raise ValueError(f"Task {task.task_name} start time {task.start_time} is after end time {task.end_time}")

        overlapping = self.get_overlapping(task.start_time, task.end_time, task.rotators)
        if len(overlapping) > 0:
            # NOTE: would get confused if tasks with status EXECUTED or CANCELLED would be still in the *_times lists
            raise ValueError(f"Task {task.task_name} ({task.start_time} - {task.end_time}) "
                             "overlaps with existing task(s) " + (', '.join([str(t) for t in overlapping])))

        self.start_times.add(task)
        self.end_times.add(task)
        self.tasks[task.task_name] = task
        self.update_task_numbering(task.task_name)
        return True

    def new_task_name(self, process_name):
        self.max_task_no[process_name] = self.max_task_no.get(process_name, 0) + 1
        return f"{process_name} #{self.max_task_no[process_name]}"

    def update_task_numbering(self, task_name):
        m = Schedule.TASK_NAME_REGEX.fullmatch(task_name)
        if m:
            base, n, pf = m[1], m[3], m[4]
            self.max_task_no[base] = max(self.max_task_no.get(base, 0), int(n) if n else 0)

    def remove(self, task: Task):
        if task.task_name in self.tasks:
            self.start_times.remove(task)
            self.end_times.remove(task)
            del self.tasks[task.task_name]

            task.status = TaskStatus.EXECUTED if task.status == TaskStatus.ONGOING else TaskStatus.CANCELLED
            self.deleted_tasks.add(task)
        else:
            raise ValueError(f"Task {task.task_name} does not exist")

    def get_overlapping(self, start_time: datetime, end_time: datetime, rotators: List[str]):
        # all tasks where task.start_time <= end_time and task.end_time >= start_time and they share rotators
        rotators = set(rotators)
        tasks1 = self.start_times.irange(maximum=end_time, inclusive=(True, False))
        tasks2 = self.end_times.irange(minimum=start_time, inclusive=(False, True))
        return sorted([self.tasks[t.task_name]
                       for t in set(tasks1).intersection(tasks2)
                       if rotators.intersection(t.rotators)
                       ], key=lambda t: t.start_time)

    def all(self):
        start_times_copy = self.start_times.copy()
        start_times_copy.update(self.deleted_tasks)
        return iter(start_times_copy)

    def __iter__(self):
        return iter(self.start_times)

    def __len__(self):
        return len(self.start_times)


def iter_all_strings():
    for size in itertools.count(1):
        for s in itertools.product(ascii_lowercase, repeat=size):
            yield "".join(s)
