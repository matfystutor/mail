import six
import logging
import argparse
import asyncore

from tutormail.server import TutorForwarder


def configure_logging():
    root = logging.getLogger()
    file_handler = logging.FileHandler('tutormail.log', 'a')
    stream_handler = logging.StreamHandler(None)
    fmt = '[%(asctime)s %(levelname)s] %(message)s'
    datefmt = None
    if six.PY3:
        formatter = logging.Formatter(fmt, datefmt, '%')
    else:
        formatter = logging.Formatter(fmt, datefmt)
    for handler in (file_handler, stream_handler):
        handler.setFormatter(formatter)
        root.addHandler(handler)
    root.setLevel(logging.DEBUG)


def get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--port', type=int, default=25,
                        help='Relay port')
    parser.add_argument('-P', '--listen-port', type=int, default=9001,
                        help='Listen port')
    return parser


def main():
    configure_logging()
    parser = get_parser()
    args = parser.parse_args()

    receiver_host = '127.0.0.1'
    receiver_port = args.listen_port
    relay_host = '127.0.0.1'
    relay_port = args.port

    server = TutorForwarder(
        receiver_host, receiver_port, relay_host, relay_port)
    try:
        asyncore.loop(timeout=0.1, use_poll=True)
    except KeyboardInterrupt:
        logging.info('TutorForwarder exited via KeyboardInterrupt')
    except:
        logging.exception('TutorForwarder exited via exception')
    else:
        logging.error('TutorForwarder exited via asyncore.loop returning')


if __name__ == "__main__":
    main()
