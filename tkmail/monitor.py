import os
import sys
import json
import time
import logging
logging.basicConfig(filename='monitor.log')
import textwrap
import smtplib

from emailtunnel import Message
import tkmail.address


MAX_SIZE = 10
MAX_DAYS = 2


def get_report(basename):
    with open('error/%s.json' % basename) as fp:
        metadata = json.load(fp)

    with open('error/%s.txt' % basename) as fp:
        mtime = os.fstat(fp.fileno()).st_mtime
        body = fp.read()

    report = dict(metadata)
    report['mtime'] = mtime
    report['body'] = body
    report['basename'] = basename
    return report


def archive_report(basename):
    for ext in 'txt json mail'.split():
        filename = '%s.%s' % (basename, ext)
        try:
            os.rename('error/%s' % filename, 'errorarchive/%s' % filename)
        except:
            logging.exception('Failed to move %s' % filename)


def main():
    try:
        filenames = os.listdir('error')
    except OSError:
        filenames = []

    now = int(time.time())
    oldest = now
    reports = []

    for filename in sorted(filenames):
        if not filename.endswith('.txt'):
            continue

        basename = filename[:-4]

        try:
            report = get_report(basename)
        except:
            exc_type, exc_value, tb = sys.exc_info()
            logging.exception('get_report failed')
            report = {
                'subject': '<get_report(%r) failed: %s>' % (basename, exc_value),
                'basename': basename,
            }
        else:
            oldest = min(oldest, report['mtime'])

        reports.append(report)

    age = oldest - now

    if len(files) <= MAX_SIZE and age <= MAX_DAYS * 24 * 60 * 60:
        logging.info('Only %s young reports; exiting' % len(files))
        return

    admins = tkmail.address.get_admin_emails()

    # admins = ['mathiasrav@gmail.com']

    keys = 'mailfrom rcpttos subject date summary mtime'.split()

    lists = {
        key: ''.join(
            '%s. %s\n' % (i + 1, report.get(key))
            for i, report in enumerate(reports))
        for key in keys
    }

    messages = ''.join(
        '%s\n\n%s\n\n' % (60 * '=', report.get('body'))
        for report in reports
    )

    body = textwrap.dedent("""
    This is the mail system of TAAGEKAMMERET.

    The following emails were not delivered to anyone.

    Reasons for failed delivery:
    {lists[summary]}

    Subjects:
    {lists[subject]}

    Senders:
    {lists[mailfrom]}

    Recipients:
    {lists[rcpttos]}

    Sent:
    {lists[date]}

    Received:
    {lists[mtime]}

    {messages}
    """).format(lists=lists, messages=messages)

    sender = recipient = 'admin@TAAGEKAMMERET.dk'
    message = Message.compose(
        sender, recipient, '[TK-admin] Failed email delivery', body)

    relay_hostname = '127.0.0.1'
    relay_port = 25
    relay_host = smtplib.SMTP(relay_hostname, relay_port)
    relay_host.set_debuglevel(0)

    try:
        relay_host.sendmail(sender, admins, str(message))
    finally:
        try:
            relay_host.quit()
        except smtplib.SMTPServerDisconnected:
            pass

    for report in reports:
        archive_report(report['basename'])


if __name__ == "__main__":
    main()
