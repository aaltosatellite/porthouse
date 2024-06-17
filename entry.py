
import argparse
import porthouse.cmdl
import porthouse.launcher
import porthouse.gs.scheduler.schedule
import porthouse.mcs.packets.packets

def main():

    parser = argparse.ArgumentParser(description='porthouse command line tool')
    subparser = parser.add_subparsers(title='utility', dest='utility', description="")

    # General configs
    parser.add_argument('--amqp', dest="amqp_url",
        help="AMQP connection URL.")
    parser.add_argument('--db', dest="db_url",
        help="PostgreSQL database URL.")


    porthouse.cmdl.setup_parser(subparser.add_parser("cmdl"))
    porthouse.launcher.setup_parser(subparser.add_parser('launch'))
    porthouse.gs.scheduler.schedule.setup_parser(subparser.add_parser('scheduler'))
    porthouse.mcs.packets.packets.setup_parser(subparser.add_parser('packets'))

    args = parser.parse_args()


    if args.utility == "cmdl":
        porthouse.cmdl.main(parser, args)
    elif args.utility == "launch":
        porthouse.launcher.main(parser, args)
    elif args.utility == "packets":
        porthouse.mcs.packets.packets.main(parser, args)
    elif args.utility == "scheduler":
        porthouse.gs.scheduler.schedule.main(parser, args)
    else:
        parser.print_help()
