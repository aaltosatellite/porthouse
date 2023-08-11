"""
    Dummy controller interface that does nothing, useful for testing
"""

import time
from typing import Tuple, Optional

from .controllerbox import PositionType, ControllerBoxError


class DummyRotatorController:
    def __init__(self,
            address: str,
            baudrate: int=115200,
            az_min: int =-90,
            az_max: int =450,
            el_min: int =0,
            el_max: int =90,
            debug=False):

        self.az_min = az_min
        self.az_max = az_max
        self.el_min = el_min
        self.el_max = el_max
        self.debug = debug
        self.current_position = (0.0, 0.0)
        self.err_cnt = 0

        self._target_position = (0.0, 0.0)
        self._az_dc_min, self._az_dc_max, self._el_dc_min, self._el_dc_max = [60] * 4

        if self.debug:
            self.log = open(f"controlbox_debug_{time.time():.0f}.log", "w")

    def open(self):
        pass

    def close(self):
        pass

    def reset(self, wait_time=1):
        time.sleep(wait_time)

    def flush_buffers(self):
        pass

    def stop(self) -> None:
        pass

    def get_position(self) -> PositionType:
        return self.current_position

    def set_position(self,
            az: float,
            el: float,
            rounding: int=1,
            shortest_path: bool=True
        ) -> PositionType:

        if az < self.az_min or az > self.az_max:
            raise ControllerBoxError("Azimuth value outside allowed limits.")
        if el < self.el_min or el > self.el_max:
            raise ControllerBoxError("Elevation value outside allowed limits.")

        self._target_position = (az, el)
        self.current_position = (az, el)
        return self.get_position_target()

    def get_position_target(self) -> PositionType:
        return self._target_position

    def get_position_range(self) -> Tuple[float, float, float, float]:
        return self.az_min, self.az_max, self.el_min, self.el_max

    def set_position_range(self,
           az_min: Optional[float]=None,
           az_max: Optional[float]=None,
           el_min: Optional[float]=None,
           el_max: Optional[float]=None,
           rounding: int=1):
        if az_min is not None:
            self.az_min = az_min

        if az_max is not None:
            self.az_max = az_max

        if el_min is not None:
            self.el_min = el_min

        if el_max is not None:
            self.el_max = el_max

        return self.get_position_range()

    def calibrate(self,
            az: float,
            el: float,
            rounding: int=1,
            timeout=120
        ) -> PositionType:

        self.set_position(az, el, rounding=rounding, shortest_path=False)

        timeout = time.time() + timeout
        while timeout < time.time():
            time.sleep(1)

        return self.get_position()

    def get_dutycycle_range(self) -> Tuple[int, int, int, int]:
        return self._az_dc_min, self._az_dc_max, self._el_dc_min, self._el_dc_max

    def set_dutycycle_range(self,
            az_duty_min: Optional[int]=None,
            az_duty_max: Optional[int]=None,
            el_duty_min: Optional[int]=None,
            el_duty_max: Optional[int]=None
        ) -> None:
        if az_duty_min is not None:
            self._az_dc_min = az_duty_min

        if az_duty_max is not None:
            self._az_dc_max = az_duty_max

        if el_duty_min is not None:
            self._el_dc_min = el_duty_min

        if el_duty_max is not None:
            self._el_dc_max = el_duty_max
