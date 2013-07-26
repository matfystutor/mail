# This file contains python variables that configure Lamson for email processing.
import logging
import os
import sys

domain = 'matfystutor.dk'

relay_config = {'host': 'localhost', 'port': 25}

receiver_config = {'host': 'localhost', 'port': 9001}

handlers = ['app.handlers.tutor']

router_defaults = {'host': 'matfystutor\\.dk'}

template_config = {'dir': 'app', 'module': 'templates'}

# Emails generated by lamson (e.g. delivery failures) use this From-address.
default_from = 'noreply@matfystutor.dk'

# Group that should receive administrative notices (e.g. delivery failures).
admin_group = 'webfar'

# Used if the admin group could not be resolved in the database.
fallback_admin = ('mathiasrav@gmail.com',)

# http://lamsonproject.org/docs/hooking_into_django.html
os.environ['DJANGO_SETTINGS_MODULE'] = 'mftutor.settings'

# http://stackoverflow.com/questions/11106326/hooking-up-lamson-with-django-1-4
sys.path.append('/home/mftutor/web/web')

# the config/boot.py will turn these values into variables set in settings