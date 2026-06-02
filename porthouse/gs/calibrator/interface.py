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
        await send_rpc_request("calibrator", f"{self.prefix}.rpc.calibration", {
            "enabled": enabled
        })