"""
    Scheduler
"""

import asyncio
import enum
import json
import yaml
from datetime import datetime, timedelta
import skyfield.api as skyfield

from porthouse.core.config import cfg_path
from porthouse.core.basemodule_async import BaseModule, RPCError, queue, rpc, bind
from porthouse.gs.tracking.utils import *


class PassStatus(enum.Enum):
    """ Pass states """
    ERROR = -1
    NOT_SCHEDULED = 0
    SCHEDULED = 1
    ONGOING = 2
    SUCCESS = 3
    DELETED = 4


class Scheduler(BaseModule):
    """
    """

    PREAOS_PERIOD = 120  # [s]
    TIME_DELTA = 180  # [s]

    def __init__(self, schedule_file="schedule.json", **kwarg):
        """
        Initialization
        """
        super().__init__(**kwarg)

        self.gs: skyfield.Topos = None
        self.schedule = []
        self.schedule_file = schedule_file


        loop = asyncio.get_event_loop()
        loop.create_task(self.setup())


    async def setup(self):
        """
        """

        tracker_cfg = yaml.load(open(cfg_path("groundstation.yaml"), "r"), Loader=yaml.Loader)

        self.gs_name = tracker_cfg["name"]
        self.gs = skyfield.Topos(
            latitude=skyfield.Angle(degrees=tracker_cfg["lat"]),
            longitude=skyfield.Angle(degrees=tracker_cfg["lon"]),
            elevation_m=tracker_cfg["elevation"]
        )


        tle_list = await self.send_rpc_request("tracking", "tle.rpc.get_tle")
        self.sat_list = [tle["name"] for tle in tle_list["tle"]]

        self.scheduled_sats = ["Aalto-1", "Suomi 100"]
        for sat in self.scheduled_sats:
            if sat not in self.sat_list:
                raise RuntimeError("No TLEs configured for %s", sat)

        self.schedule = []
        self.read_schedule()

        while True:
            self.check_schedule()
            await asyncio.sleep(1)



    def read_schedule(self):
        """
        Read schedule from json file
        """

        # Read schedule
        try:
            with open(self.schedule_file, "r") as fp:
                schedule = json.load(fp)
                schedule = schedule["schedule"]
        except Exception as e:
            self.log.error("Failed to read ", exc_info=True)
            return

        #
        schedule = []
        for elem in schedule:
            schedule.append(Pass.from_dict(elem))
        self.schedule = schedule


    def write_schedule(self):
        """
        Write schedule to JSON file
        """

        schedule = []
        for entry in self.schedule:

            # Skip entries which are older than 24 hours
            if (datetime.utcnow() - entry.los) > timedelta(hours=24):
                if entry.status == PassStatus.DELETED:
                    continue

            schedule.append(entry.to_dict())

        # Save schedule to JSON file
        try:
            with open(self.schedule_file, "w") as fp:
                json.dump({"schedule": schedule}, fp, indent=4)
        except:
            self.log.error("Failed to write schedule file", exc_info=True)


    def check_schedule(self):
        """
        Checks schedule for passes.
        """

        self.read_schedule()
        now = datetime.utcnow().timestamp()

        for elem in self.schedule:
            if now >= elem.los:
                if elem.status != PassStatus.ERROR:
                    elem.status = PassStatus.DELETED

            elif now >= elem.aos - self.PREAOS_PERIOD:
                if elem.gs != self.gs_name:
                    continue

                if elem.status == PassStatus.SCHEDULED:
                    self.start_pass(elem)
                    elem.status = PassStatus.ONGOING

        self.schedule = sorted(self.schedule, key = lambda elem: elem.aos)

        self.write_schedule()


    def create_schedule(self):
        """
        Create schedule from predicting passes.
        """
        for sat in self.scheduled_sats:
            passes = self.predict_passes(sat)
            self.add_pass(passes)


    def get_schedule(self, name=None, period=None, unscheduled=False):
        """
        Get schedule
        """

        schedule = []
        self.read_schedule()

        for elem in self.schedule:
            if name is not None:
                if elem.name != name:
                    continue

            if period is not None:
                if (datetime.utcnow() - elem.los) >= timedelta(hours=1):
                    continue

            if unscheduled and elem.status != PassStatus.NOT_SCHEDULED:
                continue

            if not unscheduled and elem.status != PassStatus.SCHEDULED:
                continue

            schedule.append(elem.to_dict())

        return schedule


    def broadcast_changed_schedule(self):
        """
        Broadcast when scheduled is changed.
        """

        self.publish({
            "time": datetime.utcnow().isoformat(),
            "schedule": [ entry.as_dict() for entry in self.schedule ]
        }, exchange="scheduler", routing_key="schedule.changed")


    def add_pass(self, sc_passes):
        """
        Add list of passes to the schedule.

        Args:
            passes: List of Pass objects to be added to schedule
        """

        self.read_schedule()
        if isinstance(sc_passes, Pass):
            sc_passes = [sc_passes]

        for sc_pass in sc_passes:
            sc_pass = self.check_overlap(sc_pass)

            if sc_pass is None:
                continue

            if sc_pass.is_valid():
                self.schedule.append(sc_pass)

        self.write_schedule()
        self.broadcast_changed_schedule()


    def modify_pass_status(self, sc_pass):
        """
        Modifies pass status that is in the schedule.
        """
        aos_search = sc_pass.aos - self.TIME_DELTA
        los_search = sc_pass.los + self.TIME_DELTA

        self.read_schedule()
        for sd_pass in self.schedule:
            if sc_pass.name != sd_pass.name:
                continue

            if sc_pass.gs != sd_pass.gs:
                continue

            if sd_pass.aos >= aos_search and sd_pass.los <= los_search:
                sd_pass.status = sc_pass.status

        self.write_schedule()
        self.broadcast_changed_schedule()


    def check_overlap(self, sc_pass):
        """
        Checks whether pass overlaps with already scheduled pass

        If new pass is overlapping, pass is modified to give scheduled pass
        precedence.
        """

        for sd_pass in self.schedule:
            if sc_pass.is_inside(sd_pass):
                return None
            elif sc_pass.is_outside(sd_pass):
                return None
            elif sc_pass.is_reaching_into(sd_pass):
                sc_pass.los = sd_pass.aos - self.PREAOS_PERIOD
            elif sc_pass.is_reaching_out(sd_pass):
                sc_pass.aos = sd_pass.los + 1

        return sc_pass


    async def broadcast_pass(self, sc_pass):
        """
        Broadcast pass information of current pass
        """
        await self.publish(sc_pass.to_dict(), exchange="scheduler", routing_key="pass.current")
        self.log.debug("Current pass of %s at GS %s: AOS %rs LOS %s",
                       sc_pass.name, sc_pass.gs, sc_pass.aos, sc_pass.los)


    async def start_pass(self, sc_pass):
        """
        Broadcast pass info, set rotators automatic and change target
        """

        self.log.debug("Starting pass of %s at GS %s", sc_pass.name, sc_pass.gs)
        await self.broadcast_pass(sc_pass)

        await self.publish({
            "mode": "automatic"
        }, exchange="rotator", routing_key="uhf.rpc.tracking")

        await self.publish({
            "satellite": sc_pass.name
        }, exchange="tracking", routing_key="rpc.set_target")


    @rpc()
    @bind("scheduler", "rpc.#")
    def rpc_handler(self, request_name, request_data):
        """
            Parse command
        """
        if request_name == "rpc.get_schedule":
            return self.get_schedule(**request_data)

        elif request_name == "rpc.add_pass":
            #
            # Schedule new pass
            #

            name = request_data["name"]
            gs = request_data["gs"]
            aos = request_data["aos"]
            los = request_data["los"]

            if name in self.sat_list:
                sc_pass = Pass(name, gs, aos, los)
                sc_pass.status = PassStatus.SCHEDULED
                self.add_pass(sc_pass)

        elif request_name == "rpc.remove_pass":
            #
            # Remove pass from the schedule
            #

            name = request_data["name"]
            gs = request_data["gs"]
            aos = request_data["aos"]
            los = request_data["los"]

            if name in self.sat_list:
                sc_pass = Pass(name, gs, PassStatus.DELETED, aos, los)
                sc_pass.status = PassStatus.DELETED
                self.modify_pass_status(sc_pass)

        elif request_name == "rpc.schedule_pass":
            #
            #
            #

            name = request_data["name"]
            gs = request_data["gs"]
            aos = request_data["aos"]
            los = request_data["los"]

            if name in self.sat_list:
                sc_pass = Pass(name, gs, PassStatus.SCHEDULED, aos, los)
                self.modify_pass_status(sc_pass)

        elif request_name == "rpc.unschedule_pass":
            name = request_data["name"]
            gs = request_data["gs"]
            aos = request_data["aos"]
            los = request_data["los"]

            if name in self.sat_list:
                sc_pass = Pass(name, gs, PassStatus.NOT_SCHEDULED, aos, los)
                self.modify_pass_status(sc_pass)

        elif request_name == "rpc.get_sat_pass":
            #
            # List all passes for the satellite
            #

            if "name" not in request_data:
                raise RPCError("No satellite name given")

            passes = self.predict_passes(**request_data)
            return [ elem.to_dict() for elem in passes ]

        raise RPCError("Unknown command")



    def find_passes(self, sat, gs, start_time, period=None, min_elevation=0):
        """
        """

        if start_time is None:
            t = datetime.utcnow().replace(tzinfo=utc)
        elif isinstance(start_time, datetime):
            t = start_time.replace(tzinfo=utc)
        elif isinstance(start_time, skyfield.Time):
            t = start_time.utc_datetime()
        else:
            raise ValueError("Invalid start_time type")

        if period is None:
            end_time = t + timedelta(hours=24)
        elif isinstance(period, timedelta):
            end_time = t + period
        else:
            raise ValueError("Invalid period type")

        el, _, _ = (sat - gs).at(ts.utc(t)).altaz()
        if el.degrees > 0:
            t -= timedelta(minutes=30)

        t_event, events = sat.find_events(gs, ts.utc(t), ts.utc(end_time), min_elevation)
        t_aos, az_aos, t_max, el_max, t_los, az_los = None, None, None, None, None, None

        pass_list = []
        for t, event in zip(t_event, events):
            el, az, _ = (sat - gs).at(t).altaz()

            if event == 0: # AOS
                t_aos, az_aos = t.utc_datetime(), az.degrees
            elif event == 1: # Max
                t_max, el_max = t.utc_datetime(), el.degrees
            elif event == 2: # LOS
                t_los, az_los = t.utc_datetime(), az.degrees

                if t_aos and t_max:
                    pass_list.append(tuple(t_aos, az_aos, t_max, el_max, t_los, az_los))

                t_aos, az_aos, t_max, el_max, t_los, az_los = None, None, None, None, None, None

        return pass_list


    async def predict_passes(self, name, period=24.0):
        """
            Predict upcoming passes of satellite w.r.t. to ground station.
        """
        request = {"satellite": name}
        tle = await self.send_rpc_request("tracking", "tle.rpc.get_tle", request)

        satellite = ephem.readtle(tle["name"], tle["tle1"], tle["tle2"])

        start = ephem.now()
        self.gs.date = start

        passes = []

        satellite.compute(self.gs)

        # If a pass has already started go little bit back in time.
        if satellite.alt > 0:
            self.gs.date -= 15 * ephem.minute
            satellite.compute(self.gs)

        # Calculate passes for the given prediction period
        while self.gs.date < ephem.Date(start + period * ephem.hour):

            try:
                tr, _, tt, _, ts, _ = next_pass = self.gs.next_pass(satellite)

                if tr == None:
                    raise ValueError

                aos = ephem.localtime(tr).timestamp()
                los = ephem.localtime(ts).timestamp()

                sc_pass = Pass(satellite.name, self.gs_name,
                               PassStatus.NOT_SCHEDULED, aos, los, satellite._orbit)

                # Calculate azimuth at max elevation
                self.gs.date = tt
                satellite.compute(self.gs)
                next_pass = (next_pass[0], next_pass[1], next_pass[2],
                             satellite.az, next_pass[3], next_pass[4], next_pass[5])

                passes.append(sc_pass)

            except ValueError:
                ts = ephem.Date(self.gs.date + ephem.hour)

            self.gs.date = ephem.Date(ts + 0.1 * ephem.hour)

        # Make sure we have some kind of result
        if len(passes) == 0:
            self.log.warning("No future passes were found for %s!", satellite.name)
            return

        # Pick pass parameters
        #tr, _, tt, _, altt, ts, _ = passes[0]
#
        # Construct info message
        # msg = "Next pass for %s (Orbit %d)" % (
        #    satellite.name, satellite._orbit)
        #msg += ", AOS: %s" % ephem.localtime(tr).strftime("%Y-%m-%d %H:%M:%S")
        #msg += ", LOS: %s" % ephem.localtime(ts).strftime("%Y-%m-%d %H:%M:%S")
        # msg += ", Pass length: %s" % (ephem.localtime(ts) -
        #                              ephem.localtime(tr))
        #msg += ", Maximum elevation: %d degrees" % math.degrees(altt)
        # self.log.info(msg)
#
        # if self.debug:
        #    print("--------------------------------------------------------------")
        #    print("      Date/Time        Elev/Azim    Alt     Range     RVel    ")
        #    print("--------------------------------------------------------------")
#
        #    self.gs.date = tr
#
        #    while self.gs.date <= ts:
        #        satellite.compute(self.gs)
#
        #        print("{0} | {1:4.1f} {2:5.1f} | {3:5.1f} | {4:6.1f} | {5:+7.1f}".format(
        #            ephem.localtime(self.gs.date).strftime(
        #                "%Y-%m-%d %H:%M:%S"),
        #            math.degrees(satellite.alt),
        #            math.degrees(satellite.az),
        #            satellite.elevation/1000.,
        #            satellite.range/1000.,
        #            satellite.range_velocity))
#
        #        self.gs.date = ephem.Date(self.gs.date + 20 * ephem.second)
#
        return passes


if __name__ == '__main__':
    Scheduler(
        amqp_url="amqp://guest:guest@localhost:5672/",
        schedule_file=".schedule.json",
        debug=True
    ).run()
