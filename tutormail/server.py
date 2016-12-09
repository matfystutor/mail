# encoding: utf8
import os
import sys
import json
import logging
import datetime
import textwrap
import traceback

import emailtunnel
from emailtunnel import SMTPForwarder, Message, InvalidRecipient

import django
import django.db

sys.path.append('/home/mftutor/web/web')
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mftutor.settings")
django.setup()

import mftutor.settings

from mftutor.aliases.models import resolve_alias
from mftutor.tutor.models import Tutor, TutorGroup, RusClass, Rus


def now_string():
    """Return the current date and time as a string."""
    return datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S.%f")


class ForwardToAdmin(Exception):
    pass


class TutorForwarder(SMTPForwarder):
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
                logging.error("must specify all of gf_year, tutor_year, " +
                              "rus_year or none of them")
            self.gf_year = mftutor.settings.YEAR
            self.tutor_year = mftutor.settings.TUTORMAIL_YEAR
            self.rus_year = mftutor.settings.RUSMAIL_YEAR
            self.year_log = ("Year from mftutor.settings: (%s, %s, %s)" %
                             (self.gf_year, self.tutor_year, self.rus_year))

        self.gf_groups = kwargs.pop(
            'gf_groups', mftutor.settings.GF_GROUPS)
        self.rusclass_base = kwargs.pop(
            'rusclass_base', mftutor.settings.RUSCLASS_BASE)
        super(TutorForwarder, self).__init__(*args, **kwargs)

        self.exceptions = set()

    def handle_envelope(self, envelope, peer):
        try:
            result = super(TutorForwarder, self).handle_envelope(envelope, peer)
            django.db.connection.close()
            return result
        except ForwardToAdmin as e:
            self.forward_to_admin(envelope, e.args[0])

    def get_envelope_mailfrom(self, envelope):
        return 'webfar@matfystutor.dk'

    def translate_recipient(self, rcptto):
        name, domain = rcptto.split('@')
        if name == 'alle':
            raise ForwardToAdmin('Mail til alle')
        if name == 'wiki':
            raise InvalidRecipient(name)
        groups = self.get_groups(name)
        if groups:
            emails = self.get_group_emails(name, groups)
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
            group_emails = [tutor.profile.email for tutor in group_tutors]
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
            tutor.profile.email
            for tutor in Tutor.objects.filter(rusclass__in=rusclasses)
        ]
        if tutors_only:
            rus_emails = []
        else:
            rus_emails = [
                rus.profile.email
                for rus in Rus.objects.filter(rusclass__in=rusclasses)
            ]

        emails = tutor_emails + rus_emails

        return sorted(set(email for email in emails if email))

    def startup_log(self):
        logging.info(
            'TutorForwarder listening on %s:%s, relaying to port %s, %s'
            % (self.host, self.port, self.relay_port, self.year_log))

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

        logging.info("Subject: %r From: %s To: %s" %
                     (str(message.subject), sender, recipients))

    def log_delivery(self, message, recipients, sender):
        recipients_string = emailtunnel.abbreviate_recipient_list(recipients)
        logging.info('Subject: %r To: %s'
                     % (str(message.subject), recipients_string))

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
            fp.write(envelope.message.as_binary())

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
