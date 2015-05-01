# encoding: utf8
import os
import textwrap

from emailtunnel import SMTPForwarder, Message, InvalidRecipient

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mftutor.settings")
django.setup()

import mftutor.settings

from mftutor.aliases.models import resolve_alias
from mftutor.tutor.models import Tutor, TutorGroup, RusClass, Rus


class TutorForwarder(SMTPForwarder):
    ERROR_TEMPLATE = """
    Nedenstående email blev ikke leveret til nogen.

    {reason}

    {message}
    """

    def __init__(self, *args, **kwargs):
        self.gf_year = mftutor.settings.YEAR
        self.tutor_year = mftutor.settings.TUTORMAIL_YEAR
        self.rus_year = mftutor.settings.RUSMAIL_YEAR
        self.gf_groups = mftutor.settings.GF_GROUPS
        self.rusclass_base = mftutor.settings.RUSCLASS_BASE

    def handle_envelope(self, envelope, peer):
        try:
            return super(TutorForwarder).handle_envelope(envelope, peer)
        except ForwardToAdmin as e:
            self.forward_to_admin(envelope, e.args[0])

    def translate_recipient(self, rcptto):
        name, domain = rcptto.split('@')
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
            group = TutorGroup.objects.get(handle=group_name)
        except TutorGroup.DoesNotExist:
            return None

        # Disallow 'alle'
        if group.handle == 'alle':
            return None

        return (group, year)

    def get_group_emails(self, name, groups):
        emails = []
        for group, year in groups:
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
