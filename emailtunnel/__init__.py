"""Lightweight email forwarding framework.

The emailtunnel module depends heavily on the standard library classes
smtpd.SMTPServer and email.message.Message (and its subclasses).

The emailtunnel module exports the classes:
SMTPReceiver -- implementation of SMTPServer that handles errors in processing
RelayMixin -- mixin providing a `deliver` method to send email
SMTPForwarder -- implementation of SMTPReceiver that forwards emails
LoggingReceiver -- simple implementation of SMTPReceiver that logs via print()
Message -- encapsulation of email.message.Message
Envelope -- connecting a Message to its sender and recipients

The emailtunnel module exports the exception:
InvalidRecipient -- raised to return SMTP 550 to remote peers

When the module is run from the command-line, SMTPForwarder is instantiated to
run an open SMTP relay.

See also the submodule:
emailtunnel.send -- simple construction and sending of email
"""

from io import BytesIO
import os
import re
import six
import sys
import logging
import datetime
import itertools

import email
import email.mime.multipart
try:
    from email.generator import BytesGenerator
except ImportError:
    pass
from email.header import Header
from email.charset import QP

import smtpd
import smtplib


def abbreviate_recipient_list(recipients):
    if all('@' in rcpt for rcpt in recipients):
        parts = [rcpt.split('@', 1) for rcpt in recipients]
        parts.sort(key=lambda x: (x[1].lower(), x[0].lower()))
        by_domain = [
            (domain, [a[0] for a in aa])
            for domain, aa in itertools.groupby(
                parts, key=lambda x: x[1])
        ]
        return ', '.join(
            '<%s@%s>' % (','.join(aa), domain)
            for domain, aa in by_domain)
    else:
        return ', '.join('<%s>' % x for x in recipients)


def _fix_eols(data):
    if isinstance(data, six.string_types):
        return re.sub(r'(?:\r\n|\n|\r)', "\r\n", data)
    elif isinstance(data, six.binary_types):
        return re.sub(br'(?:\r\n|\n|\r)', b"\r\n", data)
    else:
        raise TypeError('data must be str or bytes, not %s'
                        % type(data).__name__)


def now_string():
    """Return the current date and time as a string."""
    return datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S.%f")


class InvalidRecipient(Exception):
    pass


class Message(object):
    def __init__(self, message=None):
        if message:
            assert isinstance(message, bytes)

            self.message = email.message_from_bytes(message)

            if not self._sanity_check(message):
                self._sanity_log_invalid(message)

        else:
            self.message = email.mime.multipart.MIMEMultipart()

    def _sanity_check(self, message):
        a = message.rstrip(b'\n')
        b = self.as_binary().rstrip(b'\n')
        return a == b or self._sanity_strip(a) == self._sanity_strip(b)

    def _sanity_strip(self, data):
        data = re.sub(b': *', b': ', data)
        lines = re.split(br'[\r\n]+', data.rstrip())
        return tuple(line.rstrip() for line in lines)

    def _sanity_log_invalid(self, message):
        try:
            dirname = 'insane'
            basename = os.path.join(dirname, now_string())
            try:
                os.mkdir(dirname)
            except FileExistsError:
                pass
            with open(basename + '.in', 'ab') as fp:
                fp.write(message)
            with open(basename + '.out', 'ab') as fp:
                fp.write(self.as_binary())
            logging.debug(
                'Data is not sane; logging to %s' % (basename,))
        except:
            logging.exception(
                'Data is not sane and could not log to %s; continuing anyway'
                % (basename,))

    def __str__(self):
        return str(self.message)

    if six.PY3:
        def as_bytes(self):
            """Return the entire formatted message as a bytes object."""
            # Instead of using self.message.as_bytes() directly,
            # we copy and edit the implementation of email.Message.as_bytes
            # since it does not accept maxheaderlen, which we wish to set to 0
            # for transparency.

            policy = self.message.policy
            fp = BytesIO()
            g = BytesGenerator(fp,
                               mangle_from_=False,
                               maxheaderlen=0,
                               policy=policy)
            g.flatten(self.message, unixfrom=None)
            return fp.getvalue()

        def as_binary(self):
            return self.as_bytes()

    else:
        def as_binary(self):
            return self.message.as_string(unixfrom=None)

    def add_received_line(self, value):
        # This is a hack! email.message.Message does not support
        # adding headers in front of everything else.
        # We have to access the internal _headers API to do this.

        headers = list(self.message._headers)
        self.message._headers = []
        self.message['Received'] = value
        self.message._headers += headers

    def add_header(self, key, value):
        self.message[key] = value

    def get_header(self, key, default=None):
        return self.message.get(key, default)

    def get_all_headers(self, key):
        """Return a list of headers with the given key.

        If no headers are found, the empty list is returned.
        """

        return self.message.get_all(key, [])

    def get_unique_header(self, key):
        values = self.get_all_headers(key)
        if len(values) > 1:
            raise ValueError('Header %r occurs %s times' % (key, len(values)))
        elif len(values) == 0:
            raise KeyError('header %r' % (key,))
        else:
            return values[0]

    def set_unique_header(self, key, value):
        try:
            self.message.replace_header(key, value)
        except KeyError:
            self.message[key] = value

    def set_body_text(self, body, encoding):
        if six.PY3:
            body_part = email.message.MIMEPart()
        else:
            body_part = email.message.Message()
        if encoding:
            encoded = body.encode(encoding)
            body_part.set_payload(encoded)
            body_part['Content-Type'] = 'text/plain'
            email.charset.add_charset(encoding, QP, QP)
            body_part.set_charset(encoding)
        else:
            body_part.set_payload(body)
            body_part['Content-Type'] = 'text/plain'
        self.message.set_payload(body_part)

    @property
    def subject(self):
        try:
            subject = self.get_unique_header('Subject')
        except KeyError:
            subject = ''

        try:
            subject_parts = email.header.decode_header(subject)
        except email.errors.HeaderParseError:
            subject_parts = [(subject, None)]

        return email.header.make_header(subject_parts)

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


def ascii_prefix(bs):
    """Split bs into (x, y) such that x.encode('ascii') + y == bs."""
    s = bs.decode('ascii', 'replace')
    try:
        i = s.index('\ufffd')
    except ValueError:
        return (s, b'')

    # First i characters of bs are ascii,
    # meaning first i bytes of bs are ascii.
    x, y = s[:i], bs[i:]
    assert y and x.encode('ascii') + y == bs
    return x, y


class ResilientSMTPChannel(smtpd.SMTPChannel):
    """smtpd.SMTPChannel is not encoding agnostic -- it requires UTF-8.
    As a workaround, we interpret the bytes as latin1,
    since bytes.decode('latin1') never fails.
    This "string" is actually a Python 2-style bytestring,
    but the smtpd module should not care -- it blissfully thinks that
    everything is nice UTF-8.
    """

    def collect_incoming_data(self, data):
        str_data = data.decode('latin1')

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

    def handle_error(self):
        # The implementation of recv does not catch TimeoutError, causing the
        # default handle_error to report "uncaptured python exception".
        # This is misleading to the user as it sounds like an application bug,
        # when in fact it is caused by the remote peer not responding.
        exc_value = sys.exc_info()[1]
        if isinstance(exc_value, TimeoutError):
            logging.error("recv timed out; closing ResilientSMTPChannel")
            self.close()
        else:
            super(ResilientSMTPChannel, self).handle_error()


class SMTPReceiver(smtpd.SMTPServer):
    channel_class = ResilientSMTPChannel

    def __init__(self, host, port):
        self.host = host
        self.port = port
        super(SMTPReceiver, self).__init__((self.host, self.port), None)
        self.startup_log()

    def startup_log(self):
        logging.debug('Initialize SMTPReceiver on %s:%s'
                      % (self.host, self.port))

    def log_receipt(self, peer, envelope):
        ipaddr, port = peer
        mailfrom = envelope.mailfrom
        rcpttos = envelope.rcpttos
        message = envelope.message

        if type(mailfrom) == str:
            sender = '<%s>' % mailfrom
        else:
            sender = repr(mailfrom)

        if type(rcpttos) == list and all(type(x) == str for x in rcpttos):
            if len(rcpttos) == 1:
                recipients = 'To: <%s>' % rcpttos[0]
            else:
                recipients = 'To: %s' % ', '.join('<%s>' % x for x in rcpttos)
        else:
            recipients = 'To: %s' % (repr(rcpttos),)

        if ipaddr == '127.0.0.1':
            source = ''
        else:
            source = ' Peer: %s:%s' % (ipaddr, port)

        logging.info("Subject: %r From: %s %s%s"
                     % (str(message.subject), sender, recipients, source))

    def process_message(self, peer, mailfrom, rcpttos, str_data):
        """Overrides SMTPServer.process_message.

        peer is a tuple of (ipaddr, port).
        mailfrom is the raw sender address.
        rcpttos is a list of raw recipient addresses.
        data is the full text of the message.

        ResilientSMTPChannel packs the bytestring into a Python 2-style
        bytestring, which we unpack here.
        """

        data = str_data.encode('latin1')

        try:
            ipaddr, port = peer
            message = Message(data)
            envelope = Envelope(message, mailfrom, rcpttos)
        except:
            logging.exception("Could not construct envelope!")
            try:
                self.handle_error(None, str_data)
            except:
                logging.exception("handle_error(None) threw exception")
            return '451 Requested action aborted: error in processing'

        try:
            self.log_receipt(peer, envelope)
            return self.handle_envelope(envelope, peer)
        except:
            logging.exception("Could not handle envelope!")
            try:
                self.handle_error(envelope, str_data)
            except:
                logging.exception("handle_error threw exception")

            # Instruct the sender to retry sending the message later.
            return '451 Requested action aborted: error in processing'

    def handle_envelope(self, envelope, peer):
        raise NotImplementedError()

    def handle_error(self, envelope, str_data):
        pass


class LoggingReceiver(SMTPReceiver):
    """Message handler for --log mode"""

    def handle_envelope(self, envelope, peer):
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

    def log_delivery(self, message, recipients, sender):
        logging.info('To: %r From: %r Subject: %r'
                     % (recipients, sender, str(message.subject)))

    def deliver(self, message, recipients, sender):
        relay_host = self.configure_relay()
        self.log_delivery(message, recipients, sender)
        try:
            data = _fix_eols(message.as_binary())
            relay_host.sendmail(sender, recipients, data)
        finally:
            try:
                relay_host.quit()
            except smtplib.SMTPServerDisconnected:
                pass


class SMTPForwarder(SMTPReceiver, RelayMixin):
    def __init__(self, receiver_host, receiver_port, relay_host, relay_port):
        self.relay_host = relay_host
        self.relay_port = relay_port
        super(SMTPForwarder, self).__init__(receiver_host, receiver_port)

    def get_envelope_recipients(self, envelope):
        """May be overridden in subclasses.

        Given an envelope, return a list of target recipients.
        By default, processes each recipient using translate_recipient,
        sorts the result, filters out empty addresses and duplicates.
        """

        invalid = []
        recipients = []
        for rcptto in envelope.rcpttos:
            try:
                translated = self.translate_recipient(rcptto)
            except InvalidRecipient as e:
                if len(e.args) == 1:
                    invalid.append(e.args[0])
                else:
                    invalid.append(e)
            else:
                if isinstance(translated, str):
                    raise ValueError(
                        'translate_recipient must return a list, not a string')
                recipients += list(translated)

        if invalid:
            raise InvalidRecipient(invalid)

        # Remove falsy addresses (empty or None)
        recipients = [addy for addy in recipients if addy]
        # Remove duplicates
        recipients = sorted(set(recipients))

        return recipients

    def translate_recipient(self, rcptto):
        """Should be overridden in subclasses.

        Given a single recipient, return a list of target recipients.
        By default, returns the input recipient.
        """

        return [rcptto]

    def translate_subject(self, envelope):
        """Implement to translate the subject to something else.

        If None is returned, the subject is not changed.
        Otherwise, the subject of the message in the given envelope
        is changed to the returned value before being forwarded.
        """
        return None

    def get_envelope_mailfrom(self, envelope):
        """Compute the address to use as MAIL FROM.

        This is the Return-Path to which returned emails are sent.
        By default, returns the same MAIL FROM as the received envelope,
        but should be changed.
        """
        return envelope.mailfrom

    def get_envelope_received(self, envelope, peer):
        """Compute the value of the Received:-header to add.

        By default, we add a header with From, By, For and date information
        according to RFC 2821.

        The implementation may return None to disable the addition
        of the Received:-header.
        """

        ipaddr, port = peer
        return 'from %s\nby %s\nfor %s;\n%s' % (
            ipaddr, 'emailtunnel.local',
            ', '.join('<%s>' % rcpt for rcpt in envelope.rcpttos),
            datetime.datetime.utcnow().strftime(
                '%a, %e %b %Y %T +0000 (UTC)'),
        )

    def _get_envelope_received_header(self, envelope, peer):
        s = self.get_envelope_received(envelope, peer)
        if s is None:
            return None
        lines = [line.strip() for line in s.splitlines()]
        continuation_ws = '\t'
        linesep = '\n' + continuation_ws
        h = Header(linesep.join(lines),
                   header_name='Received',
                   continuation_ws=continuation_ws)
        return h

    def log_invalid_recipient(self, envelope, exn):
        logging.error(repr(exn))

    def handle_invalid_recipient(self, envelope, exn):
        pass

    def handle_envelope(self, envelope, peer):
        new_subject = self.translate_subject(envelope)
        if new_subject is not None:
            envelope.message.subject = new_subject

        try:
            recipients = self.get_envelope_recipients(envelope)
        except InvalidRecipient as exn:
            self.log_invalid_recipient(envelope, exn)

            self.handle_invalid_recipient(envelope, exn)

            return '550 Requested action not taken: mailbox unavailable'

        mailfrom = self.get_envelope_mailfrom(envelope)

        received = self._get_envelope_received_header(envelope, peer)

        if received is not None:
            envelope.message.add_received_line(received)

        self.deliver(envelope.message, recipients, mailfrom)
