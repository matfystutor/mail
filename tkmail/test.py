import sys
import time
import logging
import asyncore
import threading

from emailtunnel import SMTPReceiver, Envelope, Message
from tkmail.server import TKForwarder
import emailtunnel.send

envelopes = []

def deliver_local(message, recipients, sender):
    logging.info("deliver_local: From: %r To: %r Subject: %r"
        % (sender, recipients, message.subject))
    envelope = Envelope(message, sender, recipients)
    envelopes.append(envelope)

class DumpReceiver(SMTPReceiver):
    def handle_envelope(self, envelope):
        envelopes.append(envelope)


class RecipientTest(object):
    def get_envelopes(self):
        envelopes = []
        for i, recipient in enumerate(self._recipients):
            envelopes.append(
                ('-F', 'recipient_test@localhost',
                 '-T', '%s@TAAGEKAMMERET.dk' % recipient,
                 '-s', '%s_%s' % (id(self), i),
                 '-I', 'X-test-id', self.get_test_id()))
        return envelopes

    def get_test_id(self):
        return str(id(self))

    def check_envelopes(self, envelopes):
        recipients = []
        for i, envelope in enumerate(envelopes):
            message = envelope.message
            if envelope.mailfrom != 'recipient_test@localhost':
                raise AssertionError('Bad sender %r' % envelope.mailfrom)
            recipients += envelope.rcpttos
        self.check_recipients(recipients)


class SameRecipientTest(RecipientTest):
    def __init__(self, *recipients):
        self._recipients = recipients

    def check_recipients(self, recipients):
        if len(recipients) != len(self._recipients):
            raise AssertionError(
                "Bad recipient count: %r vs %r" %
                (recipients, self._recipients))
        if any(x != recipients[0] for x in recipients):
            raise AssertionError("Recipients not the same: %r" % recipients)


class MultipleRecipientTest(RecipientTest):
    def __init__(self, recipient):
        self._recipients = [recipient]

    def check_recipients(self, recipients):
        if len(recipients) <= 1:
            raise AssertionError("Only %r recipients" % len(recipients))


def main():
    relayer_port = 11110
    dumper_port = 11111
    relayer = TKForwarder('127.0.0.1', relayer_port,
                          '127.0.0.1', dumper_port,
                          year=2014)
    # dumper = DumpReceiver('127.0.0.1', dumper_port)
    relayer.deliver = deliver_local

    poller = threading.Thread(
        target=asyncore.loop,
        kwargs={'timeout': 0.1, 'use_poll': True})
    poller.start()

    tests = [
        SameRecipientTest('FORM13', 'FORM2013', 'FORM1314', 'GFORM14'),
        SameRecipientTest('FORM', 'BEST-CERM-INKA-KASS-nf-PR-SEKR-VC'),
        MultipleRecipientTest('BEST'),
        MultipleRecipientTest('BESTFU'),
        MultipleRecipientTest('FU'),
        MultipleRecipientTest('ADMIN'),
        MultipleRecipientTest('engineering'),
        MultipleRecipientTest('revy+revyteknik'),
        MultipleRecipientTest('tke'),
    ]
    test_envelopes = {
        test.get_test_id(): []
        for test in tests
    }

    for test in tests:
        for envelope in test.get_envelopes():
            envelope = [str(x) for x in envelope]
            envelope += ['--relay', '127.0.0.1:%s' % relayer_port]
            print(repr(envelope))
            emailtunnel.send.main(*envelope, body='Hej')

    logging.debug("Sleep for a bit...")
    time.sleep(1)
    logging.debug("%s envelopes" % len(envelopes))

    for envelope in envelopes:
        header = envelope.message.get_unique_header('X-test-id')
        test_envelopes[header].append(envelope)

    for i, test in enumerate(tests):
        try:
            test.check_envelopes(test_envelopes[test.get_test_id()])
        except AssertionError as e:
            logging.error("Test %s failed: %s" % (i, e))
        else:
            logging.info("Test %s succeeded" % i)

    sys.exit()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    main()
