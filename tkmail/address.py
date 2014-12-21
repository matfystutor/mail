from tkmail.database import Database


def translate_recipient(name):
    if name.upper() in ('GFORM', 'FORM13', 'FORM2013', 'FORM1314'):
        return ['mathiasrav@gmail.com']
    else:
        raise InvalidRecipient(name)
