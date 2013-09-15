# vim:set fileencoding=utf8:
import logging
from lamson.routing import route, route_like, stateless
from config.settings import relay
from config import settings
from lamson import view, mail

from mftutor.tutor.models import Tutor, TutorGroup, RusClass
from mftutor.aliases.models import *
from mftutor.settings import YEAR, RUSCLASS_BASE, TUTORS_PREFIX

try:
    from mftutor.settings import TUTORMAIL_YEAR, RUSMAIL_YEAR, GF_GROUPS
except ImportError:
    logging.error("Could not import TUTORMAIL_YEAR and/or RUSMAIL_YEAR and/or GF_GROUPS")
    TUTORMAIL_YEAR = RUSMAIL_YEAR = YEAR
    GF_GROUPS = ('best', 'koor')

@route("(address)@(host)", address=".+")
@stateless
def RELAY(message, **kwargs):
    logging.debug(u"Got a message for "+kwargs['address'].decode('utf-8')+u", To: "+unicode(message['to']))
    if relay_tutorgroup(message, **kwargs):
        return RELAY

    if relay_rusclass(message, **kwargs):
        return RELAY

    relay_unknown(message, **kwargs)
    return RELAY

def tutor_group_mails(tutorgroupname):
    """Given a group name, return email addresses of all people in the
    group."""

    year = TUTORMAIL_YEAR

    # In the time between a new board is elected (GF in November) and new tutor
    # groups are formed (1. stormøde in February), the 'best' alias should
    # change, but other tutor group aliases should remain the same.
    # In addition, 'gbest' should always point to 'best' one year back.
    if tutorgroupname in GF_GROUPS:
        year = YEAR
    elif tutorgroupname.startswith('g') and tutorgroupname[1:] in GF_GROUPS:
        year = YEAR - 1
        tutorgroupname = tutorgroupname[1:]

    groups = resolve_alias(tutorgroupname)
    logging.debug("Resolved group "+tutorgroupname+" to: "+str(tuple(groups)))

    recipients = Tutor.objects.filter(
            year=year, early_termination__isnull=True,
            groups__in=tuple(groups))
    emails = [t.profile.email for t in recipients]
    return emails

def relay_tutorgroup(message, address, host):
    """Try to relay the message to the given group."""
    try:
        emails = tutor_group_mails(address)
    except TutorGroup.DoesNotExist:
        return False
    logging.info("Message from "+message['from']+" to \""+address+"\" ("+str(len(emails))+" recipients): \""+message['subject']+"\"")
    if not emails:
        return False
    logging.debug("Message: "+unicode(message))
    relay.deliver(message, To=emails)
    return True

def relay_rusclass(message, address, host):
    handle_base = {}
    for official, handle, internal in RUSCLASS_BASE:
        handle_base[handle] = []
    handles = {}
    for rusclass in RusClass.objects.filter(year__exact=RUSMAIL_YEAR):
        handles[rusclass.handle] = rusclass
        for h in handle_base.keys():
            if rusclass.handle.startswith(h):
                handle_base[h].append(rusclass)

    handle = address

    if address.startswith(TUTORS_PREFIX):
        tutors_only = True
        handle = address[len(TUTORS_PREFIX):]
    else:
        tutors_only = False

    logging.debug("Address [{0}] is handle [{1}], tutors_only = {2}"
            .format(address, handle, tutors_only))

    if handle in handles:
        russes = [rus.profile.email for rus in Rus.objects.filter(
                year__exact=RUSMAIL_YEAR,
                rusclass__handle__exact=handle)]
        tutors = [tutor.profile.email for tutor in Tutor.members.filter(
                year__exact=RUSMAIL_YEAR,
                rusclass__handle__exact=handle)]
    elif handle in handle_base:
        russes = [rus.profile.email for rus in Rus.objects.filter(
                year__exact=RUSMAIL_YEAR,
                rusclass__in=handle_base[handle])]
        tutors = [tutor.profile.email for tutor in Tutor.members.filter(
                year__exact=RUSMAIL_YEAR,
                rusclass__in=handle_base[handle])]
    else:
        return False

    if tutors_only:
        russes = []

    emails = russes + tutors
    emails = [email for email in emails if '@' in email]

    logging.debug("Address [{0}] goes to {1} russes, {2} tutors, in total {3} emails"
            .format(address, len(russes), len(tutors), len(emails)))

    if not emails:
        return False

    relay.deliver(message, To=emails)
    return True


def relay_unknown(message, address, host):
    """Let the admin know that the message could not be delivered."""
    try:
        emails = tutor_group_mails(settings.admin_group)
        dest = settings.admin_group + '@' + settings.domain
    except TutorGroup.DoesNotExist:
        emails = settings.fallback_admin
        dest = settings.fallback_admin
    body = u'Failed to deliver the following message to '+unicode(address)+u'@'+unicode(host)+u'.\n\n'
    for k in message.keys():
        body += unicode(k)+u': '+unicode(message[k])+u'\n'
    body += u'\n'+unicode(message.body())
    resp = mail.MailResponse(
            To=dest,
            From=settings.default_from,
            Subject=u'[lamson unknown dest] '+unicode(message['subject']),
            Body=body)
    #resp.attach_all_parts(message)
    relay.deliver(resp, To=emails)
    return True

