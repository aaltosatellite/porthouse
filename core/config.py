"""
    Utils for loading porthouse configurations
"""

import os
import yaml
from typing import Any, Dict, Optional



_dir: str
_globals: Dict[str, str] = None

if os.getenv("PORTHOUSE_CFG"):
    _dir = os.getenv("PORTHOUSE_CFG")
else:
    _dir = os.path.join(os.path.expanduser("~"), ".porthouse")


def cfg_path(filename: Optional[str]=None) -> str:
    """
    Return an absolute path to config directory or a file located in config directory.

    Args:
        filename: Optional filename to be appended to the path.

    Returns:
        Absolute config path/filename as a string.
    """
    global _dir
    if filename is not None:
        return os.path.join(_dir, filename)
    return _dir


def load_globals() -> Dict[str, Any]:
    """
    Load global environment variables from the porthouse config directory.
    If the function has been called previously the dict is returned
    from cache instead of reloading the file.

    Returns:
        Dictionary containing the all global definitions.
    """
    global _globals
    if _globals is not None: # Cached
        return _globals

    try:
        with open(cfg_path("globals.yaml"), "r") as file:
            _globals = yaml.load(file, Loader=yaml.Loader)
    except FileNotFoundError:
        raise FileNotFoundError(f"Missing '{_dir}/globals.yaml'! Please run the setup.py!")
    return _globals


def create_template_config() -> None:
    """
    Create template configuration directory.
    """

    print(f"Creating configure in {_dir}")

    # Create folders
    try:
        os.mkdir(_dir)
        os.mkdir(os.path.join(_dir, "logs"))
    except FileExistsError:
        print(f"Directory already exists! Exiting...")
        return


    print("Creating 'globals.yaml' file")
    with open(os.path.join(_dir, "globals.yaml"), "x") as file:
        file.write(
            f"amqp_url: amqp://guest:guest@localhost:5672/\n"
            f"db_url: postgres://mcs:PASSWORD@localhost/porthouse\n"
            f"log_path: {os.path.join(_dir, 'logs')}\n"
            f"#hk_schema: \n"
        )

    print("Creating 'groundstation.yaml' file")
    with open(os.path.join(_dir, "groundstation.yaml"), "x") as file:
        file.write(
            "groundstation:\n"
            "  name: porthouse\n"
            "  longitude: 24.83        # Longitude in degrees\n"
            "  latitude: 60.18         # Latitude in degrees\n"
            "  elevation: 40           # Altitude in meters\n"
            "  horizon: 0              # Minimum elevation\n"
            "  default: Aalto-1        # Name of the default target\n"
        )

    print("Creating 'tle.yaml' file")
    with open(os.path.join(_dir, "tle.yaml"), "x") as file:
        file.write(
            "#\n"
            "# For more information read the documentation from https://blaa/tle_server.html\n"
            "#\n"
            "\n"
            "satellites:\n"
            "- name: Aalto-1\n"
            "  source: web\n"
            "  identifier: AALTO-1\n"
            "  websrc: http://www.celestrak.com/NORAD/elements/cubesat.txt\n"
            "\n"
            "- name: ISS\n"
            "  source: web\n"
            "  identifier: ISS (ZARYA)\n"
            "  websrc: http://www.celestrak.com/NORAD/elements/stations.txt\n"
        )
