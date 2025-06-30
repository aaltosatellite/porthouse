#!/usr/bin/env python3

import unittest
import json
import time
from porthouse.core.basemodule_async import BaseModule, RPCError, rpc, queue, bind, RPCRequestError

class RotatorTester(BaseModule):
    """
        Tester module to create RPC calls
    """

    def __init__(self, prefix, **kwargs):
        BaseModule.__init__(self, **kwargs)
        self.prefix = prefix
        self.statuses = []
        self.logs = []

    def send_event(self, etype, **kwargs):
        """
            Input for rotator module!
        """
        return self.publish(kwargs, exchange="event", routing_key=etype)

    def send_pointing(self, **kwargs):
        """
            Input for rotator module!
        """
        return self.publish(kwargs, exchange="tracking", routing_key="target.position")

    def set_mode(self, **kwargs):
        """
            params: mode("automatic", "manual")
        """
        return self.send_rpc_request(self.prefix + "rotator", self.prefix + "rpc.history", kwargs)

    def rotate(self, **kwargs):
        """
            params: az, el
        """
        return self.send_rpc_request("rotator", self.prefix + "rpc.rotate", kwargs)

    def stop(self, **kwargs):
        """
        """
        return self.send_rpc_request("rotator", self.prefix + "rpc.stop", kwargs)

    @queue()
    @bind(exchange="rotator", routing_key="#.status")  # any prefix!
    def update_callback(self, message):
        """
            Collect all status messages
        """
        self.statuses.append(json.loads(message.body))

    @queue()
    @bind(exchange="log", routing_key="*")
    def log_callback(self, message):
        """
            Collect all logs so possible log entries can be tested in the unit tests
        """
        if message.delivery_info["correlation_id"].startswith(self.prefix):
            self.logs.append(json.loads(message.body))


class TestRotator(unittest.TestCase):
    def setUp(self):
        self.rpc = RotatorTester(prefix="uhf", amqp_host="localhost:5672", amqp_user="guest", amqp_password="guest")

    def test_modes(self):

        self.rpc.set_mode(mode="automatic")
        self.rpc.set_mode(mode="manual")

        # invalid mode
        with self.assertRaises(RPCRequestError) as cm:
            self.rpc.set_mode(mode="banana")

    def test_rotate(self):
        self.rpc.set_mode(mode="manual")

        self.rpc.statuses = []
        time.sleep(1)
        self.rpc.rotate(az=30, el=90)
        time.sleep(2)

        # Check that the rotator has moved
        first, last = self.rpc.statuses[1], self.rpc.statuses[-1]
        self.assertNotEqual(first["az"], last["az"])
        self.assertNotEqual(first["el"], last["el"])

    def test_tracking(self):
        self.rpc.set_mode(mode="automatic")

        self.rpc.statuses = []
        time.sleep(1)

        self.rpc.send_pointing(az=30, el=90, velocity=213)
        time.sleep(2)

        # Check that the rotator has moved
        first, last = self.rpc.statuses[1], self.rpc.statuses[-1]
        self.assertNotEqual(first["az"], last["az"])
        self.assertNotEqual(first["el"], last["el"])

    def test_stop(self):
        self.rpc.set_mode(mode="automatic")

        self.rpc.statuses = []
        self.rpc.rotate(az=30, el=90)
        time.sleep(1)
        self.rpc.stop()
        time.sleep(1)

        # Check that the rotator has moved
        first, last = self.rpc.statuses[1], self.rpc.statuses[-1]
        self.assertNotEqual(first["az"], last["az"])
        self.assertNotEqual(first["el"], last["el"])


if __name__ == "__main__":
    unittest.main()

    #rot = RotatorTester(amqp_host="localhost:5672", amqp_user="guest", amqp_password="guest")
    #rot.rotate(az=12.0, el=45.0)
