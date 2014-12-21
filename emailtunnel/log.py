import argparse
import asyncore
from emailtunnel import LoggingReceiver


def main():
    parser = argparse.ArgumentParser()
    args = parser.parse_args()

    receiver_host = '0.0.0.0'
    receiver_port = 8825
    server = LoggingReceiver(receiver_host, receiver_port)
    asyncore.loop(timeout=0.1, use_poll=True)


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.DEBUG)

    main()
