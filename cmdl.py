"""
porthouse command line tool
"""

import asyncio
import json
import argparse
import importlib

from os import environ
from datetime import datetime

import aiormq

from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit import print_formatted_text
from prompt_toolkit.application import in_terminal

from ptpython.repl import embed, PythonRepl
from ptpython.prompt_style import PromptStyle


from porthouse.core.config import load_globals, cfg_path
from porthouse.core.rpc_async import amqp_connect, send_rpc_request


def configure(repl: PythonRepl):
    """
    Config callback function for the ptpython repl
    """

    class PorthousePrompt(PromptStyle):
        def in_prompt(self):
            return [('class:prompt', 'GS>>> ')]

        def in2_prompt(self, width):
            return [('class:prompt.dots', '   ...')]

        def out_prompt(self):
            return []

    repl.all_prompt_styles['custom'] = PorthousePrompt()
    repl.prompt_style = 'custom'
    repl.show_docstring = True
    repl.insert_blank_line_after_output = False
    repl.enable_dictionary_completion = True

    """
    Monkey patching eval_asyc!
    This wrapper makes sure that if async functions are called from the CLI
    the returned coroutines will be awaited.
    """
    repl.org_eval_async = repl.eval_async
    async def auto_async_eval(line):
        result = repl.org_eval_async(line)
        while asyncio.iscoroutine(result):
            result = await result
        return result
    repl.eval_async = auto_async_eval


async def logger() -> None:
    """
    Log printer coroutine
    """

    LOG_COLORS = {
        "info":     "ansiwhite",
        "warning":  "ansiyellow",
        "error":    "ansired",
        "critical": "ansibrightred",
    }

    async def print_log_entry(message: aiormq.abc.DeliveredMessage):
        """
        Print received message to stdout.
        """
        try:
            entry = json.loads(message.body)
        except:
            return

        if "message" in entry:
            timestamp = datetime.utcfromtimestamp(entry["created"]).isoformat()
            async with in_terminal():
                print_formatted_text(FormattedText([(
                     LOG_COLORS.get(entry['level'], ''),
                     f"\r\r# {timestamp} - {entry['level'].upper()} - {entry['module']} - {entry['message']}"
                )]))

    declare_ok = await channel.queue_declare(exclusive=True, auto_delete=True)
    log_queue = declare_ok.queue
    await channel.basic_consume(log_queue, print_log_entry)
    await channel.queue_bind(log_queue, exchange="log", routing_key="*")


async def run_repl() -> None:
    """
    Coroutine for running the Python REPL
    """
    try:
        await embed(globals(), locals(),
            vi_mode=False,
            configure=configure,
            history_filename=cfg_path(".cmdl-history"),
            return_asyncio_coroutine=True,
            patch_stdout=True,
        )
    except EOFError:
        asyncio.get_event_loop().stop()


def setup_parser(cmdl_parser: argparse.ArgumentParser) -> None:
    """
    """
    cmdl_parser.add_argument('-l', '--logger', action="store_true")
    cmdl_parser.add_argument('--amqp', dest="amqp_url",  help="AMQP connection URL.")
    cmdl_parser.add_argument('--db', dest="db_url", help="PostgreSQL database URL.")


def main(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """ """

    #
    # Load cmdl config file
    #
    try:
        import yaml
        with open(cfg_path("cmdl.yaml"), "r") as fd:
            cmdl_cfg = yaml.load(fd, Loader=yaml.Loader)
    except FileNotFoundError:
        cmdl_cfg = { }

    #
    # Load the environment
    #
    services = [
        {
            "name": "rotator",
            "class": "porthouse.gs.hardware.interface.RotatorInterface",
            "params": {
                "prefix": "uhf"
            }
        },
        {
            "name": "torator",
            "class": "porthouse.gs.hardware.interface.RotatorInterface",
            "params": {
                "prefix": "sband"
            }
        },
        {
            "name": "tracker",
            "class": "porthouse.gs.tracking.interface.OrbitTrackerInterface",
        }
    ]

    for service in services:
        """
        Instantiate interface objects and add them to 'globals()'
        """
        package_name, class_name = service["class"].rsplit('.', 1)
        params = service.get("params", {})
        package = importlib.import_module(package_name)
        class_object = getattr(package, class_name)

        import inspect
        # Check that all the required arguments have been define and output understandable error if not
        argspec = inspect.getfullargspec(class_object.__init__)
        for j, arg in enumerate(argspec.args[1:]):
            if j >= len(argspec.defaults or []) and arg not in params:
                raise RuntimeError(f"Module {class_name!r} missing argument {arg!r}")

        globals()[service["name"]] = class_object(**params)

    #
    # Connect to AMQP broker
    #
    connection, channel = None, None
    async def connect_broker(amqp_url: str):
        global connection, channel
        connection, channel = await amqp_connect(amqp_url)

    print(r"                  _   _                           ")
    print(r" _ __   ___  _ __| |_| |__   ___  _   _ ___  ___  ")
    print(r"| '_ \ / _ \| '__| __| '_ \ / _ \| | | / __|/ _ \ ")
    print(r"| |_) | (_) | |  | |_| | | | (_) | |_| \__ \  __/ ")
    print(r"| .__/ \___/|_|   \__|_| |_|\___/ \__,_|___/\___| ")
    print(r"|_|                                               ")
    print(r"             Command line interface               ")

    loop = asyncio.get_event_loop()
    loop.run_until_complete(connect_broker(args.amqp_url))
    if args.logger:
        loop.create_task(logger())

    repl_task = loop.create_task(run_repl())
    while not repl_task.done():
        try:
            loop.run_until_complete(repl_task)
        except KeyboardInterrupt:
            repl_task.cancel()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Commandline')
    setup_parser(parser)
    main(parser, parser.parse_args())
