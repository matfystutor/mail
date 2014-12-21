import os
import json
import logging
import datetime
import traceback

from emailtunnel import SMTPForwarder, InvalidRecipient

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

    def handle_error(self, envelope):
        tb = ''.join(traceback.format_exc())
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
            fp.write('%s\n' % tb)
            fp.write(str(envelope.message))
