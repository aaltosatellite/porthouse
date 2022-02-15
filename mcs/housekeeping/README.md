
# Installation:


## Install Postgres and Timescale
```

# Add timescale to apt package manager
sudo add-apt-repository ppa:timescale/timescaledb-ppa
sudo apt-get update

# Install PostgreSQL and Timescale
sudo apt install postgresql-11 timescaledb-postgresql-11

# Setup the Timescale plugin
sudo timescaledb-tune

# Restart PostgreSQL server
sudo service postgresql restart

```
More information: https://docs.timescale.com/latest/getting-started/installation/ubuntu/installation-apt-ubuntu


## Setup the database

```
# Create new user for database access
sudo -u postgres createuser mcs -P
<type a good password here>   (PASSWORD is used in the default configuration)

# Create new database (mcs user is the owner)
sudo -u postgres createdb "foresail" -O mcs

# Install the timescale as superuser
sudo -u postgres psql -d foresail
> CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

# Generate the housekeeping tables
python3 database_api.py --create_schema
```

Database connection URL need to be defined to configuration file.

## Creating a read-only user

```
$ sudo -u postgres psql -d foresail
foresail=# CREATE USER reader WITH PASSWORD 'test';
foresail=# GRANT SELECT ON eps, obc, adcs, uhf TO reader;
foresail=# \d


# To allow password log in over IP open ""/etc/postgresql/11/main/pg_hba.conf" and add line like:

# TYPE  DATABASE        USER            ADDRESS                 METHOD
local   all             reader                                  md5

# Note: This has to be added to middle of the file where similar header line is located!


# Restart PostgreSQL server
sudo service postgresql restart

# Test the user
psql -U reader -d foresail -W

```
