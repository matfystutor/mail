import os
import sys
import json
import time
import logging
import argparse
import textwrap
import smtplib

from emailtunnel import Message
import tkmail.address


MAX_SIZE = 10
MAX_DAYS = 2


def configure_logging(use_tty):
    root = logging.getLogger()
    if use_tty:
        handler = logging.StreamHandler(None)
    else:
        handler = logging.FileHandler('monitor.log', 'a')
    fmt = '[%(asctime)s %(levelname)s] %(message)s'
    datefmt = None
    formatter = logging.Formatter(fmt, datefmt, '%')
    handler.setFormatter(formatter)
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)


def get_report(basename):
    with open('error/%s.json' % basename) as fp:
        metadata = json.load(fp)

    mtime = os.stat('error/%s.txt' % basename).st_mtime

    report = dict(metadata)
    report['mtime'] = int(mtime)
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
    parser = argparse.ArgumentParser()
    parser.add_argument('-n', '--dry-run', action='store_true')
    args = parser.parse_args()

    configure_logging(args.dry_run)

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
            exc_value = sys.exc_info()[1]
            logging.exception('get_report failed')
            report = {
                'subject': '<get_report(%r) failed: %s>'
                           % (basename, exc_value),
                'basename': basename,
            }
        else:
            oldest = min(oldest, report['mtime'])

        reports.append(report)

    age = now - oldest

    logging.info('%s report(s) / age %s (limit is %s / %s)' %
                 (len(reports), age, MAX_SIZE, MAX_DAYS * 24 * 60 * 60))

    if (not args.dry_run and (len(reports) <= MAX_SIZE and
                              age <= MAX_DAYS * 24 * 60 * 60)):
        return

    admins = tkmail.address.get_admin_emails()

    # admins = ['mathiasrav@gmail.com']

    keys = 'mailfrom rcpttos subject date summary mtime basename'.split()

    lists = {
        key: ''.join(
            '%s. %s\n' % (i + 1, report.get(key))
            for i, report in sorted(
                enumerate(reports),
                key=lambda x: x[1].get(key)
            ))
        for key in keys
    }

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

    Local reference in errorarchive folder:
    {lists[basename]}
    """).format(lists=lists)

    sender = recipient = 'admin@TAAGEKAMMERET.dk'
    message = Message.compose(
        sender, recipient, '[TK-admin] Failed email delivery', body)

    if args.dry_run:
        print(str(message))
        return

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

    # If no exception was raised, the following code is run
    for report in reports:
        archive_report(report['basename'])


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info('monitor exited via KeyboardInterrupt')
        raise
    except SystemExit:
        raise
    except:
        logging.exception('monitor exited via exception')
        raise
