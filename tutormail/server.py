# encoding: utf8
import datetime
import email.utils
import itertools
import json
import os
import re
import sys
import textwrap
import traceback

from emailtunnel import SMTPForwarder, Message, InvalidRecipient, logger
from emailtunnel.mailhole import MailholeRelayMixin

from django.db import connection
from django.conf import settings

from mftutor.aliases.models import resolve_alias
from mftutor.tutor.models import Tutor, TutorGroup, RusClass, Rus


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


def now_string():
    """Return the current date and time as a string."""
    return datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S.%f")


class ForwardToAdmin(Exception):
    pass


def get_tutorprofile_email(tp):
    # Avoid blacklisting by relaying through @post.au.dk addresses.
    # valid_studentnumber = re.match(r'^201\d+$', tp.studentnumber)
    # if tp.email.endswith('@gmail.com') and valid_studentnumber:
    #     return '%s@post.au.dk' % tp.studentnumber
    return tp.email


class TutorForwarder(SMTPForwarder, MailholeRelayMixin):
    REWRITE_FROM = True
    STRIP_HTML = True

    MAIL_FROM = 'admin@TAAGEKAMMERET.dk'

    ERROR_TEMPLATE = """
    Nedenstående email blev ikke leveret til nogen.

    {reason}

    {message}
    """

    def __init__(self, *args, **kwargs):
        self.gf_year = kwargs.pop('gf_year', None)
        self.tutor_year = kwargs.pop('tutor_year', None)
        self.rus_year = kwargs.pop('rus_year', None)

        years = (self.gf_year, self.tutor_year, self.rus_year)
        if all(years):
            self.year_log = ("Year from kwargs: (%s, %s, %s)" %
                             (self.gf_year, self.tutor_year, self.rus_year))
        else:
            if any(years):
                logger.error("must specify all of gf_year, tutor_year, " +
                             "rus_year or none of them")
            self.gf_year = settings.YEAR
            self.tutor_year = settings.TUTORMAIL_YEAR
            self.rus_year = settings.RUSMAIL_YEAR
            self.year_log = ("Year from mftutor.settings: (%s, %s, %s)" %
                             (self.gf_year, self.tutor_year, self.rus_year))

        self.gf_groups = kwargs.pop(
            'gf_groups', settings.GF_GROUPS)
        self.rusclass_base = kwargs.pop(
            'rusclass_base', settings.RUSCLASS_BASE)
        super(TutorForwarder, self).__init__(*args, **kwargs)

        self.exceptions = set()

    def should_mailhole(self, message, recipient, sender):
        # Send everything to mailhole
        return True

    def startup_log(self):
        logger.info('TutorForwarder listening on %s:%s, ' +
                    'relaying to mailhole. %s',
                    self.host, self.port, self.year_log)

    def reject(self, envelope):
        if envelope.mailfrom == '<>':
            # RFC 5321, 4.5.5. Messages with a Null Reverse-Path:
            # "[Automated email processors] SHOULD NOT reply to messages
            # with a null reverse-path, and they SHOULD NOT add a non-null
            # reverse-path, or change a null reverse-path to a non-null one,
            # to such messages when forwarding."
            # Since we would forward this message with a non-null reverse-path,
            # we should reject it instead.
            return True
        rcpttos = tuple(r.lower() for r in envelope.rcpttos)
        subject = str(envelope.message.subject)
        return (rcpttos == ('webfar@matfystutor.dk',)
                and ('Delayed Mail' in subject
                     or 'Undelivered Mail Returned to Sender' in subject))

    def handle_envelope(self, envelope, peer):
        try:
            if self.reject(envelope):
                description = summary = 'Rejected due to reject()'
                self.store_failed_envelope(envelope, description, summary)
                return
            return super(TutorForwarder, self).handle_envelope(envelope, peer)
        except ForwardToAdmin as e:
            self.forward_to_admin(envelope, e.args[0])
        finally:
            connection.close()

    def forward(self, original_envelope, message, recipients, sender):
        if self.REWRITE_FROM:
            del message.message["DKIM-Signature"]
            orig_from = message.get_header("From")
            parsed = email.utils.getaddresses([orig_from])
            orig_name = parsed[0][0]
            name = "%s via matfystutor" % orig_name
            addr = "webfar@matfystutor.dk"
            new_from = email.utils.formataddr((name, addr))
            message.set_unique_header("From", new_from)
            message.set_unique_header("Reply-To", orig_from)
        if self.STRIP_HTML:
            from emailtunnel.extract_text import get_body_text

            del message.message["DKIM-Signature"]
            t = get_body_text(message.message)
            message.set_unique_header("Content-Type", "text/plain")
            del message.message["Content-Transfer-Encoding"]
            charset = email.charset.Charset("utf-8")
            charset.header_encoding = charset.body_encoding = email.charset.QP
            message.message.set_payload(t, charset=charset)

        super().forward(original_envelope, message, recipients, sender)

    def get_envelope_mailfrom(self, envelope):
        return self.MAIL_FROM.lower()

    def translate_recipient(self, rcptto):
        name, domain = rcptto.split('@')
        if name == 'alle':
            raise ForwardToAdmin('Mail til alle')
        if name == 'wiki':
            raise InvalidRecipient(name)
        if name == 'ravtest':
            return ['mathiasrav@outlook.dk']
        groups = self.get_groups(name)
        if groups:
            emails = []
            if any(g[0].handle == 'best' for g in groups):
                emails.append('matfys.udd.nat@au.dk')
                groups = [g for g in groups if g[0].handle != 'best']
            emails += self.get_group_emails(name, groups)
            if not emails:
                raise ForwardToAdmin('Grupper er tomme: %r' % (groups,))
            return emails

        tutors_only, rusclasses = self.get_rusclasses(name)
        if rusclasses is not None:
            emails = self.get_rusclass_emails(tutors_only, rusclasses)
            if not emails:
                raise ForwardToAdmin('Ingen tutor/rus-modtagere: %r' %
                                     (groups,))
            return emails

        raise InvalidRecipient(name)

    def get_groups(self, recipient):
        """Get all TutorGroups that an alias refers to."""
        try:
            group_names = resolve_alias(recipient)
        except Exception:
            logger.exception("resolve_alias raised an exception - " +
                             "reconnecting to the database and trying again")
            # https://code.djangoproject.com/ticket/21597#comment:29
            connection.close()
            group_names = resolve_alias(recipient)
        groups = []
        for name in group_names:
            group_and_year = self.get_group(name)
            if group_and_year is not None:
                groups.append(group_and_year)
        return groups

    def get_group(self, group_name):
        """Resolves a concrete group name to a (group, year)-tuple.

        Returns None if the group name is invalid,
        or a tuple (group, year) where group is a TutorGroup
        and year is the year to find the tutors in.
        """

        # Find the year
        group_name = group_name.lower()
        if group_name in self.gf_groups:
            year = self.gf_year
        elif group_name.startswith('g') and group_name[1:] in self.gf_groups:
            year = self.gf_year - 1
            group_name = group_name[1:]
        else:
            year = self.tutor_year

        # Is name a tutorgroup?
        try:
            group = TutorGroup.objects.get(handle=group_name, year=year)
        except TutorGroup.DoesNotExist:
            return None

        # Disallow 'alle'
        if group.handle == 'alle':
            return None

        return (group, year)

    def get_group_emails(self, name, groups):
        emails = []
        for group, year in groups:
            # TODO: After TutorGroup has a year field, this year-filter is
            # perhaps unwanted/unnecessary.
            group_tutors = Tutor.objects.filter(
                groups=group, year=year,
                early_termination__isnull=True)
            group_emails = [get_tutorprofile_email(tutor.profile) for tutor in group_tutors]
            emails += [email for email in group_emails
                       if email is not None]

        # Remove duplicate email addresses
        return sorted(set(emails))

    def get_rusclasses(self, recipient):
        """(tutors_only, list of RusClass)"""
        year = self.rus_year

        tutors_only_prefix = 'tutor+'
        if recipient.startswith(tutors_only_prefix):
            recipient = recipient[len(tutors_only_prefix):]
            tutors_only = True
        else:
            tutors_only = False

        rusclasses = None

        for official, handle, internal in self.rusclass_base:
            if recipient == handle:
                rusclasses = list(RusClass.objects.filter(
                    year=year,
                    handle__startswith=recipient))

        if rusclasses is None:
            try:
                rusclasses = [RusClass.objects.get(year=year, handle=recipient)]
            except RusClass.DoesNotExist:
                pass

        return (tutors_only, rusclasses)

    def get_rusclass_emails(self, tutors_only, rusclasses):
        tutor_emails = [
            get_tutorprofile_email(tutor.profile)
            for tutor in Tutor.objects.filter(rusclass__in=rusclasses)
        ]
        if tutors_only:
            rus_emails = []
        else:
            rus_emails = [
                get_tutorprofile_email(rus.profile)
                for rus in Rus.objects.filter(rusclass__in=rusclasses)
            ]

        emails = tutor_emails + rus_emails

        return sorted(set(email for email in emails if email))

    def log_receipt(self, peer, envelope):
        mailfrom = envelope.mailfrom
        rcpttos = envelope.rcpttos
        message = envelope.message

        if type(mailfrom) == str:
            sender = '<%s>' % mailfrom
        else:
            sender = repr(mailfrom)

        if type(rcpttos) == list and all(type(x) == str for x in rcpttos):
            recipients = ', '.join('<%s>' % x for x in rcpttos)
        else:
            recipients = repr(rcpttos)

        logger.info("Subject: %r From: %s To: %s",
                    str(message.subject), sender, recipients)

    def log_delivery(self, message, recipients, sender):
        recipients_string = abbreviate_recipient_list(recipients)
        logger.info('Subject: %r To: %s',
                    str(message.subject), recipients_string)

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
            self.forward_to_admin(envelope, tb)

    def forward_to_admin(self, envelope, reason):
        admin_emails = ['mathiasrav@gmail.com']
        sender = recipient = 'webfar@matfystutor.dk'

        subject = '[TutorForwarder] %s' % (reason[:50],)
        body = textwrap.dedent(self.ERROR_TEMPLATE).format(
            reason=reason, message=envelope.message)
        admin_message = Message.compose(
            sender, recipient, subject, body)
        admin_message.add_header('Auto-Submitted', 'auto-replied')
        self.deliver(admin_message, admin_emails, sender)

    def store_failed_envelope(self, envelope, description, summary):
        now = now_string()

        try:
            os.mkdir('error')
        except OSError:
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
