import unittest
import json
from ...core.basemodule_async import BaseModule, queue, bind, RPCRequestError


class HousekeepingTester(BaseModule):
    """
        Tester module to create RPC calls
    """

    def __init__(self, **kwargs):
        BaseModule.__init__(self, **kwargs)
        self.logs = []
        self.hk_updates = []

    def store_value(self, **kwargs):
        """
            params: satellite, housekeeping, metadata
            Inside housekeeping list {id, raw or value}
        """
        return self.publish(kwargs, exchange="housekeeping", routing_key="store")

    def get_history(self, **kwargs):
        """
            Get housekeeping history for given variable/id
            params: satellite, id, timespan, after, before, max_entries
        """
        return self.send_rpc_request("housekeeping", "rpc.history", kwargs)

    def get_latest(self, **kwargs):
        """
            Get all latest housekeeping values
        """
        return self.send_rpc_request("housekeeping", "rpc.latest", kwargs)

    @queue()
    @bind("housekeeping", "update")
    def update_callback(self, message):
        """
            Collect all housekeeping updates to be checked
        """
        self.hk_updates.append(json.loads(message.body))

    @queue()
    @bind("log", "*")
    def log_callback(self, message):
        """
            Collect all logs so possible log entries can be tested in the unit tests
        """
        self.logs.append(json.loads(message.body))


class TestHousekeepingBackend(unittest.TestCase):
    def setUp(self):
        self.rpc = HousekeepingTester(amqp_url="localhost:5672", amqp_user="guest", amqp_password="guest")

    def test_latest(self):
        self.rpc.get_latest(satellite="aalto-1")

        # invalid satellite
        with self.assertRaises(RPCRequestError) as cm:
            self.rpc.get_latest(satellite="Apollo 11")

        #self.assertEqual(cm.exception.error_code, 3)

    def test_history(self):
        self.rpc.get_history(satellite="aalto-1")

    def test_housekeeping_storing(self):
        pass
        # self.rpc.store_value()
        # check sefl.rpc.hk_updates

    def test_limits(self):
        pass


if __name__ == "__main__":
    # unittest.main()

    hk = HousekeepingTester(amqp_url="amqp://guest:guest@localhost:5672/", amqp_user="guest", amqp_password="guest", debug=True)
    print(hk.get_latest(satellite="aalto-1"))
