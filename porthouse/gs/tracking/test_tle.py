import unittest
import time
import json


from porthouse.core.testmodule import TestModule, queue, bind, RPCRequestError


class TLETester(TestModule):
    """
    Tester module to create RPC calls
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.broadcasts = []
        self.logs = []

    def update_tle(self):
        return self.send_rpc_request("tracking", "tle.rpc.update")

    def request_tle(self, **kwargs):
        return self.send_rpc_request("tracking", "tle.rpc.get_tle", kwargs)

    @queue()
    @bind("tracking", "tle.updated")
    def updated_callback(self, message):
        """
        """
        self.broadcasts.append(json.loads(message.body))

    @queue()
    @bind("log", "*")
    def log_callback(self, message):
        """
        Collect all logs so possible log entries can be tested in the unit tests
        """
        self.logs.append(json.loads(message.body))


class TestTLE(unittest.TestCase):
    """
        Testcase for TLE module
    """

    def setUp(self):
        self.rpc = TLETester(amqp_url="amqp://guest:guest@localhost:5672/")

    def test_update(self):

        # 1) Request old TLE line to see

        # 2) Trigger TLE update!
        self.rpc.update_tle()
        self.rpc.wait_messages(10)

        # 3) Check logs
        ok = False
        for log_entry in self.rpc.logs:
            self.assertEqual(log_entry["level"], "info")
            if log_entry["module"] == "TLEUpdater" and log_entry["level"] == "info":
                ok = True
        self.assertTrue(ok, "No info message found!")

        # 4) Check that the TLE line was updated

    def test_satellite_listing(self):
        # 1) Request satellite list
        ret = self.rpc.get_satellites()

        # 2) Check result
        self.assertIsInstance(ret, dict)
        self.assertTrue("satellites" in ret)
        self.assertIsInstance(ret["satellites"], list)
        self.assertGreater(len(ret["satellites"]), 0)

    def test_request(self):
        # 1) Request EstCube's TLE lines
        ret = self.rpc.request_tle(satellite="ESTCUBE 1")

        # 2) Check lines
        self.assertIsInstance(ret, dict)
        self.assertEqual(ret["tle0"], "ESTCUBE 1")
        self.assertEqual(len(ret["tle1"]), 69)
        self.assertEqual(len(ret["tle2"]), 69)

    def test_invalid_satellite(self):

        # Check that invalid satellite name cause RPC Exception
        with self.assertRaises(RPCRequestError) as cm:
            self.rpc.request_tle(satellite="APOLLO 11")

        #self.assertEqual(cm.exception.error_code, 3)

    def test_check_logs(self):
        for log_entry in filter(lambda x: x["module"] == "TLEUpdate", self.rpc.logs):
            self.assertNotEqual(logs["level"], "info")



if __name__ == "__main__":
    unittest.main()
