from porthouse.core.rpc_async import send_rpc_request


class SchedulerInterface:
    """
    Scheduler related commands
    """

    async def get_processes(self, process_name=None, target=None, rotators=None, enabled=None, limit=None, verbose=True):
        """
        List all processes.
        """
        data = {k: v for k, v in locals().items() if k in ("process_name", "target", "rotators", "enabled", "limit")}
        processes = await send_rpc_request("scheduler", "rpc.get_processes", data)
        if verbose:
            print(processes)
        else:
            return processes

    async def get_schedule(self, process_name=None, target=None, rotators=None, status=None, limit=None, verbose=True):
        """
        Get all scheduled tasks.
        """
        data = {k: v for k, v in locals().items() if k in ("process_name", "target", "rotators", "status", "limit")}
        schedule = await send_rpc_request("scheduler", "rpc.get_schedule", data)
        if verbose:
            print(schedule)
        else:
            return schedule

    async def update_schedule(self, start_time=None, end_time=None, reset=False, reset_ongoing=True, process_name=None):
        """
        Update schedule manually. If reset=True, clears schedule first. If reset_ongoing=True stops any ongoing task
        also. Affects only given process_name if provided, else affects all processes (default). Affected time range
        is [start_time, end_time).
        Args:
            start_time: Datetime in ISO format and UTC timezone, e.g. "2020-01-01T00:00:00". Default is now.
            end_time: Same format as start_time, default is 48 hours from now.
            reset: bool, remove all tasks in the given time range before creating new tasks.
            reset_ongoing: bool, if True (default), stops any ongoing task also if also reset=True.
            process_name: str, name of the process to update. If None (default), affects all processes.
        """
        data = {k: v for k, v in locals().items() if k in ("start_time", "end_time", "reset", "reset_ongoing",
                                                           "process_name")}
        res = await send_rpc_request("scheduler", "rpc.update_schedule", data)
        return res

    async def enable_schedule_file_sync(self, enable):
        """
        Enable/disable schedule.yaml file constant reading and writing. Also disables processes.yaml reading (and in
        the future writing).
        """
        res = await send_rpc_request("scheduler", "rpc.enable_schedule_file_sync", {"enable": enable})
        return res

    async def add_task(self, task_name, process_name, start_time, end_time, rotators, status="SCHEDULED",
                       process_overrides=None, deny_main=False, mode="strict"):
        """
        Add a task to the schedule.
        """
        process_overrides = process_overrides or {}
        data = {k: v for k, v in locals().items() if k in ("task_name", "process_name", "start_time", "end_time",
                                                           "rotators", "status", "process_overrides", "deny_main",
                                                           "mode")}
        res = await send_rpc_request("scheduler", "rpc.add_task", data)
        return res

    async def remove_task(self, task_name, deny_main=False):
        """
        Remove a task from the schedule.
        """
        data = {k: v for k, v in locals().items() if k in ("task_name", "deny_main")}
        res = await send_rpc_request("scheduler", "rpc.remove_task", data)
        return res

    async def get_potential_tasks(self, target, start_time=None, end_time=None, min_elevation=0,
                                  min_max_elevation=0, sun_max_elevation=None, obj_sunlit=None, duration=None,
                                  daily_windows=None, date_ranges=None):
        """
        Get potential tasks for a target.
        """
        data = {k: v for k, v in locals().items() if k in ("target", "start_time", "end_time", "min_elevation",
                                                           "min_max_elevation", "sun_max_elevation", "obj_sunlit",
                                                           "duration", "daily_windows", "date_ranges")}
        res = await send_rpc_request("scheduler", "rpc.get_potential_tasks", data)
        return res

