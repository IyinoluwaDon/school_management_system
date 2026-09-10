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
