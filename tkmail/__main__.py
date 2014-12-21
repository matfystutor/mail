import logging
import argparse
import asyncore

from tkmail.server import TKForwarder


def configure_logging():
    root = logging.getLogger()
    file_handler = logging.FileHandler('tkmail.log', 'a')
    stream_handler = logging.StreamHandler(None)
    fmt = '[%(asctime)s %(levelname)s] %(message)s'
    datefmt = None
    formatter = logging.Formatter(fmt, datefmt, '%')
    for handler in (file_handler, stream_handler):
        handler.setFormatter(formatter)
        root.addHandler(handler)
    root.setLevel(logging.DEBUG)


def get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--port', type=int, default=25,
                        help='Relay port')
    parser.add_argument('-y', '--gf', type=int, default=2014,
                        help='GF year')
    return parser


def main():
    configure_logging()
    parser = get_parser()
    args = parser.parse_args()

    receiver_host = '0.0.0.0'
    receiver_port = 9000
    relay_host = '127.0.0.1'
    relay_port = args.port

    server = TKForwarder(
        receiver_host, receiver_port, relay_host, relay_port,
        year=args.gf)
    logging.info('TKForwarder initialized with relay port %s, GF year %s' %
                 (relay_port, args.gf))
    try:
        asyncore.loop(timeout=0.1, use_poll=True)
    except KeyboardInterrupt:
        logging.info('TKForwarder exited via KeyboardInterrupt')
    except:
        logging.exception('TKForwarder exited via exception')
    else:
        logging.error('TKForwarder exited via asyncore.loop returning')


if __name__ == "__main__":
    main()
