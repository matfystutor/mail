import os
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
        if name.lower() == 'exceptiontest':
            raise ValueError("name is %r" % name)
        return tkmail.address.translate_recipient(self.year, name)

    def handle_invalid_recipient(self, envelope, exn):
        self.store_failed_envelope(envelope, str(exn))

    def handle_error(self, envelope):
        tb = ''.join(traceback.format_exc())
        self.store_failed_envelope(envelope, str(tb))

        admin_emails = tkmail.address.get_admin_emails()

        sender = recipient = 'admin@TAAGEKAMMERET.dk'

        admin_message = Message()
        admin_message.add_header('From', sender)
        admin_message.add_header('To', recipient)
        admin_message.subject = '[TK-mail] Unhandled exception in processing'
        admin_message.add_header(
            'Date', datetime.datetime.utcnow().strftime("%a, %d %b %Y %T +0000"))
        admin_message.add_header('Auto-Submitted', 'auto-replied')
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

        self.deliver(admin_message, admin_emails, sender)

    def store_failed_envelope(self, envelope, description):
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
            }
            json.dump(metadata, fp)

        with open('error/%s.txt' % now, 'w') as fp:
            fp.write('From %s\n' % envelope.mailfrom)
            fp.write('To %s\n\n' % envelope.rcpttos)
            fp.write('%s\n' % description)
            fp.write(str(envelope.message))
