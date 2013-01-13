import logging
from lamson.routing import route, route_like, stateless
from config.settings import relay
from config import settings
from lamson import view, mail
from ..webapp.tutor.models import TutorGroup

@route("(address)@(host)", address=".+")
@stateless
def RELAY(message, **kwargs):
    logging.debug("Got a message for "+kwargs['address']+", To: "+message['to'])
    if relay_tutorgroup(message, **kwargs):
        return RELAY

    relay_unknown(message, **kwargs)
    return RELAY

def tutor_group_mails(tutorgroupname):
    """Given a group name, return email addresses of all people in the
    group."""
    tutorgroup = TutorGroup.objects.get(handle=tutorgroupname)
    recipients = tutorgroup.tutor_set.all()
    return [t.profile.user.email for t in recipients]

def relay_tutorgroup(message, address, host):
    """Try to relay the message to the given group."""
    try:
        emails = tutor_group_mails(address)
    except TutorGroup.DoesNotExist:
        return False
    relay.deliver(message, To=emails)
    return True

def relay_unknown(message, address, host):
    """Let the admin know that the message could not be delivered."""
    try:
        emails = tutor_group_mails(settings.admin_group)
    except TutorGroup.DoesNotExist:
        emails = settings.fallback_admin
    body = 'Failed to deliver the following message.\n\n'
    for k in message.keys():
        body += k+': '+message[k]+'\n'
    body += '\n'+message.body()
    resp = mail.MailResponse(
            To=None,
            From=settings.default_from,
            Subject='[lamson unknown dest] '+message['subject'],
            Body=body)
    resp.attach_all_parts(message)
    relay.deliver(resp, To=emails)
    return True

