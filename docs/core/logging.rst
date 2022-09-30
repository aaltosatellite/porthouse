
Logging
#######


The basemodule initializes the default logging servive

the Pyhton's standard logging system.
Also the basemodule initializes stdout output and AMQ


.. code-block:: python

    from porthouse.core.basemodule import *

    class MyModule(BaseModule):
        ...
        def do_something(self):
            self.log.info("Just logging here...")


AMQP logging
------------

The logging messages are using exchange ``log``. The routing_key has log severity level.

.. code-block:: json

    {
        module: "ModuleName",
        level: "info",  # logging severity level: debug, info, warning, critical
        created": "2021-06-23T21:21:23.151996",  # Timestamp as ISO date
        message": "Logging message string"
    }


Any other module can
