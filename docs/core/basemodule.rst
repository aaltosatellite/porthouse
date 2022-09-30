.. highlight:: python

BaseModule
==========



The BaseModule is the base class for all the porthouse software modules.

The class implements the basic functionalities such as:


* Common configuration system
* Standard logging methods and setup of logging handlers
* Connecting to AMQP server
* Publishing and subscribing to AMQP message queues
* JSON-RPC server and client functionalities


.. automodule:: porthouse.core.basemodule.BaseModule
   :members:
   :undoc-members:




.. highlight:: python
  :linenothreshold: 5


Binding to queue
----------------

.. code-block:: python

    from porthouse.core.basemodule import *

    class MyModule(BaseModule):
        ...
        def __init__(self, **kwargs):
            BaseModule.__init__(self, **kwargs)

        @queue()
        @bind("exchange", "*.routing_key")
        def queue_callback(self, msg):
            self.log.info("I received: %r", msg.body)




Sending RPCs
------------

.. code-block:: python

    class MyModule(BaseModule):
        # ...

        def something(self);
            try:
                ret = self.send_rpc_request(
                    exchange="service",
                    routing_key="rpc.get",
                    query_data={
                        arg1: 1,
                        arg2: "foo"
                    }
                )

                print("Success", ret)

            expect RPCRequestError as e:
                print("RPC failed and returned", e)

            expect RPCRequestTimeout as e:
                print("RPC failed and returned", e)



Receiving RPCs
--------------

.. code-block:: python

    class MyModule(BaseModule):
        # ...

        @rpc()
        @bind("service", "rpc.*")
        def rpc_handler(self, request_name, request_data):
            """
                RPC Callback
            """

            if request_name == "rpc.echo":
                return request_data

            elif request_name == "rpc.error":
                raise RPCError("I'm doomed to fail!")

            return {
                "answer": 42
            }

If the RPC_handler fails to an unhandled exception, an automatic error message will be generated.


Routing key prefixing
---------------------

The BaseModule supports so called automatic routing_key _prefixing_ on its various functionalities.
When the BaseModule binds or broadcasts to a exchange the module can automatically prefix the given
routing_key

This feature makes possible to have multiple instances of same module running.

The prefix string is given in __init__ argument list when the module is
if prefix=True.


The `prefix=True` argument can be given to the `bind()`-decorator or `publish()`-function.

prefixed() function can be used to prefix any given
