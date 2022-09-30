TLE Server
==========

TLE Server module maintains a system wide list of tracked satellites and
updates provides up-to-date TLE orbital elements from various source.

Module provides a RPC interface for requesting the satellite list and updating the list.

The supported TLE source types are:

* *lines*: static lines from any source. Specify ``tle1`` and ``tle2`` parameters
* *web*: txt on a HTTP. Specify ``websrc`` and ``identifier`` parameters.
* *space-track*: request TLE from `space-track.org<https://www.space-track.org/>`_ using NORAD ID.

More about the

To modify the satellite list edit ``.porthouse/tle.yaml`` file and re-run TLE update routine.



.. todo:: Mention about the cache

.. todo:: JSON-OMM


Installation
------------

Additionally, to the standard the TLE server module requires ``requests-async`` library.
This library can be installed from pip with following command:

.. code-block:: console

    $ pip3 install requests-async


After this the TLEServer can be added to the launcher configuration file:

.. code-block:: yaml

    - module: porthouse.gs.tracking.orbit_tracker.OrbitTracker



Configurations
--------------

TLE server uses a.
The configuration file is reloaded every time.

.. confval:: Static lines

**Static TLE lines:**

.. code-block:: yaml

    - name: Aalto-1
      source: lines
      tle1: 1 42775U 17036L   20105.14526983  .00000705  00000-0  34087-4 0  9996
      tle2: 2 42775  97.3059 159.0899 0012346 242.0416 117.9571 15.21747321155898


.. confval:: Static HTTP source**

Parse TLE lines from text document provided somewhere in the Internet.

.. code-block:: yaml

    - name: Aalto-1
      source: web
      identifier: AALTO-1
      websrc: http://www.celestrak.com/NORAD/elements/cubesat.txt



.. confval:: Space-track.org

Note! Specify also login credentials for space-track.org

.. code-block:: yaml

    satellites:
    - name: Aalto-1
      source: space-track
      norad_id: 42775

    space-track_credentials:
      identity: <YOUR USERNAME>
      password: <YOUR PASSWORD>



RPC methods
-----------

.. rpc-method:: tle.rpc.get_tle(satellite, check_time)

    If 'satellite'

    If `check_time` argument is provided in the request, the RPC handler will check
    that the provided timestamp is more than 2 seconds off from the server's time.
    This can feature can be used to .
    The clock mismatch between server and client can easily result to operator's confusion
    about the tracking systems behavior because the clients usually use their local time
    for the orbit propagation and pass calculations.


.. rpc-method:: tle.rpc.update()

    Trigger the TLE update routine. The module will reload the


Module definition
-----------------

.. automodule:: porthouse.gs.tracking.tle_server.TLEServer
    :members:
