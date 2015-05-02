import os
import email

from io import BytesIO, StringIO
from email.generator import Generator

import emailtunnel


def main():
    for filename in sorted(os.listdir('insane')):
        if filename.endswith('.in'):
            with open('insane/%s' % filename, 'rb') as fp:
                a = fp.read()
            if a.startswith(b'From nobody'):
                nl = a.index(b'\n')
                a = a[nl+1:]
                strip_from = True
            else:
                strip_from = False
            message = email.message_from_string(a)

            fp = BytesIO()
            g = Generator(fp,
                          mangle_from_=False,
                          maxheaderlen=0)
            g.flatten(message, unixfrom=False)
            b = fp.getvalue()

            a = a.rstrip(b'\n')
            b = b.rstrip(b'\n')

            a_s = emailtunnel.Message.sanity_strip(a)
            b_s = emailtunnel.Message.sanity_strip(b)

            after_stripping = ' after stripping From' if strip_from else ''
            if a == b:
                print("%s: OK -- identical%s" % (filename, after_stripping))
            elif a_s == b_s:
                print("%s: OK%s" % (filename, after_stripping))
            elif len(a_s) != len(b_s):
                print("%s: Different # lines" % (filename,))
                o = next((i, al, bl) for i, (al, bl) in enumerate(zip(a_s, b_s)) if al != bl)
                print(o)
            else:
                print("%s: Not OK" % (filename,))


if __name__ == "__main__":
    main()
