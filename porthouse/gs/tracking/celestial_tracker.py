"""

    Celestial tracker module

    Untested and not in use!

"""

import json
import math
import ephem
from configparser import ConfigParser
from basemodule import *


class CelestialTracker(BaseModule):
    """
    """

    #
    BODY_CLASSES = {
        "sun": ephem.Sun,
        "moon": ephem.Moon,
        "star": ephem.star
    }

    def __init__(self,
                 cfg_file,
                 **kwarg):
        """
            Initialize module
        """
        BaseModule.__init__(self, **kwarg)
        self.target = None
        self.target_str = "None"

        # Open config file
        cfg = ConfigParser()
        cfg.read_file(open(cfg_file))

        # Create observer from config file
        self.obs = ephem.Observer()
        self.obs.lat = math.radians(cfg.getfloat("observer", "latitude"))
        self.obs.long = math.radians(cfg.getfloat("observer", "longitude"))
        self.obs.elevation = cfg.getfloat("observer", "elevation")

        # Add update add_timeout
        self.add_timeout(1, self.update)

    @rpc()
    @bind("tracking", "celestial.rpc.#")
    def rpc_handler(self, request_name, request_data):
        """
            Handle commands
        """

        if request_name == "celestial.rpc.set_target":

            self.target = None
            self.target_str = "None"

            if "target" not in request_data:
                raise RPCError("No target specified!")

            if request_data["target"] == "radec":

                try:
                    ra = ephem.degrees(float(request_data["ra"]))
                    dec = ephem.degrees(float(request_data["dec"]))
                except (KeyError, ValueError):
                    raise RPCError("No target specified!")

                self.target = ephem.FixedBody(ra=ra, dec=dec)
                self.target_str = "Radec(%f°, %f°)" % (ra, dec)

            elif request_data["target"] == "star":
                self.target = ephem.star(request_data["star"])
                self.target_str = "Star (%s)" % request_data["star"]

            elif request_data["target"] in self.BODY_CLASSES:
                self.target = self.BODY_CLASSES[request_data["target"]]()
                self.target_str = request_data["target"]

            else:
                raise RPCError("Invalid target \"%s\"" %
                               request_data["target"])

            self.obs.date = ephem.now()
            self.target.compute(self.obs)

        elif request_name == "celestial.rpc.stop":
            self.target = None
            self.target_str = "None"

    def update(self):
        """
            Update tracking calculations
        """

        # Tracking state machine:
        if self.target:

            # Update current prediction
            self.obs.date = ephem.now()
            self.target.compute(self.obs)

            # Broadcast spacecraft position
            self.broadcast_pointing(math.degrees(self.target.az),
                                    math.degrees(self.target.alt))

        self.broadcast_status()
        self.add_timeout(2, self.update)

    def broadcast_pointing(self, az, el):
        """
            Broadcast pointing information
        """

        if az > 180:
            az -= 360

        self.publish({
            "az": round(az, 1),
            "el": max(0, round(el, 1)),
            "velocity": 0
        }, exchange="tracking", routing_key="target.position")

    def broadcast_status(self):
        """
            Broadcast tracker status
        """

        self.publish({
            "status": "Tracking" if self.target else "No target",
            "target": self.target_str,
        }, exchange="tracking", routing_key="celestial_tracker.status")


if __name__ == "__main__":
    CelestialTracker(cfg_file="tracker.cfg",
                     amqp_url="amqp://guest:guest@localhost:5672/",
                     debug=True).run()
