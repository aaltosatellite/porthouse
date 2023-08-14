from porthouse.core.rpc_async import send_rpc_request


class SchedulerInterface:
    """
    Scheduler related commands
    """

    async def get_schedule(self, verbose=True):
        """
        Get satellite tracker status.
        """
        schedule = await send_rpc_request("scheduler", "rpc.get_schedule")
        if verbose:
            print(schedule)
        else:
            return schedule

    async def get_processes(self, verbose=True):
        processes = await send_rpc_request("scheduler", "rpc.get_processes")
        if verbose:
            print(processes)
        else:
            return processes

    async def update_schedule(self, start_time=None, end_time=None):
        params = dict(start_time=start_time, end_time=end_time)
        res = await send_rpc_request("scheduler", "rpc.update_schedule", params)
        return res

    async def enable_schedule_file_sync(self, enable):
        res = await send_rpc_request("scheduler", "rpc.enable_schedule_file_sync", {"enable": enable})
        return res

    async def add_task(self):
        raise NotImplementedError()

    async def remove_task(self):
        raise NotImplementedError()

    async def get_potential_tasks(self):
        raise NotImplementedError()

