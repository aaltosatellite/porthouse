from porthouse.core.rpc_async import send_rpc_request


class SchedulerInterface:
    """
    Scheduler related commands
    """

    async def get_schedule(self, verbose=True):
        """
        Get all scheduled tasks.
        """
        schedule = await send_rpc_request("scheduler", "rpc.get_schedule")
        if verbose:
            print(schedule)
        else:
            return schedule

    async def get_processes(self, verbose=True):
        """
        List all processes.
        """
        processes = await send_rpc_request("scheduler", "rpc.get_processes")
        if verbose:
            print(processes)
        else:
            return processes

    async def update_schedule(self, start_time=None, end_time=None, reset=False, process_name=None):
        """
        Update schedule manually. If reset=True, clears schedule first. Affects only given process_name if provided,
        else affects all processes (default). Affected time range is [start_time, end_time).
        Args:
            start_time: Datetime in ISO format and UTC timezone, e.g. "2020-01-01T00:00:00". Default is now.
            end_time: Same format as start_time, default is 48 hours from now.
            reset: bool
            process_name: str
        """
        params = dict(start_time=start_time, end_time=end_time, reset=reset, process_name=process_name)
        res = await send_rpc_request("scheduler", "rpc.update_schedule", params)
        return res

    async def enable_schedule_file_sync(self, enable):
        """
        Enable/disable schedule.yaml file constant reading and writing. Also disables processes.yaml reading (and in
        the future writing).
        """
        res = await send_rpc_request("scheduler", "rpc.enable_schedule_file_sync", {"enable": enable})
        return res

    async def add_task(self):
        raise NotImplementedError()

    async def remove_task(self):
        raise NotImplementedError()

    async def get_potential_tasks(self):
        raise NotImplementedError()

