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

`TutorForwarder listening on 0.0.0.0:9001, relaying to mailhole.
Year from mftutor.settings: (2018, 2017, 2017)`

Tuplen `(2018, 2017, 2017)` betyder at GF-året er sat til 2018;
tutoråret til 2017; og rusåret til 2017.
Det betyder at
* emails til GF-bestemte grupper (best, koor, webfar, og andre) skal sendes til 2018-grupper;
* emails til 1. stormøde-bestemte grupper (dvs. de fleste) skal sendes til 2017-grupper;
* emails til rushold og holdtutorer skal sendes til 2017-lister.

Det betyder desuden at når man
**ændrer på GF-året/tutoråret/rusåret, skal mailserveren genstartes**.

Emails bliver videresendt til mailhole på https://mail.tket.dk
hvorfra de bliver videresendt til tutorer og russer.
Her skal `MAILHOLE_KEY` ovenfor
sættes til en nøgle der også er konfigureret i mailhole.

Emaillister hentes direkte fra Django-databasen
ved at importere `mftutor.tutor.models`
og lave Django queryset-opslag.

Den overordnede metode er `translate_recipient()`
i `TutorForwarder` i `tutormail/server.py`.
Her implementeres logikken der følger gruppealiaser,
finder passende grupper i passende årgange,
og finder tutorers emailadresser.
Desuden er der logik til at finde rushold/holdtutorers emailadresser.


## Delivery status notifications

Når en DSN (delivery status notification) sendes retur til webfar@matfystutor.dk
bliver den fanget i `error`-mappen af mailserveren.
Det sker via `TutorForwarder.reject()` metoden.
