import json
import logging
import smtplib
import datetime

import email
# import email.message
# from email.mime.base import MIMEBase
import smtpd


class InvalidRecipient(Exception):
    pass


class Message(object):
    def __init__(self, message):
        # assert isinstance(message, str)
        self.message = email.message_from_string(message)

        if message.rstrip('\n') == str(self).rstrip('\n'):
            logging.debug('Data is sane')
        else:
            logging.debug('Data is not sane')
            logging.debug(repr(message))
            logging.debug(repr(str(self)))

    def __str__(self):
        return str(self.message)

    def add_header(self, key, value):
        pass

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
            % (mailfrom, rcpttos, message.subject))
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
                     % (sender, recipients, message.subject))
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

    def translate_subject(self, subject):
        """Implement to translate the subject to something else."""
        raise NotImplementedError()

    def handle_envelope(self, envelope):
        subject = envelope.message.subject

        try:
            new_subject = self.translate_subject(subject)
        except NotImplementedError:
            pass
        else:
            envelope.message.subject = new_subject

        try:
            recipients = self.translate_recipients(envelope.rcpttos)
        except InvalidRecipient as e:
            logging.error(repr(e))

            # 550 is not valid after DATA according to
            # http://www.greenend.org.uk/rjk/tech/smtpreplies.html
            return '554 Transaction failed: mailbox unavailable'

        self.deliver(envelope.message, recipients, envelope.mailfrom)
