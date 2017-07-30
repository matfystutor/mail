import os
import sys
import logging
import argparse
import asyncore

from emailtunnel import logger


def configure_logging():
    file_handler = logging.FileHandler('tutormail.log', 'a')
    stream_handler = logging.StreamHandler(None)
    fmt = '[%(asctime)s %(levelname)s] %(message)s'
    datefmt = None
    formatter = logging.Formatter(fmt, datefmt, '%')
    for handler in (file_handler, stream_handler):
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)


parser = argparse.ArgumentParser()
parser.add_argument('-d', '--project-path', required=True,
                    help='Path to github.com/matfystutor/web.git repo')
parser.add_argument('-p', '--port', type=int, default=25,
                    help='Relay port')
parser.add_argument('-P', '--listen-port', type=int, default=9001,
                    help='Listen port')


def main():
    configure_logging()
    args = parser.parse_args()
    sys.path.append(args.project_path)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mftutor.settings")

    import django
    django.setup()

    receiver_host = '127.0.0.1'
    receiver_port = args.listen_port
    relay_host = '127.0.0.1'
    relay_port = args.port

    # Delay importing TutorForwarder to allow configuring Django first
    from tutormail.server import TutorForwarder

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
