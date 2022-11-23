

Housekeeping
############




Installing PostgreSQL and Timescale
--------------------------------

New instructions.

Go to TimescaleDB for installation instructions:
https://docs.timescale.com/install/latest/self-hosted/installation-debian/

Briefly, install TimescaleDB and PostgreSQL:

.. code-block:: console

    $ sudo apt install gnupg postgresql-common apt-transport-https lsb-release wget
    $ sudo /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh
    $ sudo echo "deb https://packagecloud.io/timescale/timescaledb/ubuntu/ $(lsb_release -c -s) main" | sudo tee /etc/apt/sources.list.d/timescaledb.list
    $ sudo wget --quiet -O - https://packagecloud.io/timescale/timescaledb/gpgkey | sudo gpg --dearmor -o /etc/apt/trusted.gpg.d/timescaledb.gpg
    $ sudo apt update
    $ sudo apt install timescaledb-2-postgresql-14

Next install psql for command-line use

.. code-block:: console

    $ sudo apt-get update
    $ sudo apt-get install postgresql-client

Setup the Timescale plugin and restart PostgreSQL server

.. code-block:: console

    $ sudo timescaledb-tune -pg-version 14 -yes
    $ sudo service postgresql restart

Now PostgreSQL and TimescaleDB should be installed.

.. TODO::
    See if these are necessary.
    (Might need this command below for access to postgresql.conf, to add timescaledb to preloaded libraries.)
    .. code-block:: console
        $ sudo chown postgres:root /etc/postgresql/14/main/*

    (Now maybe restart the service, after using timescaledb-tune)
    .. code-block:: console
        $ systemctl restart postgresql



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


Install psycopg2

.. code-block:: console

    $ sudo apt install python3-psycopg2


Creating tables

.. code-block:: console

    $ python3 -m porthouse.mcs.housekeeping.database --create_tables
