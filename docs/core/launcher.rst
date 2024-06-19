
Launcher
########

The launcher is an utility script for launching a set of porthouse modules.
The tool can be launched via the ``porthouse`` CLI tool using keyword ``launch``.
Generally, the launcher takes in the launcher configuration files as ``--cfg`` argument to be launched.
``--include`` and ``--exclude`` can be used to selectively launch only some modules.
The format of the launcher configuration is described in following sections.


.. code-block:: console

    $ porthouse launch --help
                      _   _
    _ __   ___  _ __| |_| |__   ___  _   _ ___  ___
    | '_ \ / _ \| '__| __| '_ \ / _ \| | | / __|/ _ \
    | |_) | (_) | |  | |_| | | | (_) | |_| \__ \  __/
    | .__/ \___/|_|   \__|_| |_|\___/ \__,_|___/\___|
    |_|

    usage: porthouse [-h] [--amqp AMQP_URL] [--db DB_URL] {cmdl,launch,scheduler,packets,housekeeping}

    Porthouse command line utility

    positional arguments:
      {cmdl,launch,scheduler,packets,housekeeping}

    options:
      -h, --help            show this help message and exit
      --amqp AMQP_URL       AMQP connection URL.
      --db DB_URL           PostgreSQL database URL.


Launcher configuration file
----------------------------

Each module definition shall include at least the ``module`` argument. This argument is the
name for example ``porthouse.gs.tracking.orbit_tracker.OrbitTracker``.
In this definition ``porthouse.gs.tracking.orbit_tracker`` is the module path and
``OrbitTracker`` software module class name.


Optionally, a ``name`` argument can be given for the module instance to different single
instance of a module from another.  The name is mainly used in as the logging.
If multiple instances of same module are launched.


TODO: ``prefix``



.. code-block:: yaml

    modules:
    - name: MyOrbitTracker
      module: porthouse.gs.tracking.orbit_tracker.OrbitTracker
      params:
      - name: config
        value: 123



Filtering loaded modules
========================

The list of modules the launcher will start can be modified using `--include` and `--exclude` arguments.
By default all the modules listed in the launch configuration will be launched.
If include argument is given, only modules which name contains one of the include keywords are loaded.
If exclude argument is given, all modules expect which name contains any of the excluded keywords are loaded.
If both include and exclude arguments are given, only modules which name contains one of the include and doesn't contain any of the excluded keywords are loade


In other words:

- If you want to load only one or two modules use `--include`.
  For example to lad only the tle_server module:

.. code-block:: console

    $ /etc/porthouse/launcher.py ... --include tle_server


- If you want to load all expect one or several modules use `--exclude`.
  For example to load all modules except scheduler:

.. code-block:: console

    $ /etc/porthouse/launcher.py ... --exlclude scheduler


- If you want to load all modules under certain directory but exclude one, you can use both arguments.
  All GS modules (no MCS modules) expect scheduler:

.. code-block:: console

    $ /etc/porthouse/launcher.py ... --include gs --exlclude scheduler
