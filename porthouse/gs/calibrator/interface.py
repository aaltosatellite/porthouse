from porthouse.core.rpc_async import send_rpc_request

class CalibratorInterface:
    """
    Calibrator related commands
    """

    def __init__(self):
        pass
    
    async def set_enabled(
            self,
            enabled: bool=True
        ):
        """
        Enable/disable automatic calibration.

        Args:
            enabled: If true automatic calibration is enabled.
        """
        await send_rpc_request("calibrator", "rpc.calibration", {
            "enabled": enabled
        })
        
    async def set_max_calibration_cycles(
            self,
            cycle_count: int
        ):
        """
        Set maximum amount of cycles the calibration can perform when having unsatisfactory results before giving up

        Args:
            cycle_count: Cycle amount
        """
        await send_rpc_request("calibrator", "rpc.cycle_count", {
            "cycle_count": cycle_count
        })
    
    async def calibrate(self):
        """
        Manually run a calibration cycle
        """
        await send_rpc_request("calibrator", "rpc.calibrate",timeout=1800)
    
    async def calibrate_mindfully(self):
        """
        Manually runs the 'check_schedule' function before calibrating
        """
        await send_rpc_request("calibrator", "rpc.calibrate_sched",timeout=1800)
    
    async def stop_calibration(self):
        """
        Stops the calibration at the next possible opportunity
        """
        await send_rpc_request("calibrator", "rpc.stop_calibration")
    
    async def status(self):
        """
        Reports the current status of the calibrator and configuration
        """
        status = await send_rpc_request("calibrator", "rpc.status")
        return status