import logging
from lamson.routing import route, route_like, stateless
from config.settings import relay
from config import settings
from lamson import view, mail

from mftutor.tutor.models import TutorProfile, TutorGroup, RusClass
from mftutor.aliases.models import *
from mftutor.settings import YEAR, RUSCLASS_BASE, TUTORS_PREFIX

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
    groups = resolve_alias(tutorgroupname)
    logging.debug("Resolved group "+tutorgroupname+" to: "+str(tuple(groups)))
    recipients = TutorProfile.objects.filter(
            tutor__year__exact = YEAR,
            tutor__groups__in=tuple(groups))
    emails = [t.email for t in recipients]
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
    handle_base = {handle: []
            for official, handle, internal in RUSCLASS_BASE}
    handles = {}
    for rusclass in RusClass.objects.filter(year__exact=YEAR):
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

    if address in handles:
        russes = [tp.email for tp in TutorProfile.objects.filter(
                rus__year__exact=YEAR,
                rus__rusclass__handle__exact=address)]
        tutors = [tp.email for tp in TutorProfile.objects.filter(
                tutor__year__exact=YEAR,
                tutor__rusclass__handle__exact=address)]
    elif address in handle_base:
        russes = [tp.email for tp in TutorProfile.objects.filter(
                rus__year__exact=YEAR,
                rus__rusclass__in=handle_base[address])]
        tutors = [tp.email for tp in TutorProfile.objects.filter(
                tutor__year__exact=YEAR,
                tutor__rusclass__in=handle_base[address])]
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

