import io
import os
import re
import json
try:
    import requests
except ImportError:
    print("You must `pip install requests`!")
    requests = None
from emailtunnel import RelayMixin


class MailholeRelayMixin(RelayMixin):
    mailhole_pattern = r'^.*@(hotmail|msn|live|outlook)\.\w+$'

    def get_mailhole_key(self):
        return os.getenv('MAILHOLE_KEY')

    def should_mailhole(self, message, recipient, sender):
        return bool(re.match(self.mailhole_pattern, recipient))

    def deliver_mailhole(self, original_envelope, message, recipients, sender):
        mailhole_url = os.environ.get('MAILHOLE_URL', 'https://mail.tket.dk')
        mailhole_key = self.get_mailhole_key()
        if not mailhole_key:
            raise Exception("You must set MAILHOLE_KEY env var!")
        if not requests:
            raise Exception("You must pip install requests!")
        with requests.Session() as session:
            orig_message_bytes = re.sub(br'(\r\n|\n|\r)', b'\r\n',
                                        original_envelope.message.as_bytes())
            message_bytes = re.sub(br'(\r\n|\n|\r)', b'\r\n',
                                   message.as_binary())
            data = dict(
                key=mailhole_key,
                mail_from=sender,
                rcpt_tos=json.dumps(recipients),
                orig_mail_from=original_envelope.mailfrom,
                orig_rcpt_tos=json.dumps(original_envelope.rcpttos),
            )
            files = dict(
                orig_message_bytes=('orig_message.msg',
                                    io.BytesIO(orig_message_bytes)),
                message_bytes=('message.msg', io.BytesIO(message_bytes)),
            )
            response = session.post(
                mailhole_url + '/api/submit/', data=data, files=files)
            text = response.text
            status = response.status_code
            if status != 200 or text.strip() != '250 OK':
                raise Exception('From %r to %r: HTTP %s %r' %
                                (sender, recipients, status,
                                 text.splitlines()[:200]))
            fake_rcpt = 'https://mail.tket.dk/%s' % ','.join(recipients)
            self.log_delivery(message, [fake_rcpt], sender)

    def forward(self, original_envelope, message, recipients, sender):
        mailhole_rcpts = []
        ordinary_rcpts = []
        for rcpt in recipients:
            if self.should_mailhole(message, rcpt, sender):
                mailhole_rcpts.append(rcpt)
            else:
                ordinary_rcpts.append(rcpt)
        if mailhole_rcpts:
            if not self.get_mailhole_key():
                raise Exception("You must set MAILHOLE_KEY env var!")
            if not requests:
                raise Exception("You must `pip install requests`!")
            self.deliver_mailhole(original_envelope,
                                  message, mailhole_recipients, sender)
        if ordinary_rcpts:
            self.deliver(message, ordinary_rcpts, sender)


assert re.match(MailholeRelayMixin.mailhole_pattern, 'test@hotmail.com')
assert re.match(MailholeRelayMixin.mailhole_pattern, 'test@msn.dk')
assert re.match(MailholeRelayMixin.mailhole_pattern, 'test@live.ru')
assert re.match(MailholeRelayMixin.mailhole_pattern, 'test@outlook.net')
assert not re.match(MailholeRelayMixin.mailhole_pattern, 'test@gmail.com')
assert not re.match(MailholeRelayMixin.mailhole_pattern, 'outlook@gmail.com')
