import re

from emailtunnel import InvalidRecipient
from tkmail.database import Database
from tkmail.config import ADMINS


def get_admin_emails():
    """Resolve the group "admin" or fallback if the database is unavailable.

    The default set of admins is set in the tkmail.database module.
    """

    email_addresses = []
    try:
        db = Database()
        email_addresses = [
            addy.replace('&#064;', '@')
            for addy in db.get_admin_emails()
        ]
    except:
        pass

    if not email_addresses:
        email_addresses = list(ADMINS)

    return email_addresses


def translate_recipient(year, name):
    """Translate recipient `name` in GF year `year`.

    >>> translate_recipient(2010, "K3FORM")
    ["mathiasrav@gmail.com"]

    >>> translate_recipient(2010, "GFORM14")
    ["mathiasrav@gmail.com"]

    >>> translate_recipient(2010, "BEST2013")
    ["mathiasrav@gmail.com", ...]
    """

    db = Database()
    recipient_ids = parse_recipient(name.upper(), db, year)
    email_addresses = [
        addy.replace('&#064;', '@').strip()
        for addy in db.get_email_addresses(recipient_ids)
    ]
    return email_addresses


prefixValues = {
    'K': -1,
    'G': 1,
    'B': 2,
    'O': 3,
    'T': 1
}


def parse_recipient(recipient, db, currentYear):
    """
    Evaluate each address which is divided by + and -.
    Collects the resulting sets of not matched and the set of spam addresses.
    And return the set of person indexes that are to receive the email.
    """

    personIdOps = []
    invalid_recipients = []
    for sign, name in re.findall(r'([+-]?)([^+-]+)', recipient):
        try:
            personIds = parse_alias(name, db, currentYear)
            personIdOps.append((sign or '+', personIds))
        except InvalidRecipient as e:
            invalid_recipients.append(e.args[0])

    if invalid_recipients:
        raise InvalidRecipient(invalid_recipients)

    recipient_ids = set()
    for sign, personIds in personIdOps:
        if sign == '+':  # union
            recipient_ids = recipient_ids.union(personIds)
        else:  # minus
            recipient_ids = recipient_ids.difference(personIds)

    return recipient_ids


def parse_alias(alias, db, currentYear):
    """
    Evaluates the alias, returning a non-empty list of person IDs.
    Raise exception if a spam or no match email.
    """

    anciprefix = r"(?P<pre>(?:[KGBOT][KGBOT0-9]*)?)"
    ancipostfix = r"(?P<post>(?:[0-9]{2}|[0-9]{4})?)"
    try:
        groups = db.get_groups()
        matches = []
        for row in groups:
            groupId, groupRegexp, relativ, groupType = row
            groupId = int(groupId)
            if relativ == 1:  # Relativ = true
                regexp = (r'^%s(?P<name>%s)%s$'
                          % (anciprefix, groupRegexp, ancipostfix))
            else:
                regexp = '^(?P<name>%s)$' % groupRegexp
            result = re.match(regexp, alias)
            if result:
                matches.append((groupId, groupType, result))

        if not matches:
            raise InvalidRecipient(alias)

        if len(matches) > 1:
            raise ValueError("The alias %r matches more than one group"
                             % alias)

        groupId, groupType, result = matches[0]

        if groupType == 0:  # Group, without aging
            personIds = db.get_group_members(groupId)
        elif groupType == 1:  # Group with aging
            grad = getGrad(
                result.group("pre"),
                result.group("post"),
                currentYear)
            personIds = db.get_grad_group_members(groupId, grad)
        elif groupType == 2:  # Titel, with/without aging
            grad = getGrad(
                result.group("pre"),
                result.group("post"),
                currentYear)
            personIds = db.get_user_by_title(result.group('name'), grad)
        elif groupType == 3:  # Direct user
            personIds = db.get_user_by_id(result.group('name')[6:])
        elif groupType == 4:  # BESTFU hack
            grad = getGrad(
                result.group("pre"),
                result.group("post"),
                currentYear)
            personIds = (
                db.get_grad_group_members(groupId + 1, grad)
                + db.get_grad_group_members(groupId - 1, grad))
        else:
            raise Exception(
                "Error in table gruppe, type: %s is unknown."
                % groupType)

        if not personIds:
            # No users in the database fit the current alias
            raise InvalidRecipient(alias)

        return personIds

    finally:
        pass


def getGrad(preFix, postFix, currentYear):
    """
    CurrentYear is the year where the current BEST was elected.
    Assumes currentyear <= 2056.
    Returnes the corresponding grad of pre,post and currentYear.
    (Calculates as the person have the prefix in year postfix)
    """

    if not postFix:
        grad = 0
    else:
        if len(postFix) == 4:
            first, second = int(postFix[0:2]), int(postFix[2:4])
            # Note that postFix 1920, 2021 and 2122 are technically ambiguous,
            # but luckily there was no BEST in 1920 and this script hopefully
            # won't live until the year 2122, so they are not actually
            # ambiguous.
            if (first + 1) % 100 == second:
                # There should be exactly one year between the two numbers
                if first > 56:
                    grad = currentYear - (1900 + first)
                else:
                    grad = currentYear - (2000 + first)
            elif first in (19, 20):
                # 19xx or 20xx
                grad = currentYear - int(postFix)
            else:
                raise InvalidRecipient(postFix)
        elif len(postFix) == 2:
            year = int(postFix[0:2])
            if year > 56:  # 19??
                grad = currentYear - (1900 + year)
            else:  # 20??
                grad = currentYear - (2000 + year)
        else:
            raise InvalidRecipient(postFix)

    # Now evaluate the prefix:
    for base, exponent in re.findall(r"([KGBOT])([0-9]*)", preFix):
        exponent = int(exponent or 1)
        grad += prefixValues[base] * int(exponent)

    return grad
