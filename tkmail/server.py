import os
import sys
import json
import logging
import datetime
import textwrap
import traceback

from emailtunnel import SMTPForwarder, InvalidRecipient, Message

import tkmail.address


def now_string():
    """Return the current date and time as a string."""
    return datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S.%f")


class TKForwarder(SMTPForwarder):
    def __init__(self, *args, **kwargs):
        self.year = kwargs.pop('year')
        super(TKForwarder, self).__init__(*args, **kwargs)

    def translate_subject(self, envelope):
        subject = envelope.message.subject
        if '[TK' in subject:
            return subject
        else:
            return '[TK] %s' % subject

    def translate_recipient(self, rcptto):
        name, domain = rcptto.split('@')
        return tkmail.address.translate_recipient(self.year, name)

    def handle_invalid_recipient(self, envelope, exn):
        self.store_failed_envelope(
            envelope, str(exn), 'Invalid recipient: %s' % exn)

    def handle_error(self, envelope):
        exc_type, exc_value, tb = sys.exc_info()
        tb = ''.join(traceback.format_exc())
        self.store_failed_envelope(
            envelope, str(tb),
            '%s: %s' % (type(exc_value).__name__, exc_value))

        admin_emails = tkmail.address.get_admin_emails()
        # admin_emails = ['mathiasrav@gmail.com']

        sender = recipient = 'admin@TAAGEKAMMERET.dk'

        subject = '[TK-mail] Unhandled exception in processing'
        body = textwrap.dedent("""
        This is the mail system of TAAGEKAMMERET.

        The following exception was raised when processing the message below:

        {traceback}

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

        with open('error/%s.mail' % now, 'w') as fp:
            fp.write(str(envelope.message))

        with open('error/%s.json' % now, 'w') as fp:
            metadata = {
                'mailfrom': envelope.mailfrom,
                'rcpttos': envelope.rcpttos,
                'subject': envelope.message.subject,
                'date': envelope.message.get_header('Date'),
                'summary': summary,
            }
            json.dump(metadata, fp)

        with open('error/%s.txt' % now, 'w') as fp:
            fp.write('From %s\n' % envelope.mailfrom)
            fp.write('To %s\n\n' % envelope.rcpttos)
            fp.write('%s\n' % description)
            fp.write(str(envelope.message))
