# PYTHON_ARGCOMPLETE_OK
import os
import argcomplete
import argparse
from importlib import import_module


SUBMODULES = {
    "cmdl": "porthouse.cmdl",
    "launch": "porthouse.launcher",
    "scheduler": "porthouse.gs.scheduler.schedule",
    "packets": "porthouse.mcs.packets.packets",
    "housekeeping": "porthouse.mcs.housekeeping.tools"
}


PORTHOUSE_BANNER = "\n".join([
    r"                  _   _                           ",
    r" _ __   ___  _ __| |_| |__   ___  _   _ ___  ___  ",
    r"| '_ \ / _ \| '__| __| '_ \ / _ \| | | / __|/ _ \ ",
    r"| |_) | (_) | |  | |_| | | | (_) | |_| \__ \  __/ ",
    r"| .__/ \___/|_|   \__|_| |_|\___/ \__,_|___/\___| ",
    r"|_|                                               ",
    "\n"
])


class PorthouseHelpFormatter(argparse.HelpFormatter):
    """ Custom Help formatter class to add the porthouse banner. """
    def format_help(self):
        return PORTHOUSE_BANNER + super().format_help()


def main():
    """
    """

    parser = argparse.ArgumentParser(description="Porthouse command line utility", formatter_class=PorthouseHelpFormatter)
    utility = parser.add_argument('utility', choices=SUBMODULES.keys())

    # General configs
    parser.add_argument('--amqp', dest="amqp_url",
        help="AMQP connection URL.")
    parser.add_argument('--db', dest="db_url",
        help="PostgreSQL database URL.")

    if "_ARGCOMPLETE" in os.environ:

        # Call custom setup_parser before trying autocompleting
        package = None
        line = os.environ["COMP_LINE"]
        for module, package_import in SUBMODULES.items():
            if module in line:
                package = import_module(package_import)
                package.setup_parser(parser)
                break

        argcomplete.autocomplete(parser)
        return

    args, _ = parser.parse_known_args()
    package = import_module(SUBMODULES[args.utility])
    package.setup_parser(parser)
    args = parser.parse_args()
    package.main(parser, args)
