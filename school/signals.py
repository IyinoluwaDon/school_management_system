import logging
import os

from django.db import transaction


from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import (
    Announcement, Assessment, AttendanceRecord, DisciplinaryIncident, Enrollment, Grade,
    Invoice, LeaveRequest, LibraryLoan, MedicalRecord, Payment, ReportCard,
    StockTransaction, TimetableEntry,
)

AUDITED_MODELS = (
    Announcement, Assessment, AttendanceRecord, DisciplinaryIncident, Enrollment, Grade,
    Invoice, LeaveRequest, LibraryLoan, MedicalRecord, Payment, ReportCard,
    StockTransaction, TimetableEntry,
)


@receiver(post_save)
def audit_save(sender, instance, created, **kwargs):
    if sender not in AUDITED_MODELS:
        return
    # Import lazily so the AuditLog model is fully registered during app startup.
    from .models import AuditLog

    AuditLog.objects.create(
        action="CREATE" if created else "UPDATE",
        model_name=sender.__name__,
        object_id=str(instance.pk),
        details={"source": "model_signal"},
    )


@receiver(post_delete)
def audit_delete(sender, instance, **kwargs):
    if sender not in AUDITED_MODELS:
        return
    from .models import AuditLog

    AuditLog.objects.create(
        action="DELETE",
        model_name=sender.__name__,
        object_id=str(instance.pk),
        details={"source": "model_signal"},
    )


# --------------------------------------------------------------------------
# Notify guardians when a student is marked ABSENT.
# Reads Twilio/SendGrid config straight from the environment - nothing to
# add to settings.py. Both channels are attempted independently; either,
# both, or neither may be configured and it degrades gracefully.
# --------------------------------------------------------------------------

logger = logging.getLogger(__name__)


def _send_absence_sms(phone_number, message):
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_number = os.environ.get("TWILIO_FROM_NUMBER")
    if not (account_sid and auth_token and from_number and phone_number):
        return False
    try:
        from twilio.rest import Client

        Client(account_sid, auth_token).messages.create(body=message, from_=from_number, to=phone_number)
        return True
    except Exception:
        logger.exception("Twilio SMS failed for %s", phone_number)
        return False


def _send_absence_email(to_email, subject, message):
    api_key = os.environ.get("SENDGRID_API_KEY")
    from_email = os.environ.get("SENDGRID_FROM_EMAIL")
    if not (api_key and from_email and to_email):
        return False
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail

        mail = Mail(from_email=from_email, to_emails=to_email, subject=subject, plain_text_content=message)
        SendGridAPIClient(api_key).send(mail)
        return True
    except Exception:
        logger.exception("SendGrid email failed for %s", to_email)
        return False


def _dispatch_absence_alert(record_id):
    from .models import AttendanceRecord, Notification

    try:
        record = AttendanceRecord.objects.select_related("student__user").get(pk=record_id)
    except AttendanceRecord.DoesNotExist:
        return
    if record.status != "ABSENT":
        return  # could have been corrected before the transaction committed

    student = record.student
    student_name = student.user.get_full_name() or student.user.username
    message = f"{student_name} ({student.admission_number}) was marked ABSENT on {record.date.isoformat()}."

    # Idempotent: the message is fully determined by (student, date), so if
    # it's already been logged, this exact absence has already been alerted -
    # safe against the record being re-saved (e.g. a note added later).
    if Notification.objects.filter(recipient=student.user, body=message).exists():
        return

    sent_sms = _send_absence_sms(student.guardian_phone, message) if student.guardian_phone else False

    primary_link = (
        student.parent_relationships.filter(is_primary=True).select_related("parent__user").first()
        or student.parent_relationships.select_related("parent__user").first()
    )
    parent_email = primary_link.parent.user.email if primary_link and primary_link.parent.user.email else None
    sent_email = _send_absence_email(parent_email, "Absence alert", message) if parent_email else False

    if sent_sms or sent_email:
        Notification.objects.create(
            recipient=student.user,
            title="Absence alert sent",
            body=message,
            channel="SMS" if sent_sms else "EMAIL",
        )


@receiver(post_save, sender=AttendanceRecord)
def notify_guardians_on_absence(sender, instance, created, **kwargs):
    if instance.status != "ABSENT":
        return

    # Only fire once the DB transaction actually commits, so a record that
    # gets rolled back never triggers a real text/email. The idempotency
    # check itself lives in _dispatch_absence_alert (see there for why).
    transaction.on_commit(lambda: _dispatch_absence_alert(instance.pk))