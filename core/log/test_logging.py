#!/usr/bin/env python3
import unittest
import time
import json
import socket
from porthouse.core.static_basemodule import BaseModule, rpc, queue, bind


class LogServerTester(BaseModule):
    """
        Tester module to create RPC calls
    """

    def __init__(self, **kwargs):
        BaseModule.__init__(self, **kwargs)
        self.logs = []

    def wait_messages(self, timeout=1):
        end = time.time() + timeout
        while end > time.time():
            try:
                self.connection.drain_events(timeout=1)
            except socket.timeout:
                pass

    def get_history(self, **kwargs):
        """
            Request log history!
            possible params: before
        """
        return self.send_rpc_request("log", "rpc.get_history", kwargs)

    @queue()
    @bind(exchange="log", routing_key="*")
    def log_callback(self, message):
        """
            Collect all logs so possible log entries can be tested in the unit tests
        """
        self.logs.append(json.loads(message.body))


#new system parses from amqp_url
class TestTLEServer(unittest.TestCase):
    """
        Testcase for TLE module
    """

    def setUp(self):
        self.rpc = LogServerTester(amqp_url="amqp://guest:guest@localhost:5672/")
        time.sleep(0.2)

    def test_producing(self):
        for i in range(40):
            self.rpc.log.warning("testing #%d" % i)

    def test_requesting(self):

        # 1: Spam content to the log
        for i in range(40):
            self.rpc.log.warning("testing #%d" % i)

        # 2: Request logs
        first_request = self.rpc.get_history()
        self.assertEqual(len(first_request["entries"]), 30)

        """for r in first_request["entries"]:
            print(r["id"], r["message"])
        print("")"""

        # 3: Request more logs
        second_request = self.rpc.get_history(before=first_request["entries"][2]["id"])

        """for r in second_request["entries"]:
            print(r["id"], r["message"])"""

        self.assertGreater(len(second_request["entries"]), 9)
        self.assertEqual(first_request["entries"][0]["id"], second_request["entries"][-2]["id"])
        self.assertEqual(first_request["entries"][1]["id"], second_request["entries"][-1]["id"])


if __name__ == "__main__":
    unittest.main()
