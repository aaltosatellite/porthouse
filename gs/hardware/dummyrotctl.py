"""
    Dummy controller interface that does nothing, useful for testing
"""

import time
from typing import Tuple, Optional

from .base import RotatorController
from .controllerbox import PositionType, ControllerBoxError


class DummyRotatorController(RotatorController):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._az_dc_min, self._az_dc_max, self._el_dc_min, self._el_dc_max = [60] * 4

    def stop(self) -> None:
        pass

    def get_position(self, with_timestamp=False) -> PositionType:
        self.maybe_enforce_limits()
        self.current_pos_ts = time.time()
        return self.current_position if not with_timestamp else (self.current_position, self.current_pos_ts)

    def set_position(self,
                     az: float,
                     el: float,
                     ts: Optional[float] = None,
                     shortest_path: bool = True) -> PositionType:
        self.position_valid(az, el, raise_error=True)
        self.target_position = (az, el)
        self.target_pos_ts = ts or time.time()
        self.current_position = (az, el)
        self.current_pos_ts = time.time()
        return az, el

    def get_position_target(self) -> PositionType:
        return self.target_position

    def get_position_range(self) -> Tuple[float, float, float, float]:
        return self.az_min, self.az_max, self.el_min, self.el_max

    def set_position_range(self,
                           az_min: Optional[float] = None,
                           az_max: Optional[float] = None,
                           el_min: Optional[float] = None,
                           el_max: Optional[float] = None) -> Tuple[float, float, float, float]:
        if az_min is not None:
            self.az_min = az_min

        if az_max is not None:
            self.az_max = az_max

        if el_min is not None:
            self.el_min = el_min

        if el_max is not None:
            self.el_max = el_max

        return self.get_position_range()

    def reset_position(self, az: float, el: float):
        self.current_position = az, el

    def get_dutycycle_range(self) -> Tuple[float, float, float, float]:
        return self._az_dc_min, self._az_dc_max, self._el_dc_min, self._el_dc_max

    def set_dutycycle_range(self,
                            az_duty_min: Optional[float] = None,
                            az_duty_max: Optional[float] = None,
                            el_duty_min: Optional[float] = None,
                            el_duty_max: Optional[float] = None) -> None:
        if az_duty_min is not None:
            self._az_dc_min = az_duty_min

        if az_duty_max is not None:
            self._az_dc_max = az_duty_max

        if el_duty_min is not None:
            self._el_dc_min = el_duty_min

        if el_duty_max is not None:
            self._el_dc_max = el_duty_max

    def pop_motion_log(self):
        pass
