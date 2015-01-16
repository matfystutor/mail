import os
import re
import sys
import json
import logging
import datetime
import textwrap
import traceback

import email.header

from emailtunnel import SMTPForwarder, Message

import tkmail.address


def now_string():
    """Return the current date and time as a string."""
    return datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S.%f")


class TKForwarder(SMTPForwarder):
    ERROR_TEMPLATE = """
    This is the mail system of TAAGEKAMMERET.

    The following exception was raised when processing the message below:

    {traceback}

    This exception will not be reported again before the mail server has
    been restarted.

    Envelope sender: {mailfrom}
    Envelope recipients: {rcpttos}
    Envelope message:

    {message}
    """

    ERROR_TEMPLATE_CONSTRUCTION = """
    This is the mail system of TAAGEKAMMERET.

    The following exception was raised when CONSTRUCTING AN ENVELOPE:

    {traceback}

    This exception will not be reported again before the mail server has
    been restarted.

    Raw data:

    {data}
    """

    def __init__(self, *args, **kwargs):
        self.year = kwargs.pop('year')
        self.exceptions = set()
        super(TKForwarder, self).__init__(*args, **kwargs)

    def startup_log(self):
        logging.info(
            'TKForwarder listening on %s:%s, relaying to port %s, GF year %s'
            % (self.host, self.port, self.relay_port, self.year))

    def log_receipt(self, peer, envelope):
        mailfrom = envelope.mailfrom
        rcpttos = envelope.rcpttos
        message = envelope.message

        if type(mailfrom) == str:
            sender = '<%s>' % mailfrom
        else:
            sender = repr(mailfrom)

        if type(rcpttos) == list and all(type(x) == str for x in rcpttos):
            rcpttos = [re.sub(r'@(T)AAGE(K)AMMERET\.dk$', r'@@\1\2', x,
                              0, re.I)
                       for x in rcpttos]
            if len(rcpttos) == 1:
                recipients = '<%s>' % rcpttos[0]
            else:
                recipients = ', '.join('<%s>' % x for x in rcpttos)
        else:
            recipients = repr(rcpttos)

        logging.info("Subject: %r From: %s To: %s"
                     % (str(message.subject), sender, recipients))

    def log_delivery(self, message, recipients, sender):
        recipients = ', '.join('<%s>' % x for x in recipients)
        logging.info('Subject: %r To: %s'
                     % (str(message.subject), recipients))

    def translate_subject(self, envelope):
        subject = envelope.message.subject
        subject_decoded = str(subject)

        if '[TK' in subject_decoded:
            # No change
            return None

        try:
            parts = subject._parts
        except AttributeError:
            parts = email.header.decode_header(subject_decoded)

        # No space in '[TK]', since the parts are joined by spaces.
        subject_parts = [('[TK]', None)] + list(parts)
        return email.header.make_header(subject_parts)

    def translate_recipient(self, rcptto):
        name, domain = rcptto.split('@')
        return tkmail.address.translate_recipient(self.year, name)

    def get_envelope_mailfrom(self, envelope):
        return 'admin@TAAGEKAMMERET.dk'

    def log_invalid_recipient(self, envelope, exn):
        # Use logging.info instead of the default logging.error
        logging.info('Invalid recipient: %r' % (exn.args,))

    def handle_invalid_recipient(self, envelope, exn):
        self.store_failed_envelope(
            envelope, str(exn), 'Invalid recipient: %s' % exn)

    def handle_error(self, envelope, str_data):
        exc_value = sys.exc_info()[1]
        exc_typename = type(exc_value).__name__
        filename, line, function, text = traceback.extract_tb(
            sys.exc_info()[2])[0]

        tb = ''.join(traceback.format_exc())
        if envelope:
            self.store_failed_envelope(
                envelope, str(tb),
                '%s: %s' % (exc_typename, exc_value))

        exc_key = (filename, line, exc_typename)

        if exc_key not in self.exceptions:
            self.exceptions.add(exc_key)
            self.forward_to_admin(envelope, str_data, tb)

    def forward_to_admin(self, envelope, str_data, tb):
        # admin_emails = tkmail.address.get_admin_emails()
        admin_emails = ['mathiasrav@gmail.com']

        sender = recipient = 'admin@TAAGEKAMMERET.dk'

        if envelope:
            subject = '[TK-mail] Unhandled exception in processing'
            body = textwrap.dedent(self.ERROR_TEMPLATE).format(
                traceback=tb, mailfrom=envelope.mailfrom,
                rcpttos=envelope.rcpttos, message=envelope.message)

        else:
            subject = '[TK-mail] Could not construct envelope'
            body = textwrap.dedent(self.ERROR_TEMPLATE_CONSTRUCTION).format(
                traceback=tb, data=str_data)

        admin_message = Message.compose(
            sender, recipient, subject, body)
        admin_message.add_header('Auto-Submitted', 'auto-replied')

        self.deliver(admin_message, admin_emails, sender)

    def store_failed_envelope(self, envelope, description, summary):
        now = now_string()

        try:
            os.mkdir('error')
        except FileExistsError:
            pass

        with open('error/%s.mail' % now, 'wb') as fp:
            fp.write(envelope.message.as_bytes())

        with open('error/%s.json' % now, 'w') as fp:
            metadata = {
                'mailfrom': envelope.mailfrom,
                'rcpttos': envelope.rcpttos,
                'subject': str(envelope.message.subject),
                'date': envelope.message.get_header('Date'),
                'summary': summary,
            }
            json.dump(metadata, fp)

        with open('error/%s.txt' % now, 'w') as fp:
            fp.write('From %s\n' % envelope.mailfrom)
            fp.write('To %s\n\n' % envelope.rcpttos)
            fp.write('%s\n' % description)
            fp.write(str(envelope.message))
