# Tutorgruppens mailsystem

Mailsystemet er bygget ovenpå
[emailtunnel](https://github.com/TK-IT/emailtunnel)
som i sig selv bygger ovenpå
[aiosmtpd](https://github.com/aio-libs/aiosmtpd).

Mailserveren køres således:

```
cd path/to/tutormail
. venv/bin/activate
MAILHOLE_KEY=my_mailhole_key python -m tutormail -d path/to/tutorweb
```

Når mailserveren starter op, skriver den noget à la:

```
TutorForwarder listening on 0.0.0.0:9001, relaying to port 25, Year from mftutor.settings: (2018, 2017, 2017)
```

Tuplen `(2018, 2017, 2017)` betyder at GF-året er sat til 2018;
tutoråret til 2017; og rusåret til 2017.
Det betyder med andre ord, at emails til GF-bestemte grupper
(best, koor, webfar, og andre) skal sendes til 2018-grupper;
emails til 1. stormøde-bestemte grupper (dvs. de fleste) skal sendes til
2017-grupper; emails til rushold og holdtutorer skal sendes til 2017-lister.


I `tutormail/server.py` defineres klassen `TutorForwarder`
som står for at modtage og videresende emails.
