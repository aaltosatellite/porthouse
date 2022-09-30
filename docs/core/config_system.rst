
Configuration System
####################

All the user specific configurations and persistent data for the porthouse is stored in

The default location for the config directory is the ``.porthouse`` folder in users home (aka ``~/.porthouse``).
The config folder location can be forced using ``PORTHOUSE_CFG`` environment variable.

By default the configuration folder includes following files:
- ``globals.yaml``
- ``tle.yaml``
- ``groundstation.yaml``

The configuration folder template is created by the ``setup.py`` installation script.
The template generator script is locate in ``porthouse.core.config``.


The porthouse
