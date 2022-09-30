

Housekeeping
############




Installing PostgreSQL and Timescale
--------------------------------

Add timescale to apt package manager

.. code-block:: console

    $ sudo add-apt-repository ppa:timescale/timescaledb-ppa

If you have postgres already installed, check its version by typing:

.. code-block:: console

    $ psql --version

If yes install only the corresponding timescale plugin for Postgres.

.. code-block:: console

    $ sudo apt install postgresql-12
    $ sudo apt install timescaledb-postgresql-12

Setup the Timescale plugin and restart PostgreSQL server

.. code-block:: console

    $ sudo timescaledb-tune
    $ sudo service postgresql restart


Creating a database
---------------

Create new user for database access

.. code-block:: console

    $ sudo -u postgres createuser mcs -P
    <type a good password here>   # PASSWORD is used in the default configuration :D

Create new database (mcs user is the database owner user)

.. code-block:: console

    $ sudo -u postgres createdb "porthouse" -O mcs

.. TODO::

    Write about housekeeping schema setup

Install the timescale as superuser

.. code-block:: console

    $ sudo -u postgres psql -d porthouse
    > CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;





Creating tables

.. code-block:: console

    $ python3 -m porthouse.mcs.housekeeping.database --create_tables
