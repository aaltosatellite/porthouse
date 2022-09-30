
Orbit Tracker
#############

The Orbit Tracker is simple for tracking orbital objects based on their orbital parameters.
The tracker can have single active target at the time. Orbit propagation is done using two
line element or so called TLE lines provided by the TLEServer. The implementation relies
on skyfield-library.


Installation
------------

The OrbitTracker does not require any additional software libraries beside the porthouse's
standard dependencies.


.. code-block:: yaml

    - module: porthouse.gs.tracking.orbit_tracker.OrbitTracker


Configuration
in ´´groundstation.yaml´´



RPC methods
-----------

.. rpc-method:: rpc.set_target(satellite)


.. rpc-method:: rpc.get_config()

    Return the ground station configuration.

    .. code-block:: json

        {
            "name": <name of the ground station>,
            "lat": <gs latitude as float>,
            "lon": <gs longitude as float>,
            "elevation": <gs elevation in meters>,
            "horizon": <gs horizon>,
        }


.. rpc-method:: rpc.get_satellite_pass(satellite)




Module definition
-----------------

.. automodule:: porthouse.gs.tracking.orbit_tracker.OrbitTracker
    :members:
