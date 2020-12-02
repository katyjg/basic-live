from django.core.management.base import BaseCommand
from django.core import mail
from django.utils import timezone
from datetime import timedelta
from django.conf import settings

from basiclive.core.schedule.models import EmailNotification


class Command(BaseCommand):
    help = 'Notifies users of upcoming beamtime'

    def handle(self, *args, **options):
        self.from_email = getattr(settings, 'FROM_EMAIL', "sender@no-reply.ca")
        now = timezone.now() - timedelta(hours=1)

        for notification in EmailNotification.objects.filter(sent=False, beamtime__cancelled=False).filter(send_time__range=[now, now + timedelta(hours=2)]):
            self.save(notification)

    def get_message_dict(self, notification):

        message_dict = {
            'from_email': self.from_email,
            'to': notification.recipient_list(),
            'cc': not settings.DEBUG and [self.from_email] or [],
            'subject': notification.email_subject,
            'body': notification.email_body,
        }
        return message_dict
    
    def save(self, notification=None, fail_silently=False):
        """
        Build and send the email message.
        
        """
        message_dict = self.get_message_dict(notification)
        email = mail.EmailMessage(**message_dict)
        email.send(fail_silently=fail_silently)

        notification.sent = True
        notification.save()
