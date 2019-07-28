#!/usr/bin/env python3

from flask import current_app, g
from flask_sendgrid import SendGrid

def get_mail_context():
    if "main" not in g:
        mail = SendGrid(current_app)
        g.mail = mail
    return g.mail

def send_mail(subject, html, sender, recipient):
    mail = get_mail_context()
    r = mail.send_email(from_email=sender,
                        to_email=recipient,
                        subject=subject,
                        html=html)
    if r.status_code != 202:
        current_app.logger.error("Unexpected email response: {0}"
                                 .format(r.status_code))
    return r
