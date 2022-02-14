#!/usr/bin/env python3
import unittest
import time
import json
import socket
from basemodule import *


class CelestialTester(BaseModule):
    """
        Tester module to create RPC calls
    """

    def __init__(self, **kwargs):
        BaseModule.__init__(self, **kwargs)
        self.logs = []
        self.pointings = []
        self.statuses = []

    def wait_messages(self, timeout=1):
        end = time.time() + timeout
        while end > time.time():
            try:
                self.connection.drain_events(timeout=1)
            except socket.timeout:
                pass

    def set_target(self, **kwargs):
        return self.send_rpc_request("tracking", "celestial.rpc.set_target", kwargs)

    @queue()
    @bind("tracking", "target.position")
    def pointings_callback(self, message):
        """
            Collect all pointing messages
        """
        print(message.body)
        self.pointings.append(json.loads(message.body))

    @queue()
    @bind("tracking", "celestial.status")
    def status_callback(self, message):
        """
            Collect all pointing messages
        """
        self.statuses.append(json.loads(message.body))

    @queue()
    @bind("log", "*")
    def log_callback(self, message):
        """
            Collect all logs so possible log entries can be tested in the unit tests
        """
        self.logs.append(json.loads(message.body))


class TestCelestialTracking(unittest.TestCase):
    """
        Testcase for CelestialTracker module
    """

    def setUp(self):
        self.rpc = CelestialTester(
            amqp_host="localhost:5672", amqp_user="guest", amqp_password="guest")

    def test_targetting(self):

        # 1)
        self.rpc.set_target(target="sun")
        self.rpc.wait_messages(2)
        self.rpc.pointings = []

        # 2)
        self.rpc.set_target(target="moon")
        self.rpc.wait_messages(2)
        self.rpc.pointings = []

        # 3)
        self.rpc.set_target(target="radec", ra=12.0, dec=42.13)
        self.rpc.wait_messages(2)
        self.rpc.pointings = []

        # Check that invalid satellite name cause RPC Exception
        with self.assertRaises(RPCRequestError) as cm:
            self.rpc.set_target(target="Orange")


if __name__ == "__main__":

    unittest.main()

    #rpc = CelestialTester(amqp_host="localhost:5672", amqp_user="guest", amqp_password="guest", debug=True)
    # rpc.set_target(target="sun")
    #rpc.set_target(target="radec", ra=12.0, dec=22.13)
    # rpc.wait_messages(10)
