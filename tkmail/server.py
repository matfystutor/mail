import os
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
    def __init__(self, *args, **kwargs):
        self.year = kwargs.pop('year')
        self.exceptions = set()
        super(TKForwarder, self).__init__(*args, **kwargs)

    def startup_log(self):
        logging.info(
            'TKForwarder listening on %s:%s, relaying to port %s, GF year %s'
            % (self.host, self.port, self.relay_port, self.year))

    def translate_subject(self, envelope):
        subject = envelope.message.subject
        subject_parts = email.header.decode_header(subject)
        subject_decoded = str(email.header.make_header(subject_parts))

        if '[TK' in subject_decoded:
            # No change
            return None
        else:
            # No space in '[TK]', since the parts are joined by spaces.
            subject_parts = [('[TK]', None)] + list(subject_parts)
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

    def handle_error(self, envelope):
        exc_value = sys.exc_info()[1]
        exc_typename = type(exc_value).__name__
        filename, line, function, text = traceback.extract_tb(
            sys.exc_info()[2])[0]

        tb = ''.join(traceback.format_exc())
        self.store_failed_envelope(
            envelope, str(tb),
            '%s: %s' % (exc_typename, exc_value))

        exc_key = (filename, line, exc_typename)

        if exc_key not in self.exceptions:
            self.exceptions.add(exc_key)
            self.forward_to_admin(envelope, tb)

    def forward_to_admin(self, envelope, tb):
        # admin_emails = tkmail.address.get_admin_emails()
        admin_emails = ['mathiasrav@gmail.com']

        sender = recipient = 'admin@TAAGEKAMMERET.dk'

        subject = '[TK-mail] Unhandled exception in processing'
        body = textwrap.dedent("""
        This is the mail system of TAAGEKAMMERET.

        The following exception was raised when processing the message below:

        {traceback}

        This exception will not be reported again before the mail server has
        been restarted.

        Envelope sender: {mailfrom}
        Envelope recipients: {rcpttos}
        Envelope message:

        {message}
        """).format(traceback=tb, mailfrom=envelope.mailfrom,
                    rcpttos=envelope.rcpttos, message=envelope.message)

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
