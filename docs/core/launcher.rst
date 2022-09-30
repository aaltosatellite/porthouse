
Launcher
########

The launcher is an utility script for launching a set of porthouse modules.
The tool can be launched via the ``porthouse`` CLI tool using keyword ``launch``.
Generally, the launcher takes in the launcher configuration files as ``--cfg`` argument to be launched.
``--include`` and ``--exclude`` can be used to selectively launch only some modules.
The format of the launcher configuration is described in following sections.


.. code-block:: console

    $ porthouse launch --help
    usage: launcher.py [-h] --cfg CFG [--declare_exchanges] [-d] [--include [INCLUDE [INCLUDE ...]]] [--exclude [EXCLUDE [EXCLUDE ...]]]

    Mission Control Software

    optional arguments:
      -h, --help            show this help message and exit
      --cfg CFG             Configuration file
      --declare_exchanges   Declare exchanges
      -d, --debug           Enable debug features
      --include [INCLUDE [INCLUDE ...]]
                            Modules to be included from the configuration
      --exclude [EXCLUDE [EXCLUDE ...]]
                            Modules to be excluded from the configuration


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
