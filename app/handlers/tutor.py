import logging
from lamson.routing import route, route_like, stateless
from config.settings import relay
from config import settings
from lamson import view, mail
from ..webapp.tutor.models import TutorGroup
from aliases.models import *
from django.contrib.auth.models import User
from mftutor import siteconfig

@route("(address)@(host)", address=".+")
@stateless
def RELAY(message, **kwargs):
    logging.debug(u"Got a message for "+kwargs['address'].decode('utf-8')+u", To: "+message['to'])
    if relay_tutorgroup(message, **kwargs):
        return RELAY

    relay_unknown(message, **kwargs)
    return RELAY

def resolve_alias(recipient, visited=None):
    """Given a recipient, return the transitive closure of the alias graph."""
    if visited:
        visited = frozenset([recipient]).union(visited)
    else:
        visited = frozenset([recipient])

    aliases = list(Alias.objects.filter(source=recipient))
    result = frozenset([recipient])
    for a in aliases:
        if a.destination in visited:
            logging.warning("Cycle involving "+a)
        else:
            result = result.union(resolve_alias(a.destination, visited))

    return result

#def resolve_aliases(recipients):
#    result = frozenset()
#    for rcp in recipients:
#        result = result.union(resolve_alias(result))
#    return result

def tutor_group_mails(tutorgroupname):
    """Given a group name, return email addresses of all people in the
    group."""
    groups = resolve_alias(tutorgroupname)
    logging.debug("Resolved group "+tutorgroupname+" to: "+str(tuple(groups)))
    recipients = User.objects.filter(tutorprofile__tutor__year__exact = siteconfig.year,
            tutorprofile__tutor__groups__in=tuple(groups))
    return [t.email for t in recipients]

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
        dest = settings.admin_group + '@' + settings.domain
    except TutorGroup.DoesNotExist:
        emails = settings.fallback_admin
        dest = settings.fallback_admin
    body = 'Failed to deliver the following message.\n\n'
    for k in message.keys():
        body += k+': '+message[k]+'\n'
    body += '\n'+message.body()
    resp = mail.MailResponse(
            To=dest,
            From=settings.default_from,
            Subject='[lamson unknown dest] '+message['subject'],
            Body=body)
    resp.attach_all_parts(message)
    relay.deliver(resp, To=emails)
    return True

