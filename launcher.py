#!/usr/bin/env python3
"""
    The porthouse launcher script can be used to launch a larger set of porthouse and monitor their state.
    The launcher script takes an YARML configuration file as an input   is described in YAML-file. Modules and params...

    The modules can be selectively launched from the launcher file using ``--include`` and ``--exclude`` command line arguments.
    If no filter arguments is provided all the modules defined in the file will be launched.
    More about the launcher file can be read from `BLAA`<>.
"""

if __package__ is None:
    __package__ = "porthouse" # Force the launcher to be loaded as a module


import os
import amqp
import yaml
import time
import argparse
from multiprocessing import Process, RLock
from importlib import import_module
import logging, logging.handlers
from functools import reduce
from urllib.parse import urlparse
from typing import Any, Dict, List, Optional, NoReturn, Tuple

from porthouse.core.config import load_globals
from porthouse.core.log.amqp_handler import AMQPLogHandler
from porthouse.core.basemodule_async import assert_module_spec_valid
from porthouse.core.amqp_tools import check_exchange_exists

# There was massive confusion between parameters for launcher, and parameters for modules,
# causing silent bugs and erroneous function without crash.
# Hence, a strict policy on allowed arguments and parameters per level will be enforced.
LAUNCHER_VALID_CFG_MEMBERS = {"modules":(list,dict), "exchanges":(dict,(str,str))}
def _assert_cfg_valid(cfg:dict):
    assert (type(cfg) == dict), type(cfg)
    for k in cfg.keys():
        assert (k in LAUNCHER_VALID_CFG_MEMBERS), k
        assert (type(cfg[k]) == LAUNCHER_VALID_CFG_MEMBERS[k][0]) , type(cfg[k])
        if LAUNCHER_VALID_CFG_MEMBERS[k][0] == list:
            for x in cfg[k]:
                assert (type(x) == LAUNCHER_VALID_CFG_MEMBERS[k][1])
        if LAUNCHER_VALID_CFG_MEMBERS[k][0] == dict:
            for x1,x2 in cfg[k].items():
                assert (type(x1) == LAUNCHER_VALID_CFG_MEMBERS[k][1][0])
                assert (type(x2) == LAUNCHER_VALID_CFG_MEMBERS[k][1][1])





class Launcher:
    """
    Module for launching multiple porthouse modules.
    """
    log = None
    def __init__(self,
            cfg_file: str,
            includes: Optional[List[str]]=None,
            excludes: Optional[List[str]]=None,
            declare_exchanges: bool=False,
            debug: bool=False):
        """

        Args:
            cfg_file: Configuration file path
            includes: Modules to be included from the launcher module list. If none then all.
            excludes: Modules to be excluded from the launcher module list
            declare_exchanges: Initialize exchanges in start
            debug: Enable global debugging
        """
        self.threads = []
        self.debug = debug
        self.prefix = None
        self.rlock = RLock()
        #self.log = None

        # Read basic configuration
        with open(cfg_file, "r") as cfg_fd:
            cfg = yaml.load(cfg_fd, Loader=yaml.Loader)
            _assert_cfg_valid(cfg)
        self.exchanges = cfg.get("exchanges", {})
        self.modules = cfg["modules"]


        self.globals = load_globals()

        # Connect to message broker
        amqp_url = urlparse(self.globals["amqp_url"])
        self.connection = amqp.Connection(host=amqp_url.hostname, userid=amqp_url.username, password=amqp_url.password)
        self.connection.connect()
        self.channel = self.connection.channel()

        # Setup exchanges
        if declare_exchanges:
            self.create_log_handlers(self.globals["log_path"], cfg.get("name", "Launcher"), log_to_amqp=False)
            self.declare_exchanges(self.exchanges.items())
            return

        # Setup logging
        self.create_log_handlers(self.globals["log_path"], cfg.get("name", "Launcher"), log_to_amqp=False)
        self.log.info("Launching modules from %s!", cfg_file)

        # Check exchange are present
        #self.check_exchanges(self.exchanges.items())

        # Setup modules
        self.setup_modules(self.modules, includes, excludes)

        self.wait()

        self.log.critical("Core shutdown!")
        self.__del__()  # Ugly!


    def __del__(self):
        """
        Kill all modules
        """

        # Kill all child processes/threads
        for t in self.threads:
            t.terminate()
            t.join()

        self.threads = []


    def create_log_handlers(self, log_path: str, module_name: str, log_to_amqp: bool=True, log_to_stderr: bool=True) -> None:
        """
        Create AMQP and file (+ stdout) log handlers for logging

        params:
            log_path:    Directory for log file
            module_name: Name used to identify module
            log_to_amqp:
            log_to_stderr:
        """
        assert(os.path.isdir(log_path))
        file_path = os.path.join(log_path,module_name+".log")

        self.log = logging.getLogger(module_name)
        self.log.setLevel(logging.INFO)

        if log_to_amqp:
            # AMQP log handler
            amqp_handler = AMQPLogHandler(module_name, self.channel)
            amqp_handler.setLevel(logging.INFO)
            self.log.addHandler(amqp_handler)

        # File log handler
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler = logging.handlers.RotatingFileHandler(file_path , maxBytes=int(2e6), backupCount=5)
        file_handler.setFormatter(formatter)
        self.log.addHandler(file_handler)

        if log_to_stderr:
            # Create stdout log handler
            stdout_handler = logging.StreamHandler()
            stdout_handler.setFormatter(formatter)
            self.log.addHandler(stdout_handler)


    def setup_modules(self,
                      modules: List[Dict[str, Any]],
                      includes: Optional[List[str]]=None,
                      excludes: Optional[List[str]]=None) -> None:
        """
        Read the modules from the configure file and start them.

        Args.
            modules: List of module definitions for the setup
            includes: Modules to be included from the list. (If None all the modules will be loaded)
            excludes: MOdules to be enxcluded from the list.

        """
        self.log.info("Setup modules...")
        for module in modules:
            try:
                #assert_module_spec_valid(module)

                name = module.get("name", module.get('module', ''))

                ok = True
                if includes is not None: # Whitelist/including
                    ok = reduce(lambda value, inc: value or (inc in name), includes, False)
                if excludes is not None: # Blacklisting/excluding
                    ok = reduce(lambda value, exc: value and (exc not in name), excludes, ok)

                if not ok:
                    continue


                # Parse parameters
                params = dict(self.globals)
                for param in module.get("params", []):
                    for k in ("name","value"):
                        assert(k in param)

                    val = param.get("value", None)
                    if val is None:
                        continue

                    if type(val) == str:
                        if val.startswith("GLOBAL:"):
                            val = self.globals[val[len("GLOBAL:"):]]

                    if param.get("type") == "string":
                        val = str(val)
                    elif param.get("type") == "integer":
                        val = int(val)
                    elif param.get("type") == "float":
                        val = float(val)
                    elif param.get("type") == "boolean":
                        val = (val.lower() == "true")

                    if not (val is None):
                        params[param.get("name")] = val


                # Exchange prefixing!
                if self.prefix:
                    if "prefix" in params:
                        assert(type(params["prefix"]) == str)
                        params["prefix"] = "%s.%s" % (self.prefix, params["prefix"])
                    else:
                        params["prefix"] = self.prefix

                if self.debug:
                    params["debug"] = True

                # Create new process for the module
                t = Process(target=self.worker, args=(module.get("module"), params), daemon=True)
                self.threads.append(t)
                t.start()

            except:
                self.log.error("Failed to start module \"%s\"", module.get("name"))
                raise


    def declare_exchanges(self, exchanges: List[Tuple[str, str]]) -> None:
        """
        Declare/redeclare all required AMQP exchanges.
        """
        self.log.info("Declaring exchanges...")
        for exchange, etype in exchanges:
            self.log.debug("\t%s (%s)", exchange, etype)
            try:
                self.channel.exchange_delete(exchange)
                self.channel.exchange_declare(exchange=exchange, type=etype, durable=True,  auto_delete=False)
            except:
                raise ValueError("Invalid exchange spec.")
        self.log.info("Declaring done")


    def check_exchanges(self, exchanges: List[Tuple[str, str]]) -> None:
        """
        Declare/redeclare all required AMQP exchanges.
        """
        self.log.info("Checking exchanges...")
        for exchange, etype in exchanges:
            self.log.debug("\t%s (%s)", exchange, etype)
            try:
                assert check_exchange_exists(exchange, etype)
            except:
                raise ValueError("Exchange {} not according to spec.".format(exchange))
        self.log.info("Exchanges ok.")


    def wait(self) -> NoReturn:
        """
        Wait until someone dies.
        """
        try:
            running = True
            while running:
                time.sleep(0.5)

                for t in self.threads:
                    if not t.is_alive():
                        running = False

        except KeyboardInterrupt:
            pass


    def worker(self, module: str, params: Dict) -> NoReturn:
        """
        Worker function to start the new module.
        """
        try:
            package_name, module_name = module.rsplit('.', 1)
            i = import_module(package_name)
            """
                Note: Logging here isn't completely threadsafe!
                      ... but meh!
            """
            with self.rlock:
                self.log.info("Starting %s (%s.%s)", params.get("module_name", module_name), package_name, module_name)

            import inspect

            # Check that all the required arguments have been define and output understandable error if not
            argspec = inspect.getfullargspec(getattr(i, module_name).__init__)
            for j, arg in enumerate(argspec.args[1:]):
                if j >= len(argspec.defaults or []) and arg not in params:
                    raise RuntimeError(f"Module {module_name!r} missing argument {arg!r}")

            inst = getattr(i, module_name)(**params)
            inst.run()

            with self.rlock:
                self.log.info("Module %s (%s.%s) exited", params.get("module_name", module_name), package_name, module_name)

        except KeyboardInterrupt:
            pass

        except: # Catch all exceptions!
            with self.rlock:
                self.log.critical("%s crashed!", module, exc_info=True)


def setup_parser(parser: argparse.ArgumentParser) -> None:

    parser.add_argument('--cfg', required=True,
        help='Configuration file')
    parser.add_argument('--declare_exchanges', action='store_true',
        help='Declare exchanges')
    parser.add_argument('-d', '--debug', action='store_true',
        help='Enable debug features')
    parser.add_argument('--include', nargs='*',
        help='Modules to be included from the configuration')
    parser.add_argument('--exclude', nargs='*',
        help='Modules to be excluded from the configuration')



def main(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    Launcher(
        cfg_file=args.cfg,
        includes=args.include, excludes=args.exclude,
        declare_exchanges=args.declare_exchanges,
        debug=args.debug
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='porthouse launcher script')
    setup_parser(parser)
    main(parser, parser.parse_args())
