import subprocess
import smtplib
import socket
from email.mime.text import MIMEText
import datetime
from pytz import timezone
localtz = timezone('Asia/Singapore')


class GmailAlertServer(object):
    def __init__(self, app=None):
        self._server = None
        if app:
            self.init_app(app)

    def init_app(self, app):
        self.app = app
        self.app.extensions['gmail_alert_server'] = self

    def send(self, subject, content):
        to = self.app.config['GMAIL_ALERT_TO']
        gmail_user = self.app.config['GMAIL_ALERT_USER']
        gmail_password = self.app.config['GMAIL_ALERT_PASSWORD']
        smtpserver = smtplib.SMTP('smtp.gmail.com', 587)
        smtpserver.ehlo()
        smtpserver.starttls()
        smtpserver.ehlo
        smtpserver.login(gmail_user, gmail_password)
        msg = MIMEText(content, 'html')
        msg['Subject'] = subject
        msg['From'] = gmail_user
        msg['To'] = to
        smtpserver.sendmail(gmail_user, [to], msg.as_string())
        smtpserver.quit()

    @property
    def today(self):
        return datetime.datetime.now(localtz)
