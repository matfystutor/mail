import json
import logging
import datetime

import email
import email.message
import email.mime.multipart
# from email.mime.base import MIMEBase
import email.charset
from email.charset import QP

import smtpd
import smtplib


class InvalidRecipient(Exception):
    pass


class Message(object):
    def __init__(self, message=None):
        # assert isinstance(message, str)
        if message:
            self.message = email.message_from_string(message)

            a = message.rstrip('\n')
            b = str(self).rstrip('\n')

            if a == b:
                logging.debug('Data is sane')
            else:
                a_lines = tuple(line.rstrip(' ') for line in a.splitlines())
                b_lines = tuple(line.rstrip(' ') for line in b.splitlines())
                if a_lines == b_lines:
                    logging.debug(
                        'Data is sane after stripping trailing spaces')
                else:
                    amavis_warnings = self.get_all_headers('X-Amavis-Alert')
                    if amavis_warnings:
                        logging.debug('Data is not sane; contains X-Amavis-Alert:')
                        for s in amavis_warnings:
                            logging.debug(s)
                    else:
                        logging.debug('Data is not sane')
                        logging.debug(repr(message))
                        logging.debug(repr(str(self)))
        else:
            self.message = email.mime.multipart.MIMEMultipart()

    def __str__(self):
        return str(self.message)

    def add_header(self, key, value):
        self.message.add_header(key, value)

    def get_header(self, key, default=None):
        return self.message.get(key, default)

    def get_all_headers(self, key):
        return self.message.get_all(key, [])

    def get_unique_header(self, key):
        values = self.message.get_all(key)
        if len(values) > 1:
            raise ValueError('Header %r occurs %s times' % (key, len(values)))
        elif len(values) == 0:
            raise KeyError('header %r' % key)
        else:
            return values[0]

    def set_unique_header(self, key, value):
        try:
            self.message.replace_header(key, value)
        except KeyError:
            self.message.add_header(key, value)

    def set_body_text(self, body, encoding):
        body_part = email.message.MIMEPart()
        if encoding:
            encoded = body.encode(encoding)
            body_part.set_payload(encoded)
            body_part.add_header(
                'Content-Type', 'text/plain')
            email.charset.add_charset(encoding, QP, QP)
            body_part.set_charset(encoding)
        else:
            body_part.set_payload(body)
            body_part.add_header('Content-Type', 'text/plain')
        self.message.set_payload(body_part)

    @property
    def subject(self):
        return self.get_unique_header('Subject')

    @subject.setter
    def subject(self, s):
        self.set_unique_header('Subject', s)

    @classmethod
    def compose(cls, from_, to, subject, body):
        message = cls()
        message.add_header('From', from_)
        message.add_header('To', to)
        message.subject = subject
        message.add_header(
            'Date',
            datetime.datetime.utcnow().strftime("%a, %d %b %Y %T +0000"))
        message.set_body_text(body, 'utf-8')
        return message


class Envelope(object):
    def __init__(self, message, mailfrom, rcpttos):
        """See also SMTPReceiver.process_message.

        mailfrom is a string; rcpttos is a list of recipients.
        """

        assert isinstance(message, Message)
        self.message = message
        self.mailfrom = mailfrom
        self.rcpttos = rcpttos


class ResilientSMTPChannel(smtpd.SMTPChannel):
    def collect_incoming_data(self, data):
        try:
            str_data = str(data, 'utf-8')
        except UnicodeDecodeError:
            logging.error('ResilientSMTPChannel.collect_incoming_data: ' +
                          'UnicodeDecodeError encountered; decoding with ' +
                          'errors=replace')
            str_data = data.decode('utf-8', 'replace')

        # str_data.encode('utf-8').decode('utf-8') will surely not raise
        # a UnicodeDecodeError in SMTPChannel.collect_incoming_data.
        super(ResilientSMTPChannel, self).collect_incoming_data(
            str_data.encode('utf-8'))

    def log_info(self, message, type_='info'):
        try:
            logger = getattr(logging, type_)
        except AttributeError:
            logger = logging.info

        logger(message)


class SMTPReceiver(smtpd.SMTPServer):
    channel_class = ResilientSMTPChannel

    def __init__(self, host, port):
        self.host = host
        self.port = port
        logging.debug('Initialize SMTPReceiver on %s:%s' % (host, port))
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
        logging.debug("Message received from peer %r" % (peer,))
        logging.info("From: %r To: %r Subject: %r"
            % (mailfrom, rcpttos, str(message.subject)))
        try:
            return self.handle_envelope(envelope)
        except:
            logging.exception("Could not handle envelope!")
            try:
                self.handle_error(envelope)
            except:
                logging.exception("handle_error threw exception")

            # Instruct the sender to retry sending the message later.
            return '451 Requested action aborted: error in processing'

    def handle_envelope(self, envelope):
        raise NotImplementedError()

    def handle_error(self, envelope):
        pass


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
        logging.info('From: %r To: %r Subject: %r'
                     % (sender, recipients, str(message.subject)))
        try:
            relay_host.sendmail(sender, recipients, str(message))
        finally:
            try:
                relay_host.quit()
            except smtplib.SMTPServerDisconnected:
                pass


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

        invalid = []
        recipients = []
        for rcptto in rcpttos:
            try:
                translated = self.translate_recipient(rcptto)
            except InvalidRecipient as e:
                if len(e.args) == 1:
                    invalid.append(e.args[0])
                else:
                    invalid.append(e)
            else:
                if isinstance(translated, str):
                    raise ValueError('translate_recipient must return a list, '
                                     'not a string')
                recipients += list(translated)
        if invalid:
            raise InvalidRecipient(invalid)
        return recipients

    def translate_recipient(self, rcptto):
        """Should be overridden in subclasses.

        Given a single recipient, return a list of target recipients.
        By default, returns the input recipient.
        """

        return [rcptto]

    def translate_subject(self, envelope):
        """Implement to translate the subject to something else.

        If None is returned, or NotImplementedError is raised,
        the subject is not changed.
        Otherwise, the subject of the message in the given envelope
        is changed to the returned value before being forwarded.
        """
        raise NotImplementedError()

    def get_envelope_mailfrom(self, envelope):
        """Compute the address to use as MAIL FROM.

        This is the Return-Path to which returned emails are sent.
        By default, returns the same MAIL FROM as the received envelope,
        but should be changed.
        """
        return envelope.mailfrom

    def handle_invalid_recipient(self, envelope, exn):
        pass

    def handle_envelope(self, envelope):
        subject = envelope.message.subject

        try:
            new_subject = self.translate_subject(envelope)
        except NotImplementedError:
            pass
        else:
            if new_subject is not None:
                envelope.message.subject = new_subject

        try:
            recipients = self.translate_recipients(envelope.rcpttos)
        except InvalidRecipient as e:
            logging.error(repr(e))

            self.handle_invalid_recipient(envelope, e)

            # 550 is not valid after DATA according to
            # http://www.greenend.org.uk/rjk/tech/smtpreplies.html
            return '554 Transaction failed: mailbox unavailable'

        mailfrom = self.get_envelope_mailfrom(envelope)

        self.deliver(envelope.message, recipients, mailfrom)
