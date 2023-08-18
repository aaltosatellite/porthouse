"""
    Scheduler
"""

import asyncio
from collections import OrderedDict
from typing import List, Union, Optional
import yaml

from datetime import datetime, timedelta, timezone

from porthouse.core.config import cfg_path
from porthouse.core.basemodule_async import BaseModule, RPCError, rpc, bind, RPCRequestTimeout
from porthouse.gs.scheduler.model import Schedule, TaskStatus, Process, Task
from porthouse.gs.tracking.gnss_tracker import PointTracker
from porthouse.gs.tracking.orbit_tracker import OrbitTracker
from porthouse.gs.tracking.utils import SkyfieldModuleMixin, CelestialObject, parse_time


class Scheduler(SkyfieldModuleMixin, BaseModule):
    """
    Scheduler module
    """

    MISC_TRACKER_PREFIX = "misc:"

    def __init__(self, main_processes_file="processes.yaml", misc_processes_file="misc-processes.yaml",
                 main_schedule_file="schedule.yaml", misc_schedule_file="misc-schedule.yaml", **kwargs):
        """
        Initialization
        """
        super().__init__(**kwargs)

        self.main_processes_file = main_processes_file
        self.misc_processes_file = misc_processes_file
        self.processes = OrderedDict()

        self.main_schedule_file = main_schedule_file
        self.misc_schedule_file = misc_schedule_file
        self.schedule = Schedule()
        self.schedule_updated_date = None
        self._create_schedule_task = None
        self._debug_log_time = datetime.utcfromtimestamp(0).replace(tzinfo=timezone.utc)

        # Schedule updating via execution, new task creation, api task addition & removal  can in general be done
        # concurrently. However, schedule updating by reloading the schedule file should be done exclusively.
        self.schedule_lock = asyncio.Lock()

        self.tle_sats = []
        self.gs_rotators = []

        self.sync_schedule_files = True

        loop = asyncio.get_event_loop()
        task = loop.create_task(self.setup(), name="scheduler.setup")
        task.add_done_callback(self.task_done_handler)

    async def setup(self):
        self.gs_rotators = await self.check_rotators(self.gs.config["rotators"])

        tle_list = await self.send_rpc_request("tracking", "tle.rpc.get_tle")
        self.tle_sats = [tle["name"] for tle in tle_list["tle"]]

        # TODO: make the following lines unnecessary by updating the tle server code
        for proc in self.processes.values():
            if proc["tracker"] == OrbitTracker.TRACKER_TYPE and proc["target"] not in self.tle_sats:
                raise RuntimeError("No TLEs configured for %s", proc["target"])

        while True:
            await self.execute_schedule()
            await asyncio.sleep(1)

    async def check_rotators(self, rotators: List[str]):
        """
        Check if rotators are available.
        """
        await asyncio.sleep(1)

        available_rotators = []
        for prefix in rotators:
            try:
                status = await self.send_rpc_request("rotator", f"{prefix}.rpc.status", timeout=2)
                if len(status):
                    available_rotators.append(prefix)
            except (RPCRequestTimeout, asyncio.exceptions.TimeoutError):
                self.log.warning(f"Rotator {prefix} not available")

        self.log.debug(f"Available rotators: {available_rotators}")
        return rotators

    async def execute_schedule(self):
        """
        Executes the schedule (i.e. checks for passes), starts/stops tracking accordingly, creates new tasks
        every 24h.
        """
        await asyncio.sleep(0)

        write_schedule = False
        if not self.schedule_lock.locked():
            # update schedule from file if schedule is not being updated by another task
            self.read_processes()
            write_schedule = self.sync_schedule_files
            await self.read_schedule()

        now = datetime.now(timezone.utc).replace(microsecond=0)  # + timedelta(minutes=1*60 + 3)

        # check for tasks that should start
        for task in self.schedule.start_times:
            if task.start_time <= now < task.end_time and task.status == TaskStatus.SCHEDULED:
                task.status = TaskStatus.ONGOING
                await self.start_task(task)
            elif task.start_time > now:
                if self._debug_log_time + timedelta(seconds=10) <= now:
                    self._debug_log_time = now
                    self.log.debug(f"Task \"{task.task_name}\" starting in {task.start_time - now}"
                                   f" ({task.start_time}) channel ok: {not self.channel.is_closed}")
                break

        # check for tasks that should be terminated or removed
        remove_tasks = []
        for task in self.schedule.end_times:
            if now >= task.end_time and task.status == TaskStatus.ONGOING:
                remove_tasks.append(task)
                await self.end_task(task)
            elif now >= task.end_time:
                remove_tasks.append(task)
            elif task.end_time > now:
                break

        for task in remove_tasks:
            self.schedule.remove(task)

        if write_schedule:
            self.write_schedule()

        self.maybe_start_schedule_creation()

    def maybe_start_schedule_creation(self, start_time=None, end_time=None, force=False, process_name=None):
        """
        Create new tasks every 24h, up to 48h into the future, starting from the last scheduled task or 24h into
        the future, whichever is earlier. Can also be used to force schedule creation for a given time interval,
        possibly limiting the creation to a certain process only.
        """
        now = datetime.now(timezone.utc).replace(microsecond=0)

        if force or self.schedule_updated_date is None or self.schedule_updated_date < now - timedelta(hours=24):
            if self._create_schedule_task is not None:
                if force:
                    raise RPCError("Schedule creation already in progress")
                self.log.warning("Previous schedule creation task has not finished! Cancelling it now.")
                self._create_schedule_task.cancel()
                self._create_schedule_task = None

            self.schedule_updated_date = now

            if start_time is None:
                start_time = now if len(self.schedule.end_times) == 0 else self.schedule.end_times[-1].end_time
                start_time = min(start_time, now + timedelta(hours=24))

            if end_time is None:
                end_time = now + timedelta(hours=48)

            loop = asyncio.get_event_loop()
            self._create_schedule_task = loop.create_task(self.create_schedule(start_time, end_time, process_name),
                                                          name="scheduler.create_schedule")
            self._create_schedule_task.add_done_callback(self.task_done_handler)

    def read_processes(self):
        """
        Read processes from file
        """
        if not self.sync_schedule_files:
            return

        self.processes = OrderedDict()

        for file, storage in ((self.main_processes_file, Process.STORAGE_MAIN),
                              (self.misc_processes_file, Process.STORAGE_MISC)):
            try:
                with open(cfg_path(file), "r") as fp:
                    processes = yaml.load(fp, Loader=yaml.Loader)
            except FileNotFoundError:
                if storage == Process.STORAGE_MAIN:
                    self.log.error(f"Failed to open processes file {file}", exc_info=True)
                continue

            for proc in (processes or []):
                proc = Process.from_dict(proc, storage=storage)
                if storage == Process.STORAGE_MAIN or not proc.expired():
                    self.processes[proc.process_name] = proc

    def write_processes(self, skip_main=True):
        """
        Write schedule to YAML file
        """
        if not self.sync_schedule_files:
            return

        for file, storage in ((self.main_processes_file, Process.STORAGE_MAIN),
                              (self.misc_processes_file, Process.STORAGE_MISC)):
            if skip_main and storage == Process.STORAGE_MAIN:
                # TODO: should we be able to write main processes file or not?
                continue

            processes = [proc.to_dict() for proc in self.processes.values()
                         if proc.storage == storage and (storage == Process.STORAGE_MAIN or not proc.expired())]

            try:
                with open(cfg_path(file), "w") as fp:
                    yaml.dump(processes, fp, indent=4, sort_keys=False)
            except Exception as e:
                self.log.error(f"Failed to write schedule file {file}: {e}", exc_info=True)

    async def read_schedule(self):
        """
        Read schedule from file
        """
        if not self.sync_schedule_files:
            return

        async with self.schedule_lock:
            self.schedule = Schedule()

            for file, storage in ((self.main_schedule_file, Task.STORAGE_MAIN),
                                  (self.misc_schedule_file, Task.STORAGE_MISC)):
                try:
                    with open(cfg_path(file), "r") as fp:
                        schedule = yaml.load(fp, Loader=yaml.Loader) or []
                except FileNotFoundError:
                    schedule = []

                try:
                    for task in schedule:
                        self.schedule.add(Task.from_dict(task, storage=storage))
                except ValueError as e:
                    self.log.error(f"Failed to read schedule file {file}: {e}")

    def write_schedule(self):
        """
        Write schedule to YAML file
        """
        if not self.sync_schedule_files:
            return

        for file, storage in ((self.main_schedule_file, Task.STORAGE_MAIN),
                              (self.misc_schedule_file, Task.STORAGE_MISC)):
            schedule = [task.to_dict()
                        for task in self.schedule.all()
                        if task.storage == storage and (
                            task.status not in (TaskStatus.EXECUTED, TaskStatus.CANCELLED)
                            or (datetime.now(timezone.utc) - task.end_time) < timedelta(hours=24))]

            try:
                with open(cfg_path(file), "w") as fp:
                    yaml.dump(schedule, fp, indent=4, sort_keys=False)
            except Exception as e:
                self.log.error(f"Failed to write schedule file {file}: {e}", exc_info=True)

    async def start_task(self, task):
        self.log.info(f"Start task \"{task.task_name}\" {task.rotators}")
        await self.publish(task.get_task_data(self.processes[task.process_name]),
                           exchange="scheduler", routing_key="task.start")

    async def end_task(self, task):
        self.log.info(f"End task \"{task.task_name}\" {task.rotators}")
        await self.publish(task.get_task_data(self.processes[task.process_name]),
                           exchange="scheduler", routing_key="task.end")

    def export_schedule(self, target=None, rotators=None, status=None, limit=None):
        def filter_task(task):
            if target is not None and task.target != target:
                return False
            if rotators is not None and len(set(rotators).intersection(task.rotators)) == 0:
                return False
            if status is not None and task.status != status:
                return False
            return True

        schedule = [task.to_dict() for task in self.schedule if filter_task(task)][:limit]
        return schedule

    def export_processes(self, target=None, rotators=None, enabled=None, storage=None):
        def filter_task(process):
            if target is not None and target not in process.target:
                return False
            if rotators is not None and len(set(rotators).intersection(process.rotators)) == 0:
                return False
            if enabled is not None and process.enabled != enabled:
                return False
            if storage is not None and process.storage != storage:
                return False
            return True

        processes = [process.to_dict() for process in self.processes.values() if filter_task(process)]
        return processes

    async def create_schedule(self, start_time: datetime = None, end_time: datetime = None, process_name: str = None):
        """
        Create schedule by predicting passes.
        """
        start_time = start_time or datetime.now(timezone.utc)
        end_time = end_time or start_time + timedelta(hours=24)

        self.log.debug(f"Creating schedule from {start_time.isoformat()} to {end_time.isoformat()}"
                       + ('' if process_name is None else f'for process {process_name} only') + "...")
        self.read_processes()

        # sort so that higher priority (low prio number) processes are scheduled first
        added_count = 0
        async with self.schedule_lock:
            for proc in sorted(list(self.processes.values()), key=lambda p: p.priority, reverse=False):
                if process_name is not None and proc.process_name != process_name:
                    continue
                tasks = await self.create_tasks(proc, start_time, end_time)
                self.log.debug(f"Adding {len(tasks)} tasks for process {proc.process_name}")
                c = self.add_tasks(tasks, 'procrustean')    # modify added tasks to fit into the schedule
                self.log.debug(f"After fitting to schedule, added {c} tasks for process {proc.process_name}")
                added_count += c
            self.write_schedule()

        self.log.info(f"Added {added_count} tasks to the schedule between "
                      f"{start_time.isoformat()} and {end_time.isoformat()}.")
        self._create_schedule_task = None

    def add_tasks(self, tasks: Union[List['Task'], 'Task'], mode='strict'):
        """
        Add tasks to the schedule

        Args:
            tasks: List of Task objects to be added to the schedule
            mode: 'strict': Raise SchedulerError if new task overlaps with existing task (default)
                  'force':  Force adding tasks to the schedule even if they overlap with existing tasks,
                            shorten, split, or cancel existing tasks if necessary
                  'procrustean': If True, force tasks to fit into the schedule
        """

        if isinstance(tasks, Task):
            tasks = [tasks]

        added_count = 0
        for task in tasks:
            assert task.start_time and task.end_time and task.start_time < task.end_time \
                   and task.start_time.tzinfo == timezone.utc and task.end_time.tzinfo == timezone.utc, \
                   f"Invalid task start and/or end time: {task.start_time} - {task.end_time}"

            if mode == 'strict':
                try:
                    self.schedule.add(task)
                    added_count += 1
                except ValueError:
                    raise SchedulerError("New task overlaps with existing task")

            elif mode == 'force':
                self.make_room_in_schedule(task)
                added_count += 1

            else:
                assert mode == 'procrustean', f"Unknown mode: {mode}"
                added_count += self.fit_to_schedule(task)

        return added_count

    def make_room_in_schedule(self, new_task: 'Task'):
        """
        Checks whether new task overlaps with already scheduled tasks, if yes,
        modifies those tasks so that new task fits into the schedule.
        """

        sched_tasks = self.schedule.get_overlapping(new_task.start_time, new_task.end_time, new_task.rotators)

        for sched_task in sched_tasks:
            if sched_task.is_inside(new_task):
                self.schedule.remove(sched_task)

            elif sched_task.is_reaching_into(new_task):
                sched_task.end_time = new_task.start_time - timedelta(seconds=1)

            elif sched_task.is_reaching_out(new_task):
                sched_task.start_time = new_task.end_time + timedelta(seconds=1)

            elif sched_task.is_encompassing(new_task):
                subtasks = sched_task.split([(new_task.start_time, new_task.end_time)])
                self.schedule.remove(sched_task)
                for task in subtasks:
                    if task.is_valid(self.processes.get(task.process_name, None)):
                        self.schedule.add(task)

        self.schedule.add(new_task)

    def fit_to_schedule(self, new_task: 'Task'):
        """
        Checks whether new task overlaps with already scheduled tasks, if yes,
        modifies the new task (trim, split, or discard) so that it fits into the schedule.
        Returns a list of modified tasks.
        """

        sched_tasks = self.schedule.get_overlapping(new_task.start_time, new_task.end_time, new_task.rotators)
        holes = []

        for sched_task in sched_tasks:
            if new_task.is_inside(sched_task):
                return 0

            elif new_task.is_reaching_into(sched_task):
                new_task.end_time = sched_task.start_time - timedelta(seconds=1)

            elif new_task.is_reaching_out(sched_task):
                new_task.start_time = sched_task.end_time + timedelta(seconds=1)

            elif new_task.is_encompassing(sched_task):
                holes.append((sched_task.start_time, sched_task.end_time))

        if holes:
            new_tasks = new_task.split(holes)
        else:
            new_tasks = [new_task]

        added_count = 0
        for new_task in new_tasks:
            if new_task.is_valid(self.processes.get(new_task.process_name, None)):
                self.schedule.add(new_task)
                added_count += 1

        return added_count

    @rpc()
    @bind("scheduler", "rpc.#")
    async def rpc_handler(self, request_name, request_data):
        """
            Parse command
        """
        await asyncio.sleep(0)

        def date_arg(date_field):
            if date_field in request_data:
                return parse_time(request_data[date_field]).utc_datetime()
            return None

        if request_name == "rpc.get_schedule":
            return self.export_schedule(**request_data)

        elif request_name == "rpc.get_processes":
            return self.export_processes(**request_data)

        elif request_name == "rpc.update_schedule":
            start_time, end_time = date_arg("start_time"), date_arg("end_time")

            if request_data.get("reset", False):
                start_time = start_time or datetime.now(timezone.utc)
                end_time = end_time or start_time + timedelta(hours=48)
                process_name = request_data.get("process_name", None)

                async with self.schedule_lock:
                    tbr = [task for task in self.schedule
                           if task.status == TaskStatus.SCHEDULED and task.auto_scheduled
                              and task.start_time >= start_time and task.end_time <= end_time
                              and (process_name is None or task.process_name == process_name)]
                    for task in tbr:
                        self.schedule.remove(task)
                    self.write_schedule()

            return self.maybe_start_schedule_creation(start_time=start_time, end_time=end_time, force=True,
                                                      process_name=request_data.get("process_name", None))

        elif request_name == "rpc.enable_schedule_file_sync":
            if "enable" not in request_data:
                raise RPCError("enable (bool) parameter not give")
            self.sync_schedule_files = request_data["enable"]
            return {"success": True}

        elif request_name == "rpc.add_task":
            #
            # Schedule new task
            #
            task = Task.from_dict(request_data)
            try:
                async with self.schedule_lock:
                    self.add_tasks(task, mode='strict')
                    self.write_schedule()
                return {"success": True}
            except SchedulerError as e:
                return {"error": "Failed to add task to schedule: " + str(e)}

        elif request_name == "rpc.remove_task":
            #
            # Remove task from the schedule
            #
            task = self.schedule.tasks.get(request_data["task_name"], None)
            if task is not None:
                async with self.schedule_lock:
                    self.schedule.remove(task)
                    self.write_schedule()
                return {"success": True}
            else:
                return {"error": "Task not found"}

        elif request_name == "rpc.get_potential_tasks":
            #
            # Get potential tasks, i.e. tasks that are unaffected by other higher priority processes
            #
            if "target" not in request_data:
                raise RPCError("No target given")

            start_time, end_time = date_arg("start_time"), date_arg("end_time")
            tasks = await self.create_tasks(Process.from_dict(request_data), start_time, end_time)
            return [task.to_dict() for task in tasks]

        raise RPCError("Unknown command")

    async def create_tasks(self, process: 'Process', start_time: datetime, end_time: datetime):
        start_time = start_time or datetime.now(timezone.utc)
        end_time = end_time or start_time + timedelta(hours=24)

        if process.tracker == OrbitTracker.TRACKER_TYPE:
            tasks = await self._create_tasks(process, start_time, end_time)
        elif process.tracker.startswith(Scheduler.MISC_TRACKER_PREFIX):
            tasks = await self._create_tasks_misc(process, start_time, end_time)
        else:
            assert process.tracker == PointTracker.TRACKER_TYPE, \
                f"Unknown tracker type for process {process.process_name}: " + process.tracker
            tasks = await self._create_tasks_fixed(process, start_time, end_time)

        if process.storage == Process.STORAGE_MISC:
            for task in tasks:
                task.storage = Task.STORAGE_MISC

        return tasks

    async def _create_tasks(self, process: 'Process', start_time: datetime, end_time: datetime):
        """
        Create tasks for a process related to a satellite or celestial object
        """
        pass_start_time = start_time + timedelta(seconds=process.preaos_time)
        kwargs = dict(target=process.target, start_time=pass_start_time, end_time=end_time,
                      min_elevation=process.min_elevation, min_max_elevation=process.min_max_elevation,
                      sun_max_elevation=process.sun_max_elevation, sunlit=process.obj_sunlit)

        if CelestialObject.is_class_of(process.target):
            obj = await self.get_celestial_object(**kwargs)
        else:
            obj = await self.get_satellite(**kwargs)

        tasks = []
        for sc_pass in obj.passes:
            task = Task()
            task.task_name = self.schedule.new_task_name(process.process_name)
            task.start_time = (sc_pass.t_aos - timedelta(seconds=process.preaos_time)).replace(microsecond=0)
            task.end_time = sc_pass.t_los.replace(microsecond=0)
            task.process_name = process.process_name
            task.rotators = process.rotators.copy()
            task.apply_limits(process)
            if task.is_valid(process):
                tasks.append(task)

        return tasks

    async def _create_tasks_misc(self, process: 'Process', start_time: datetime, end_time: datetime):
        overlapping = self.schedule.get_overlapping(start_time, end_time, process.rotators)
        holes = [(t.start_time, t.end_time) for t in overlapping]
        exchange, routing_key = process.tracker[len(Scheduler.MISC_TRACKER_PREFIX):].split(":")

        # NOTE: these tasks override the process settings, such as tracker, target, etc.
        tasks = await self.send_rpc_request(exchange, routing_key, {
            "process": process.to_dict(),
            "start_time": start_time,
            "end_time": end_time,
            "holes": holes,
        }, timeout=30)

        tasks = [Task.from_dict(task, storage=Task.STORAGE_MISC) for task in tasks]
        return tasks

    async def _create_tasks_fixed(self, process: 'Process', start_time: datetime, end_time: datetime):
        # TODO: implement gnss tracking task creation
        return []


class SchedulerError(Exception):
    pass


if __name__ == '__main__':
    Scheduler(
        amqp_url="amqp://guest:guest@localhost:5672/",
        schedule_file=".schedule.json",
        debug=True
    ).run()
