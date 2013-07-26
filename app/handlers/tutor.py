import logging
from lamson.routing import route, route_like, stateless
from config.settings import relay
from config import settings
from lamson import view, mail

from django.contrib.auth.models import User
from mftutor.tutor.models import TutorGroup
from mftutor.aliases.models import *
from mftutor.activation.models import ProfileActivation
from mftutor.settings import YEAR

@route("(address)@(host)", address=".+")
@stateless
def RELAY(message, **kwargs):
    logging.debug(u"Got a message for "+kwargs['address'].decode('utf-8')+u", To: "+unicode(message['to']))
    if relay_tutorgroup(message, **kwargs):
        return RELAY

    relay_unknown(message, **kwargs)
    return RELAY

def tutor_group_mails(tutorgroupname):
    """Given a group name, return email addresses of all people in the
    group."""
    groups = resolve_alias(tutorgroupname)
    logging.debug("Resolved group "+tutorgroupname+" to: "+str(tuple(groups)))
    recipients = User.objects.filter(
            tutorprofile__tutor__year__exact = YEAR,
            tutorprofile__tutor__groups__in=tuple(groups))
    nonactivated_recipients = ProfileActivation.objects.filter(
            profile__tutor__year__exact=YEAR,
            profile__tutor__groups__in=tuple(groups),
            profile__user=None)
    emails = [t.email for t in recipients] + [pa.email for pa in nonactivated_recipients]
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

