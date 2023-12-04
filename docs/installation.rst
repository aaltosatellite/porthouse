
Installation
############


A short guide how to get the software running on Debian-like environment...

Main Dependencies:

- Python 3.7 or newer
- PostgreSQL version 11
- Main python dependencies:
    - amqio
    - Python AMQP 2.0.3
    - skyfield



Installation of main dependencies
---------------------------------


1) Installing RabbitMQ message broker:

.. code-block:: console

    $ sudo apt-get install rabbitmq-server

optional:

.. code-block:: console

    $ sudo rabbitmq-plugins enable rabbitmq_management


2) Pull the repository

.. code-block:: console

    $ git clone git@github.com:aaltosatellite/porthouse.git
    $ cd porthouse


3) Install the porthouse in development mode

.. code-block:: console

    $ python3 setup.py develop --user


Alternatively, pip can be also used to install the package in so called "editable" mode.

.. code-block:: console

    $ pip3 install -e .



4) Install Python dependencies

.. code-block:: console

    $ pip3 install -r requirements.txt


Installing PostgreSQL
---------------------

Some of the modules uses PostgreSQL to store their data so creating a shared database is required.
To install Postgres database engine and to create a new user+database for following command can be used:

.. code-block:: console

    $ sudo apt-get install postgresql
    $ sudo -u postgres createuser mcs -P
    $ sudo -u postgres createdb "foresail" -O mcs

The createuser command requires you input a password (and PASSWORD is recommended for Foresail ground segment).

For running Foresail GS, timescale-DB and tables need to be created. Detailed setup guides for creating the database tables can be found from module specific installation guides such as from:

- [housekeeping](mcs/housekeeping/README.md) 

- [packets](mcs/packets/README.md) modules.


When needed a login to PostgreSQL console happens with following command:
```
$ sudo -u postgres psql -d foresail
```
Alternatively, Postgres permission can be modified to allow more free logins.




Launching the demo setup
------------------------

To get the first
Some additional dependencies for the demo.

.. code-block:: console

    $ sudo apt-get install libhamlib-utils


Launch the back-end with the demo configuration.

.. code-block:: console

    $ porthouse launch --cfg demo_cfg.xml --declare_exchanges


If no catastrophic errors were printed out, the back-end is now running in the demo configuration.
`--declare_exchanges` flag is required only on the first time. This flag runs AMQP exchanges declarations and RabbitMQ will remember them in the future.

To interface with the back-end you can use the system command line tool:

.. code-block:: console

    $ porthouse cmdl
                      _   _
     _ __   ___  _ __| |_| |__   ___  _   _ ___  ___
    | '_ \ / _ \| '__| __| '_ \ / _ \| | | / __|/ _ \
    | |_) | (_) | |  | |_| | | | (_) | |_| \__ \  __/
    | .__/ \___/|_|   \__|_| |_|\___/ \__,_|___/\___|
    |_|
                 Command line interface
    GS>>> Rotator.status()

    GS>>> Rotator.move(10, 10)



OR the legacy Qt GUI. The legacy GUI has some unique dependencies.

.. code-block:: console

    $ sudo apt-get install python3-pyqt5
    $ pip3 install qdarkstyle
    $ cd gs/gui
    $ python3 gui.py



Congratulation! You have now got the first touch to porthouse. |:tada:|

Next we can start installing more modules and features.




Working with the configuration file
------------------------------------

The porthouse back-end is launched based on a XML-based configuration which is given as a argument for the launcher script. The configuration file is designed to be edited by each team use and making a copy of `example_cfg.xml` or `demo_cfg.xml` called `mcs.xml` is recommended. The configuration file includes many global environment variable definitions and list of modules to be launched with the launcher.


Launching modules with the launcher
------------------------------------

Run launcher script to start all the modules...

.. code-block:: console

    $ porthouse launch --cfg [--declare_exchanges] [--create_schema]


More about `launcher.py` can be read from (here)[core/launcher.md].


# Installing more modules

More installation guides can be found from following READMEs.
- [Housekeeping backend](mcs/housekeeping/README.md)
- [Packets database](mcs/packets/README.md)
- [Notification services](notifications/README.md)
