import sys
import json
import logging
logging.basicConfig(level=logging.DEBUG)
import smtplib
import argparse
import asyncore
import datetime
import threading
import traceback

import email
import email.message
from email.mime.base import MIMEBase
import smtpd


def now_string():
    """Return the current date and time as a string."""
    return datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S.%f")


class Message(object):
    def __init__(self, message):
        # assert isinstance(message, str)
        self.message = email.message_from_string(message)

        if message.rstrip('\n') == str(self).rstrip('\n'):
            logging.debug("%s Data is sane" % self.port)
        else:
            logging.debug("%s Data is not sane" % self.port)
            print(repr(message))
            print(repr(str(self)))

    def __str__(self):
        return str(self.message)

    def add_header(self, key, value):
        pass

    def get_unique_header(self, key):
        pass

    def set_unique_header(self, key, value):
        pass

    @property
    def subject(self):
        return self.get_unique_header('Subject')

    @subject.setter
    def subject(self, s):
        self.set_unique_header('Subject', s)


class Envelope(object):
    def __init__(self, message, mailfrom, rcpttos):
        """See also SMTPReceiver.process_message.

        mailfrom is a string; rcpttos is a list of recipients.
        """

        assert isinstance(message, Message)
        self.message = message
        self.mailfrom = mailfrom
        self.rcpttos = rcpttos


class SMTPReceiver(smtpd.SMTPServer):
    def __init__(self, host, port):
        self.host = host
        self.port = port
        super(SMTPReceiver, self).__init__((self.host, self.port), None)

    def process_message(self, peer, mailfrom, rcpttos, data):
        """Implementation of SMTPReceiver.process_message.

        peer is a tuple of (ipaddr, port).
        mailfrom is the raw sender address.
        rcpttos is a list of raw recipient addresses.
        data is the full text of the message.
        """

        message = Message(data)
        envelope = Envelope(message, mailfrom, rcpttos)
        logging.debug(
            "Message received from Peer: %r, From: %r, to To %r."
            % (peer, mailfrom, rcpttos))
        try:
            return self.handle_envelope(envelope)
        except:
            try:
                self.handle_error(envelope)
            except:
                logging.exception("handle_error threw exception")

            # Instruct the sender to retry sending the message later.
            return '451 Requested action aborted: error in processing'

    def handle_envelope(self, envelope):
        raise NotImplementedError()

    def handle_error(self, envelope):
        logging.exception("Could not handle envelope!")


class LoggingReceiver(SMTPReceiver):
    """Message handler for --log mode"""

    def handle_envelope(self, envelope):
        now = datetime.datetime.now().strftime(' %Y-%m-%d %H:%M:%S ')
        print(now.center(79, '='))
        print(str(envelope.message))


class RelayMixin(object):
    def configure_relay(self):
        # relay_host = smtplib.SMTP_SSL(hostname, self.port)
        relay_host = smtplib.SMTP(self.relay_host, self.relay_port)
        relay_host.set_debuglevel(0)
        # relay_host.starttls()
        # relay_host.login(self.username, self.password)
        return relay_host

    def deliver(self, message, recipients, sender):
        relay_host = self.configure_relay()
        try:
            relay_host.sendmail(sender, recipients, str(message))
        finally:
            relay_host.quit()


class SMTPForwarder(SMTPReceiver, RelayMixin):
    def __init__(self, receiver_host, receiver_port, relay_host, relay_port):
        super(SMTPForwarder, self).__init__(receiver_host, receiver_port)
        self.relay_host = relay_host
        self.relay_port = relay_port

    def translate_recipients(self, rcpttos):
        """May be overridden in subclasses.

        Given a list of recipients, return a list of target recipients.
        By default, processes each recipient using translate_recipient.
        """

        return [recipient
                for rcptto in rcpttos
                for recipient in self.translate_recipient(rcptto)]

    def translate_recipient(self, rcptto):
        """Should be overridden in subclasses.

        Given a single recipient, return a list of target recipients.
        By default, returns the input recipient.
        """

        return [rcptto]

    def handle_envelope(self, envelope):
        recipients = self.translate_recipients(envelope.rcpttos)
        self.deliver(envelope.message, recipients, envelope.mailfrom)

    def handle_error(self, envelope):
        tb = ''.join(traceback.format_exc())
        now = now_string()

        with open('error/%s.mail' % now, 'w') as fp:
            fp.write(str(envelope.message))

        with open('error/%s.json' % now, 'w') as fp:
            metadata = {
                'mailfrom': envelope.mailfrom,
                'rcpttos': envelope.rcpttos,
            }
            json.dump(metadata, fp)

        with open('error/%s.txt' % now, 'w') as fp:
            fp.write('From %s\n' % envelope.mailfrom)
            fp.write('To %s\n\n' % envelope.rcpttos)
            fp.write('%s\n' % tb)
            fp.write(str(envelope.message))


def validate_address(v):
    host, port = v.split(':')
    port = int(port)
    return host, port


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--listen',
        type=validate_address,
        default=('0.0.0.0', 9000),
        help='hostname and port to listen on (default 0.0.0.0:9000)',
    )
    parser.add_argument(
        '--relay',
        type=validate_address,
        default=('127.0.0.1', 25),
        help='hostname and port to relay to (default 127.0.0.1:25)',
    )
    parser.add_argument(
        '--log',
        action='store_true',
        help='instead of relaying email, log all received',
    )
    args = parser.parse_args()
    if not args.log and not args.relay:
        parser.error("Must specify either --relay or --log")

    receiver_host, receiver_port = args.listen

    if args.log:
        server = LoggingReceiver(receiver_host, receiver_port)

    else:
        relay_host, relay_port = args.relay
        server = SMTPForwarder(
            receiver_host, receiver_port,
            relay_host, relay_port)

    poller = threading.Thread(
        target=asyncore.loop,
        kwargs={'timeout': 0.1, 'use_poll': True})
    poller.start()


if __name__ == "__main__":
    main()
