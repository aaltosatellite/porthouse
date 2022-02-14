
import unittest
import time
import json
import socket

from porthouse.core.testmodule import TestModule, queue, bind
from .point_tracker import calculate_azimuth_elevation


class PointTrackerTester(TestModule):
    """
    Tester module to create RPC calls
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.logs = []
        self.pointings = []

    def set_position(self, **kwargs):
        """
        params: lon, lat, alt
        """
        return self.send_rpc_request("tracking", "rpc.set_position", kwargs)

    @queue()
    @bind("tracking", "target.position")
    def pointings_callback(self, message):
        """
            Collect all pointing messages
        """
        print(message.body)
        self.pointings.append(json.loads(message.body))

    @queue()
    @bind("log", "*")
    def log_callback(self, message):
        """
            Collect all logs so possible log entries can be tested in the unit tests
        """
        self.logs.append(json.loads(message.body))


class TestPointTracking(unittest.TestCase):
    """
        Testcase for PointTracker module
    """

    def setUp(self):
        self.rpc = PointTrackerTester(
            amqp_host="localhost:5672", amqp_user="guest", amqp_password="guest")

    def test_targetting(self):
        #self.rpc.set_position(lon=0, lat=0, alt=0)
        pass


if __name__ == "__main__":
    # unittest.main()

    #rpc = PointTrackerTester(amqp_host="localhost:5672", amqp_user="guest", amqp_password="guest")
    #rpc.set_position(lon=0, lat=0, alt=0)

    gs = (60.1888, 24.8307, 50)
    balloon = (59.91658, 26.95776, 3200)
    print(calculate_azimuth_elevation(gs, balloon))
