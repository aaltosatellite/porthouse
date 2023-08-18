#!/usr/bin/env python3
"""
    Generic Rotator Module
"""

import time
import json
import asyncio

import aiormq.abc

from porthouse.core.basemodule_async import BaseModule, RPCError, rpc, queue, bind
from porthouse.gs.hardware.base import RotatorController, RotatorError
from porthouse.gs.hardware.hamlib_async import HamlibAsyncController

from .controllerbox import ControllerBox
from .hamlib import HamlibController
from .dummyrotctl import DummyRotatorController


class Rotator(BaseModule):
    """
    """

    # Statics
    # minimum update interval for position queries,
    # affects how often hardware functions are called
    position_update_interval = 1.0

    rotator: RotatorController

    def __init__(self, driver, address, tracking_enabled=False, threshold=0.5, position_range=(-90, 450, 0, 90),
                 horizon_map_file=None, min_sun_angle=None, **kwargs):
        """
        Initialize rotator module

        Args:
            address: Controller address
        """

        BaseModule.__init__(self, **kwargs)

        # TOGGLES between manual rotator use or tracker-controlled automatic mode.
        self.tracking_enabled = tracking_enabled
        self.log.debug("Tracking enabled: %s" % (self.tracking_enabled,))

        # min azimuth, max azimuth, min elevation, max elevation
        assert position_range[0] < position_range[1], "azimuth min must be smaller than azimuth max"
        assert position_range[2] < position_range[3], "elevation min must be smaller than elevation max"
        assert position_range[0] >= -90, "azimuth min must be >= -90"
        assert position_range[1] <= 450, "azimuth max must be <= 450"
        assert position_range[2] >= 0, "elevation min must be >= 0"
        assert position_range[3] <= 90, "elevation max must be <= 90"

        self.threshold = threshold               # only move while position difference is larger, given in degrees

        self.prev_status = None

        # Set target azimuth and elevation values initially to default home
        # position (180,0) (debug)
        # current azimuth/elevation target coordinate
        min_elevation = position_range[2]
        self.target_position = (0, min_elevation)
        self.old_target_position = (0, min_elevation)

        # Move to target using the shortest path is default behaviour
        self.shortest_path = True

        # tries to avoid unnecessary rotate-calls, state-machine approach could be better
        self.moving_to_target = False
        self.target_valid = False

        # most recent received position received from hardware
        self.current_position = (0, min_elevation)
        self.position_timestamp = time.time()  # timestamp for most recent position

        # select given rotator controller, connect to rotator controller hardware
        driver_cls = {"hamlib": HamlibController,
                      "hamlib_async": HamlibAsyncController,
                      "aalto": ControllerBox,
                      "dummy": DummyRotatorController}.get(driver, None)
        if driver_cls is None:
            raise ValueError(f"Unknown rotator driver {driver}")
        self.rotator = driver_cls(address, az_min=position_range[0], az_max=position_range[1],
                                  el_min=position_range[2], el_max=position_range[3],
                                  horizon_map_file=horizon_map_file, min_sun_angle=min_sun_angle, debug=self.debug)

        # create setup coroutine
        loop = asyncio.get_event_loop()
        task = loop.create_task(self.setup(), name="rotator.setup")
        task.add_done_callback(self.task_done_handler)

    async def setup(self):
        """
        """

        await self.rotator.setup()

        self.log.info(f"Rotator prefix={self.prefix} initialized with driver {self.rotator.__class__.__name__}, " +
                      f"position_range={self.rotator.get_position_range()}, "
                      f"horizon_map_file={self.rotator.horizon_map_file}" +
                      (f" (array shape: {self.rotator.horizon_map.shape})" if self.rotator.horizon_map_file else "") +
                      f", and min_sun_angle={self.rotator.min_sun_angle}")

        while True:
            await self.check_state()
            await asyncio.sleep(1 if self.moving_to_target else 2)

    def refresh_rotator_position(self, force_update=False):
        """
            returns latest rotator position.
            If position information is fresh and recent enough it returns just
            last known value to avoid slowing down hardware interface too much
            (hardware is SLO-OW down there).
            Can be forced to poll new position with "force_update".
        """

        # check if position information can be considered too old
        if time.time() < self.position_timestamp + self.position_update_interval and not force_update:
            self.log.debug("No update! Ellapsed time %f",
                           time.time() - self.position_timestamp)
            return

        try:
            # record timestamp for new position
            self.current_position = self.rotator.get_position()
            self.position_timestamp = time.time()

            self.log.debug("pos now %f %f", *self.current_position)

        except RotatorError as e:
            self.log.error("Could not get rotator position: %s", e, exc_info=True)
            return

    def get_status_msg(self):
        """
        Create rotator status information frame

        Returns:
            dict containing following fields:
            - `az`: Current azimuth angle
            - `el`: Current elevation angle
            - `az_target`: Target azimuth angle
            - `el_target`: Target elevation angle
            - `tracking`: Is automatic tracking enable
            - `rotating`: Is the rotator currently moving
        """

        if time.time() - self.position_timestamp > 60:
            status = "timeout"
        else:
            status = "tracking" if self.tracking_enabled else "manual"

        status_message = {
            "az": self.current_position[0],
            "el": self.current_position[1],
            "az_target": self.target_position[0],
            "el_target": self.target_position[1],
            "tracking": status,
            "rotating": self.moving_to_target,
        }

        if self.rotator.min_sun_angle is not None:
            sun_angle, az_sun, el_sun = self.rotator.get_sun_angle(*self.current_position)
            status_message["az_sun"] = round(az_sun, 2)
            status_message["el_sun"] = round(el_sun, 2)
            status_message["sun_angle"] = round(sun_angle, 2)
            status_message["min_sun_angle"] = self.rotator.min_sun_angle

        return status_message

    async def check_state(self):
        """
        Check rotator's current state

        Calls the actual rotate -commands through hardware interface.
        This method could and should be throttled to some rotator specific
        safe update speed.
        """

        self.refresh_rotator_position()

        # Check what we are doing atm and has anything changed
        if self.target_valid:

            # the driver will avoid any safe zone violations by changing the target by itself, forgetting the given one
            if self.moving_to_target and not self.close_positions(self.target_position, self.rotator.target_position):
                self.log.info("Target position changed by driver (%s -> %s), trying to continue to previous target",
                               self.target_position, self.rotator.target_position)
                self.set_target_position(self.target_position)

            # If antenna is pointing already to current target,
            # don't send additional commands
            if not self.check_pointing():

                # If antenna is already moving towards target position,
                # don't spam rotate commands
                if not self.moving_to_target:

                    # Antenna is not at target and not yet moving to most
                    # recent target, command it to go there
                    try:
                        # move to the closest valid position instead of actual target position
                        self.target_position = self.rotator.closest_valid_position(*self.target_position)

                        ########### Actual call of rotator command ###########
                        r = self.rotator.set_position(*self.target_position, shortest_path=self.shortest_path)

                        # toggle this on to avoid calling set_position
                        # multiple times in a row
                        self.moving_to_target = True

                    except RotatorError as e:
                        self.rotator.get_position()
                        self.log.error("Rotator could not set position: %s",
                                       str(e), exc_info=True)

            else:
                # toggle off as we are at target
                self.moving_to_target = False

                # Set back to default True when target reached
                self.shortest_path = True

        else:
            # still waiting for new target coordinates, do nothing
            pass

        await self.publish(self.get_status_msg(),
            exchange="rotator",
            routing_key="status",
            prefixed=True)

    def check_pointing(self, accuracy=0.1):
        """
        Checks if antenna is pointing to target. Takes finite accuracy of
        rotators into account by allowing some dead-zone.

        Returns True if antenna is pointing to target within limits.
        """

        return self.close_positions(self.current_position, self.target_position, accuracy)

    @staticmethod
    def close_positions(pos1, pos2, accuracy=0.1):
        """
        Checks if two positions are close to each other
        """

        return abs(pos1[0] - pos2[0]) <= accuracy and \
               abs(pos1[1] - pos2[1]) <= accuracy

    def set_target_position(self, target, shortest_path=True):
        """
        Set new target position
        """

        # set target to the closest valid position instead of given target position
        valid_position = self.rotator.closest_valid_position(*target)

        self.log.debug(f"Rotating to {valid_position} (original {target})")

        # rotator function should not be called in here
        # should be done via check_state()

        # Update target variables
        self.old_target_position = self.target_position
        self.target_position = valid_position
        self.shortest_path = shortest_path

        self.target_valid = True
        # target was updated but movement command is not yet sent.
        self.moving_to_target = False

    @rpc()
    @bind(exchange="rotator", routing_key="rpc.#", prefixed=True)
    async def rpc_handler(self, request_name, request_data):
        """
            Rotator control events
        """

        self.log.debug("Rotate_event: %s: %r", request_name, request_data)

        if request_name == "rpc.tracking":
            """
                Set tracking to automatic/manual
            """

            # Parse parameters
            try:
                mode = request_data['mode']
            except (KeyError, ValueError):
                raise RPCError("Invalid or missing mode parameter 'mode'")

            self.target_valid = False  # ignore current target until new is received

            if mode == "automatic":
                self.tracking_enabled = True
                self.target_valid = False  # ignore current target until new is received
                self.log.info("Rotator is now in automatic mode")

            elif mode == "manual":
                self.tracking_enabled = False
                self.target_valid = False  # ignore current target until new is received

                try:
                    ########### Actual call of rotator command ###########
                    self.rotator.stop()

                except RotatorError as e:
                    self.log.error(
                        "Failed to stop rotator: %s", str(e), exc_info=True)
                    return

                self.log.info("Rotator is now in manual mode")

            else:
                raise RPCError("Invalid mode %s" % mode)

            # Do immediate update for the rotator
            await self.check_state()

        elif request_name == "rpc.rotate":
            """
                Manual rotating
            """

            target = (float(request_data['az']), float(request_data['el']))

            # Disable automatic tracking
            self.tracking_enabled = False

            try:
                if "shortest" in request_data:
                    self.set_target_position(target, request_data["shortest"])

                else:
                    self.set_target_position(target)

            except RotatorError as e:
                self.log.error(
                    "Failed to update target position! %s",
                    str(e), exc_info=True)
                return

        elif request_name == "rpc.stop":
            """
                Rotator stop
            """
            # Stop tracking mode and
            self.tracking_enabled = False

            # Send stop command
            self.rotator.stop()

        elif request_name == "rpc.reset_position":
            target = float(request_data['az']), float(request_data['el'])
            with open("cal_history.txt", "a+") as history_file:
                now = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())
                history_file.write(f"{now}: Az: {self.current_position[0]} El: {self.current_position[1]} "
                                   f"=> Az: {target[0]} El: {target[1]}\n")
            self.rotator.reset_position(target[0], target[1])
            return

        elif request_name == "rpc.get_position_target":
            ########### Actual call of rotator command ###########
            ret = self.rotator.get_position_target()
            return {"position_target": ret}

        elif request_name == "rpc.get_position_range":
            ########### Actual call of rotator command ###########
            ret = self.rotator.get_position_range()
            return {"position_range": ret}

        elif request_name == "rpc.set_position_range":
            ########### Actual call of rotator command ###########
            ret = self.rotator.set_position_range(float(request_data["az_min"]),
                                                  float(request_data["az_max"]),
                                                  float(request_data["el_min"]),
                                                  float(request_data["el_max"]))
            return {"position_range": ret}

        elif request_name == "rpc.get_dutycycle_range":
            ########### Actual call of rotator command ###########
            ret = self.rotator.get_dutycycle_range()
            return {"dutycycle_range": ret}

        elif request_name == "rpc.set_dutycycle_range":
            ########### Actual call of rotator command ###########
            self.rotator.set_dutycycle_range(int(request_data["az_min"]),
                                             int(request_data["az_max"]),
                                             int(request_data["el_min"]),
                                             int(request_data["el_max"]))

        elif request_name == "rpc.status":
            """
                Get rotator status message
            """
            return self.get_status_msg()

        else:
            raise RPCError("No such command: %s" % request_name)

    @queue()
    @bind(exchange="event", routing_key="*")
    @bind(exchange="tracking", routing_key="target.position")
    def tracking_event(self, message: aiormq.abc.DeliveredMessage):
        """
            Automatic events for tracking
        """

        # Don't do anything automatic if the tracking is not enabled
        if not self.tracking_enabled:
            return

        try:
            event_body = json.loads(message.body)
        except ValueError as e:
            self.log.error('Failed to parse json: %s\n%s',
                           e.args[0], message.body)
            return

        if self.prefix not in event_body.get('rotators', []):
            return

        routing_key = message.delivery['routing_key']
        self.log.debug("tracking_event: %s: %r", routing_key, event_body)

        if routing_key == "target.position":
            """
                Satellite position update during the pass
            """

            new_target = (float(event_body['az']) % 360,
                          float(event_body['el']))

            if new_target[1] < self.threshold:
                new_target = (new_target[0], self.threshold)

            try:
                self.set_target_position(new_target, shortest_path=True)
            except RotatorError as e:
                self.log.error(
                    "Failed to update target position! %s",
                    e.args[0], exc_info=True)
                return

        elif routing_key == "preaos":
            """
                At preAOS determine the optimal initial azimuth within the
                full [-90:450] interval. Initial elevation is always min_elevation + threshold.
            """
            # Make sure azimuths are in range [0, 360]
            aos_az = event_body["az_aos"] % 360
            max_az = event_body["az_max"] % 360
            los_az = event_body["az_los"] % 360

            aos_el = self.rotator.az_dependent_min_el(aos_az) + self.threshold

            ### Might be needed to adapt this when using with different GS ###
            # Over the north-west to east or vice versa or
            # Over the north-east to west or vice versa
            if (270 < aos_az < 360 and los_az < 180) or \
                    (270 < los_az < 360 and aos_az < 180) or \
                    (0 < aos_az < 90 and los_az > 180) or \
                    (0 < los_az < 90 and aos_az > 180):
                # Check whether azimuth at max elevation is >180
                if max_az > 180:
                    aos_az = (aos_az + 360 if aos_az < 90 else aos_az)
                else:
                    aos_az = (aos_az - 360 if aos_az > 270 else aos_az)

            initial_target = (aos_az, aos_el)

            # Initial positioning of the rotator
            try:
                # Speed up the azimuth rotation speed
                self.log.info("DEBUG raise duty cycle up to 100")
                self.rotator.set_dutycycle_range(az_duty_max=100)

                # Needs to go to position defined by full [-90, +450] angle
                self.set_target_position(initial_target, shortest_path=False)

            except RotatorError as e:
                self.log.error(
                    "Failed to set initial target position! %s",
                    str(e), exc_info=True)
                return

            self.log.info("Rotator ready for the next pass (%s)",
                          event_body.get("satellite", "-"))

        elif routing_key == "aos":
            # Set to default rotation speed
            self.log.info("DEBUG set duty cycle back to 60")
            self.rotator.set_dutycycle_range(az_duty_max=60)

        elif routing_key == "los":
            """
                At LOS stop the rotator
            """

            try:
                ########### Actual call of rotator command ###########
                self.rotator.stop()

            except RotatorError as e:
                self.log.error("Failed to reset target position! %s",
                    e.args[0], exc_info=True)
                return


if __name__ == "__main__":
    Rotator(
        driver="aalto",
        address="127.0.0.1:4533",
        amqp_url="amqp://guest:guest@localhost:5672/",
        prefix="uhf",
        tracking_enabled=True,
        debug=True
    ).run()
