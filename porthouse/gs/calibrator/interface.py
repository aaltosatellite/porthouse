from porthouse.core.rpc_async import send_rpc_request

class CalibratorInterface:
    """
    Calibrator related commands
    """

    def __init__(self, prefix):
        self.prefix = prefix
    
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