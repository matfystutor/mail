import time
import logging
logging.basicConfig(level=logging.DEBUG)
import smtplib
import asyncore
import threading

import email.header

from emailtunnel import SMTPReceiver, Envelope
from tutormail.server import TutorForwarder
import emailtunnel.send


envelopes = []


def deliver_local(message, recipients, sender):
    logging.info("deliver_local: From: %r To: %r Subject: %r"
                 % (sender, recipients, str(message.subject)))
    for recipient in recipients:
        if '@' not in recipient:
            raise smtplib.SMTPDataError(0, 'No @ in %r' % recipient)
    envelope = Envelope(message, sender, recipients)
    envelopes.append(envelope)


class DumpReceiver(SMTPReceiver):
    def handle_envelope(self, envelope):
        envelopes.append(envelope)


# class RecipientTest(object):
#     _recipients = []
# 
#     def get_envelopes(self):
#         envelopes = []
#         for i, recipient in enumerate(self._recipients):
#             envelopes.append(
#                 ('-F', 'recipient_test@localhost',
#                  '-T', '%s@TAAGEKAMMERET.dk' % recipient,
#                  '-s', '%s_%s' % (id(self), i),
#                  '-I', 'X-test-id', self.get_test_id()))
#         return envelopes
# 
#     def get_test_id(self):
#         return str(id(self))
# 
#     def check_envelopes(self, envelopes):
#         recipients = []
#         for i, envelope in enumerate(envelopes):
#             recipients += envelope.rcpttos
#         self.check_recipients(recipients)
# 
#     def check_recipients(self, recipients):
#         raise NotImplementedError()
# 
# 
# class SameRecipientTest(RecipientTest):
#     def __init__(self, *recipients):
#         self._recipients = recipients
# 
#     def check_recipients(self, recipients):
#         if len(recipients) != len(self._recipients):
#             raise AssertionError(
#                 "Bad recipient count: %r vs %r" %
#                 (recipients, self._recipients))
#         if any(x != recipients[0] for x in recipients):
#             raise AssertionError("Recipients not the same: %r" % recipients)
# 
# 
# class MultipleRecipientTest(RecipientTest):
#     def __init__(self, recipient):
#         self._recipients = [recipient]
# 
#     def check_recipients(self, recipients):
#         if len(recipients) <= 1:
#             raise AssertionError("Only %r recipients" % len(recipients))
# 
# 
# class SubjectRewriteTest(object):
#     def __init__(self, subject):
#         self.subject = subject
# 
#     def get_envelopes(self):
#         return [
#             ('-F', 'subject-test@localhost',
#              '-T', 'FORM13@TAAGEKAMMERET.dk',
#              '-s', self.subject,
#              '-I', 'X-test-id', self.get_test_id())
#         ]
# 
#     def check_envelopes(self, envelopes):
#         message = envelopes[0].message
# 
#         try:
#             output_subject_raw = message.get_unique_header('Subject')
#         except KeyError as e:
#             raise AssertionError('No Subject in message') from e
# 
#         input_header = email.header.make_header(
#             email.header.decode_header(self.subject))
# 
#         input_subject = str(input_header)
#         output_subject = str(message.subject)
# 
#         if '[TK' in input_subject:
#             expected_subject = input_subject
#         else:
#             expected_subject = '[TK] %s' % input_subject
# 
#         if output_subject != expected_subject:
#             raise AssertionError(
#                 'Bad subject: %r == %r turned into %r == %r, '
#                 'expected %r' % (self.subject, input_subject,
#                                  output_subject_raw, output_subject,
#                                  expected_subject))
# 
#     def get_test_id(self):
#         return str(id(self))
# 
# 
# class ErroneousSubjectTest(object):
#     def __init__(self, subject):
#         self.subject = subject
# 
#     def get_envelopes(self):
#         return [
#             ('-F', 'subject-test@localhost',
#              '-T', 'FORM13@TAAGEKAMMERET.dk',
#              '-s', self.subject,
#              '-I', 'X-test-id', self.get_test_id())
#         ]
# 
#     def check_envelopes(self, envelopes):
#         # If the message did not throw an error, we are happy
#         pass
# 
#     def get_test_id(self):
#         return str(id(self))
# 
# 
# class NoSubjectTest(object):
#     def get_envelopes(self):
#         return [
#             ('-F', 'no-subject-test@localhost',
#              '-T', 'FORM13@TAAGEKAMMERET.dk',
#              '-I', 'X-test-id', self.get_test_id())
#         ]
# 
#     def check_envelopes(self, envelopes):
#         # If the message did not throw an error, we are happy
#         pass
# 
#     def get_test_id(self):
#         return str(id(self))


def main():
    relayer_port = 11110
    dumper_port = 11111
    relayer = TutorForwarder('127.0.0.1', relayer_port,
                             '127.0.0.1', dumper_port,
                             gf_year=2015, tutor_year=2015, rus_year=2014)
    # dumper = DumpReceiver('127.0.0.1', dumper_port)
    relayer.deliver = deliver_local

    poller = threading.Thread(
        target=asyncore.loop,
        kwargs={'timeout': 0.1, 'use_poll': True})
    poller.start()

    # tests = [
    #     SameRecipientTest('FORM13', 'FORM2013', 'FORM1314', 'gFORM14'),
    #     SameRecipientTest('FORM', 'BEST-CERM-INKA-KASS-nf-PR-SEKR-VC'),
    #     MultipleRecipientTest('BEST'),
    #     MultipleRecipientTest('BESTFU'),
    #     MultipleRecipientTest('FU'),
    #     MultipleRecipientTest('ADMIN'),
    #     MultipleRecipientTest('engineering'),
    #     MultipleRecipientTest('revy+revyteknik'),
    #     MultipleRecipientTest('tke'),
    #     SubjectRewriteTest('=?UTF-8?Q?Gl=C3=A6delig_jul?='),
    #     SubjectRewriteTest('=?UTF-8?Q?Re=3A_=5BTK=5D_Gl=C3=A6delig_jul?='),
    #     # Invalid encoding a; should be skipped by ecre in email.header
    #     ErroneousSubjectTest('=?UTF-8?a?hello_world?='),
    #     # Invalid base64 data; email.header raises an exception
    #     ErroneousSubjectTest('=?UTF-8?b?hello_world?='),
    #     NoSubjectTest(),
    # ]
    # test_envelopes = {
    #     test.get_test_id(): []
    #     for test in tests
    # }

    # for test in tests:
    #     for envelope in test.get_envelopes():
    #         envelope = [str(x) for x in envelope]
    #         envelope += ['--relay', '127.0.0.1:%s' % relayer_port]
    #         print(repr(envelope))
    #         emailtunnel.send.main(*envelope, body='Hej')

    addresses = 'web gwebfar best alle galle dat1 it tutor+mok tutor+nano2'.split()
    for address in addresses:
        sender = 'test@localhost'
        recipient = '%s@matfystutor.dk' % address
        subject = 'Hej %s' % address
        emailtunnel.send.main(
            '-F', sender,
            '-T', recipient,
            '-s', subject,
            '--relay', '127.0.0.1:%s' % relayer_port,
            body='Hej')

    logging.debug("Sleep for a bit...")
    time.sleep(1)
    logging.debug("%s envelopes" % len(envelopes))

    print(envelopes)

    # for envelope in envelopes:
    #     try:
    #         header = envelope.message.get_unique_header('X-test-id')
    #     except KeyError:
    #         logging.error("Envelope without X-test-id")
    #         continue
    #     test_envelopes[header].append(envelope)

    # for i, test in enumerate(tests):
    #     for envelope in test_envelopes[test.get_test_id()]:
    #         received_objects = envelope.message.get_all_headers('Received')
    #         received = [str(o) for o in received_objects]
    #         print(repr(received))
    #     try:
    #         test_id = test.get_test_id()
    #         e = test_envelopes[test_id]
    #         if not e:
    #             raise AssertionError("No envelopes for test id %r" % test_id)
    #         test.check_envelopes(e)
    #     except AssertionError as e:
    #         logging.error("Test %s failed: %s" % (i, e))
    #     else:
    #         logging.info("Test %s succeeded" % i)

    logging.info("tutormail.test finished; you may Ctrl-C")


if __name__ == "__main__":
    main()
