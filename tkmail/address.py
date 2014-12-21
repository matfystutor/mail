import re
import logging

from emailtunnel import InvalidRecipient
from tkmail.database import Database


def translate_recipient(year, name):
    # if name.upper() in ('GFORM', 'FORM13', 'FORM2013', 'FORM1314'):
    #     return ['mathiasrav@gmail.com']
    # else:
    #     raise InvalidRecipient(name)

    db = Database()
    recipient_ids = parse_recipient(name, db, year)
    email_addresses = db.get_email_addresses(recipient_ids)
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
        if sign == '+': # union
            recipient_ids = recipient_ids.union(personIds)
        else: # minus
            recipient_ids = recipient_ids.difference(personIds)

    # logging.debug("TKMail.py: size of recipient_ids: %d" % len(recipient_ids))

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
            if relativ == 1: ##Relativ = true
                regexp = (r'^%s(?P<name>%s)%s$'
                        % (anciprefix, groupRegexp, ancipostfix))
            else:
                regexp = '^(?P<name>%s)$' % groupRegexp
            result = re.match(regexp, alias, re.I)
            if result:
                matches.append((groupId, groupType, result))

        if not matches:
            raise InvalidRecipient(alias)

        if len(matches) > 1:
            raise ValueError("The alias %r matches more than one group"
                             % alias)

        groupId, groupType, result = matches[0]

        if groupType == 0:##Group, without aging
            logging.debug("TKMail.py: " + str(result.group("name")))
            personIds = db.get_group_members(groupId)
        elif groupType == 1:##Group with aging
            logging.debug("TKMail.py: %s pre: %s post: %s"
                    % (result.group('name'), result.group('pre'),
                        result.group('post')))
            grad = getGrad(result.group("pre"),
                    result.group("post"),
                    currentYear)
            personIds = db.get_grad_group_members(groupId, grad)
        elif groupType == 2:##Titel, with/without aging
            logging.debug("TKMail.py: %s pre: %s post: %s"
                    % (result.group('name'), result.group('pre'),
                        result.group('post')))
            grad = getGrad(result.group("pre"),
                    result.group("post"),
                    currentYear)
            personIds = db.get_user_by_title(result.group('name'), grad)
        elif groupType == 3:##Direct user
            logging.debug("TKMail.py: " + result.group("name"))
            personIds = db.get_user_by_id(result.group('name')[6:])
        elif groupType == 4:##BESTFU hack
            logging.debug("TKMail.py: " + result.group("name"))
            grad = getGrad(result.group("pre"),
                    result.group("post"),
                    currentYear)
            personIds = (db.get_grad_group_members(groupId + 1, grad)
                    + db.get_grad_group_members(groupId - 1, grad))
        else:
            raise Exception(
                "Error in table gruppe, type: %s is unknown."
                % groupType)


        if not personIds:
            ##No users in the database fit the current alias
            raise InvalidRecipient(alias)

        return personIds

    except DatabaseError as e:
        logging.error("TKMail.py:Evalalias(): %s" % e.msg)
        raise


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
            if (first + 1) % 100 != second:
                #There should be exactly one year between the two numbers
                raise InvalidRecipient(postFix)
        year = int(postFix[0:2])
        if year > 56: ##19??
            grad = currentYear - (1900 + year)
        else: ##20??
            grad = currentYear - (2000 + year)

    ##Now evaluate the prefix:
    regexpRaised = re.compile(r"([KGBOT])([0-9]+)")
    i = 0
    while i < len(preFix):
        resul = regexpRaised.match(preFix[i:])
        if resul:
            grad += prefixValues[resul.group(1)] * int(resul.group(2))
            i += len(resul.group())
        else:
            grad += prefixValues[preFix[i]]
            i += 1
    return grad
