"""
    Rotator controller base class
"""

import time
import abc
from typing import Tuple, Optional, List, Union

import numpy as np

from ...core.config import cfg_path
from ..tracking.utils import CelestialObject, angle_between_el_az_deg
from .geometry import AzElRotator


class RotatorError(Exception):
    """ Exception class for all rotator hardware """


PositionType = Tuple[float, float]


class RotatorController(abc.ABC):
    address: str
    current_position: PositionType
    current_pos_ts: float
    target_position: PositionType
    target_pos_ts: float

    az_min: float
    az_max: float
    el_min: float
    el_max: float

    horizon_map_file: Optional[str]
    horizon_map: Optional[np.ndarray]
    min_sun_angle: Optional[float]
    enforce_limits: bool
    debug: bool

    def __init__(self,
                 address: str,
                 az_min: float = -90,
                 az_max: float = 450,
                 el_min: float = 0,
                 el_max: float = 90,
                 rotator_model: Optional[dict] = None,
                 horizon_map_file: Optional[str] = None,
                 min_sun_angle: Optional[float] = None,
                 debug: bool = False,
                 prefix: str = ""):
        """
        Initialize controller hardware driver including any serial com.

        Args:
            address: Controller address
            az_min: Minimum allowed azimuth angle
            az_max: Maximum allowed azimuth angle
            el_min: Minimum allowed elevation angle
            el_max: Maximum allowed elevation angle
            rotator_model: A dictionary containing the rotator model that is used to transform real azimuth and
                           elevation values to motor angles.
            horizon_map_file: A file that can be read with numpy load and results in two column array (az, el) [deg],
                              where rows are points on the horizon. If set, the horizon map is used to limit
                              the elevation.
            min_sun_angle: Minimum allowed sun angle
            debug: Debug flag. If true, debug information is logged.
        """
        self.address = address
        self.az_min = az_min
        self.az_max = az_max
        self.el_min = el_min
        self.el_max = el_max
        self.debug = debug
        self.enforce_limits = True
        self.current_position = (0.0, 0.0)
        self.current_pos_ts = 0.0
        self.target_position = (0.0, 0.0)
        self.target_pos_ts = 0.0

        self.rotator_model = AzElRotator(**(rotator_model or {}))
        self.horizon_map_file = None
        self.horizon_map = None

        if horizon_map_file is not None and horizon_map_file.strip().lower() not in ('', 'none', 'null'):
            self.horizon_map_file = horizon_map_file
            self.horizon_map = hm = np.load(cfg_path(horizon_map_file))
            assert hm is not None and len(hm.shape) == 2 and hm.shape[1] == 2, \
                f'horizon map {horizon_map_file} must be an array with two columns (az, el), ' \
                f'current shape is {hm.shape}'
            assert np.all(hm[:, 0] >= 0) and np.all(hm[:, 0] <= 360), "horizon map azimuth values must be in [0, 360]"
            assert np.all(hm[:, 1] >= 0) and np.all(hm[:, 1] <= 90), "horizon map elevation values must be in [0, 90]"
            assert np.isclose(hm[0, 0], 0) and np.isclose(hm[-1, 0], 360) and np.isclose(hm[0, 1], hm[-1, 1]), \
                "horizon map must start and end at the same elevation (azimuth 0 and 360)"
            assert np.all(np.diff(hm[:, 0]) > 0), "horizon map azimuth values must be in increasing order"

        try:
            self.min_sun_angle, self.sun = [None] * 2
            self.min_sun_angle = float(min_sun_angle)
        except (ValueError, TypeError):
            pass

        if self.min_sun_angle is not None:
            self.sun = CelestialObject('cel:Sun')
            self.sun.initialize()

    async def setup(self):
        """Override if driver needs async setup before use."""

    def open(self):
        """Open serial com to controller hardware."""

    def close(self):
        """Close serial com to controller hardware."""

    def reset(self, wait_time: float = 1.0):
        """Reset serial com to controller hardware."""
        time.sleep(wait_time)

    def flush_buffers(self):
        """ Clear/flush the input and output buffer of serial com."""

    @abc.abstractmethod
    def stop(self) -> None:
        """
        Stop rotator movement
        """

    @abc.abstractmethod
    def get_position(self, with_timestamp=False) -> Union[PositionType, Tuple[PositionType, float]]:
        """
        Read rotator's current position. If the position is invalid, move to closest allowed position.

        Returns:
            A tuple containing current azimuth and elevation.
        """
        # Subclasses should have these two lines in the end of the method:
        self.maybe_enforce_limits()
        return self.current_position if not with_timestamp else (self.current_position, self.current_pos_ts)

    @abc.abstractmethod
    def set_position(self,
                     az: float,
                     el: float,
                     ts: Optional[float] = None,
                     rounding: int = 1,
                     shortest_path: bool = True) -> PositionType:
        """
        Set azimuth and elevation to precision of rounding and threshold.
        Additionally, possible to not use shortest path.

        Args:
            az: Target azimuth angle
            el: Target elevation angle
            ts: Timestamp for the target position
            rounding: Number of decimals
            shortest_path: Should the rotator try move using shortest path

        Returns:
            Returns the current rotator position as tuple

        Raises:
            `RotatorError` - in case the controller encountered an error.
        """
        # Subclasses should have these two lines in the beginning of the method:
        self.position_valid(az, el, raise_error=True)
        self.target_position = (az, el)
        self.target_pos_ts = ts or time.time()

    def get_position_target(self) -> PositionType:
        """
        Get position where the rotator is moving to.

        Returns:
            Target position as tuple

        Raises:
            `RotatorError` - in case the controller encountered an error.
        """
        return self.target_position

    def get_position_range(self) -> Tuple[float, float, float, float]:
        """
        Read back the allowed range of azimuth (az) and elevation (el) coordinates.

        Returns:
            A tuple containing ranges: az_min, az_max, el_min, el_max

        Raises:
            `RotatorError` - in case the controller encountered an error.
        """
        return self.az_min, self.az_max, self.el_min, self.el_max

    def set_position_range(self,
                           az_min: Optional[float] = None,
                           az_max: Optional[float] = None,
                           el_min: Optional[float] = None,
                           el_max: Optional[float] = None,
                           rounding: int = 1) -> Tuple[float, float, float, float]:
        """
        Sets azimuth and elevation range limits.

        Raises:
            `RotatorError` - in case the controller encountered an error.
        """
        if az_min is not None:
            self.az_min = az_min
        if az_max is not None:
            self.az_max = az_max
        if el_min is not None:
            self.el_min = el_min
        if el_max is not None:
            self.el_max = el_max

    @abc.abstractmethod
    def reset_position(self, az: float, el: float) -> None:
        """
        Set the current position to the given values without moving the rotator.
        """

    @abc.abstractmethod
    def get_dutycycle_range(self) -> Tuple[int, int, int, int]:
        """
        Get duty cycle range for azimuth and elevation.

        Returns:
            A tuple with (az_min, az_max, el_min, el_max) duty cycles.

        Raises:
            `RotatorError` - in case the controller encountered an error.
        """

    @abc.abstractmethod
    def set_dutycycle_range(self,
                            az_duty_min: Optional[int] = None,
                            az_duty_max: Optional[int] = None,
                            el_duty_min: Optional[int] = None,
                            el_duty_max: Optional[int] = None) -> None:
        """
            Set duty cycle range for azimuth and elevation.

        Args:
            az_duty_min: Minimum duty cycle (start speed) for azimuth
            az_duty_max: Maximum duty cycle (max speed) for azimuth
            el_duty_min: Minimum duty cycle (start speed) for elevation
            el_duty_max: Maximum duty cycle (max speed) for elevation

        Raises:
            `RotatorError` - in case the controller encountered an error.
        """

    def position_valid(self, az: float, el: float, raise_error: bool = False) -> bool:
        """
        Check if the given position is valid, i.e. within allowed limits. If horizon_map or min_sun_angle is set,
        the position is also checked against those limits. If raise_error is True, an exception is raised if the
        position is invalid.

        Args:
            az: Azimuth angle
            el: Elevation angle
            raise_error: If True, raise an exception if the position is invalid

        Raises:
            `RotatorError` - in case raise_error == True and invalid position given

        Returns:
            True if the position is valid, False otherwise
        """
        valid = True

        maz, mel = self.rotator_model.to_motor(az, el)

        if maz < self.az_min or maz > self.az_max:
            valid = False
            if raise_error:
                raise RotatorError(f"Azimuth value {az} ({maz}) is outside allowed limits "
                                   f"[({self.az_min}), ({self.az_max})].")

        # use horizon map if set to get the min elevation for the given azimuth
        el_min = self.az_dependent_min_el(az)

        if el_min is not None and el < el_min or mel < self.el_min or mel > self.el_max:
            valid = False
            if raise_error:
                raise RotatorError(f"Elevation value {el} ({mel}) is outside allowed limits "
                                   f"[{el_min} ({self.el_min}), ({self.el_max})]" +
                                   (f" given current azimuth {az} ({maz})." if self.horizon_map is not None else "."))

        if self.min_sun_angle is not None:
            sun_angle, _, _ = self.get_sun_angle(az, el)
            if sun_angle < self.min_sun_angle:
                valid = False
                if raise_error:
                    raise RotatorError(f"Sun angle {sun_angle} is below the allowed limit {self.min_sun_angle}.")

        return valid

    def maybe_enforce_limits(self) -> None:
        """
        If enforce_limits enabled, check that the current position is within allowed limits. If not, use set_position
        to move to the closest allowed position. Note that the original target position is lost and must be reset at
        a higher level.
        """
        if self.enforce_limits and not self.position_valid(*self.current_position):
            valid_position = self.closest_valid_position(*self.current_position)
            self.set_position(*valid_position, rounding=1, shortest_path=True)

    def az_dependent_min_el(self, az: float) -> Optional[float]:
        if self.horizon_map is not None:
            el_min = np.interp(az % 360, self.horizon_map[:, 0], self.horizon_map[:, 1])
            return np.floor(el_min/100)*100
        return None

    def get_sun_angle(self, az: float, el: float) -> Tuple[float, float, float]:
        """
        Calculate the sun angle between the given position and the sun.

        Args:
            az: Azimuth angle
            el: Elevation angle

        Returns:
            Tuple of sun angle, sun azimuth and sun elevation
        """
        assert self.sun is not None, 'min_sun_angle set after initialization, sun object is not initialized'
        try:
            sun_el, sun_az, _ = self.sun.pos_at(None).altaz()
            sun_az, sun_el = sun_az.degrees, sun_el.degrees
            sun_angle = angle_between_el_az_deg(az, el, sun_az, sun_el)
        except Exception as e:
            raise RotatorError(f"Failed to calculate sun angle, param values: "
                               f"az={az}, el={el}, sun_az={sun_az}, sun_el={sun_el}: {e}")

        return sun_angle, sun_az, sun_el

    def closest_valid_position(self, az: float, el: float) -> PositionType:
        """
        Find the closest allowed position to the given position.

        Args:
            az: Azimuth angle
            el: Elevation angle

        Returns:
            Tuple of closest allowed azimuth and elevation angles
        """
        # TODO: come up with some more efficient algorithm to avoid the sun

        # use horizon map if set to get the min elevation for the given azimuth
        el_min = self.az_dependent_min_el(az)
        if el_min is not None:
            el = max(el_min, el)

        maz, mel = self.rotator_model.to_motor(az, el)
        maz = max(self.az_min, min(self.az_max, maz))
        mel = max(self.el_min, min(self.el_max, mel))
        az, el = self.rotator_model.to_real(maz, mel)

        if self.min_sun_angle is not None:
            sun_angle, sun_az, sun_el = self.get_sun_angle(az, el)
            if sun_angle < self.min_sun_angle:
                az, el = self.closest_valid_position(az + (2 if az > sun_az else -2),
                                                     el + (2 if el > sun_el else -2))

        return az, el
