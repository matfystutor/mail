import io
import os
import re
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

    def deliver_mailhole(self, message, recipients, sender, mailhole_key):
        with requests.Session() as session:
            message_bytes = re.sub(br'(\r\n|\n|\r)', b'\r\n',
                                   message.as_bytes())
            for rcpt in recipients:
                data = dict(
                    key=mailhole_key,
                    mail_from=sender,
                    rcpt_to=rcpt,
                )
                files = dict(
                    message_bytes=('message.msg', io.BytesIO(message_bytes)),
                )
                response = session.post(
                    'https://mail.tket.dk/api/submit/', data=data, files=files)
                text = response.text
                status = response.status_code
                if status != 200 or text.strip() != '250 OK':
                    raise Exception('From %r to %r: HTTP %s %r' %
                                    (sender, rcpt, status,
                                     text.splitlines()[:200]))
                fake_rcpt = 'https://mail.tket.dk/%s' % rcpt
                self.log_delivery(message, [fake_rcpt], sender)

    def deliver(self, message, recipients, sender):
        mailhole_rcpts = []
        ordinary_rcpts = []
        for rcpt in recipients:
            if self.should_mailhole(message, rcpt, sender):
                mailhole_rcpts.append(rcpt)
            else:
                ordinary_rcpts.append(rcpt)
        if mailhole_rcpts:
            mailhole_key = self.get_mailhole_key()
            if mailhole_key and requests:
                self.deliver_mailhole(message, mailhole_rcpts, sender,
                                      mailhole_key)
            else:
                ordinary_rcpts = recipients  # ordinary delivery to all
                if not mailhole_key:
                    print("You must set MAILHOLE_KEY env var!")
                if not requests:
                    print("You must `pip install requests`!")
        if ordinary_rcpts:
            super().deliver(message, ordinary_rcpts, sender)


assert re.match(MailholeRelayMixin.mailhole_pattern, 'test@hotmail.com')
assert re.match(MailholeRelayMixin.mailhole_pattern, 'test@msn.dk')
assert re.match(MailholeRelayMixin.mailhole_pattern, 'test@live.ru')
assert re.match(MailholeRelayMixin.mailhole_pattern, 'test@outlook.net')
assert not re.match(MailholeRelayMixin.mailhole_pattern, 'test@gmail.com')
assert not re.match(MailholeRelayMixin.mailhole_pattern, 'outlook@gmail.com')
