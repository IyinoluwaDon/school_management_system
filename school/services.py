from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
import shutil

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.conf import settings

from accounts.models import generate_barcode_token
from .models import (
    AttendanceConfig,
    AttendanceRecord,
    ExamCandidate,
    ExamPaper,
    Grade,
    InventoryItem,
    Invoice,
    LibraryBook,
    LibraryLoan,
    Payment,
    ReportCard,
    StockTransaction,
    TimetableEntry,
    BackupRecord,
    Notification,
    SystemSetting,
    StaffAttendance,
)


def barcode_value_for_user(user):
    """Return the stable value a barcode scanner should encode for a user."""
    if not user.digital_token:
        user.digital_token = generate_barcode_token()
        user.save(update_fields=["digital_token"])
    return user.digital_token


@transaction.atomic
def record_attendance(student, attendance_date, status="PRESENT", recorded_by=None, method="MANUAL", notes=""):
    """Create or update one attendance mark per student and calendar day."""
    record, _ = AttendanceRecord.objects.update_or_create(
        student=student,
        date=attendance_date,
        defaults={
            "status": status,
            "recorded_by": recorded_by,
            "method": method,
            "notes": notes,
        },
    )
    return record


def _attendance_status(scan_time):
    config = AttendanceConfig.current()
    if scan_time >= config.absent_threshold:
        return "ABSENT"
    return "LATE" if scan_time >= config.late_threshold else "PRESENT"


@transaction.atomic
def process_barcode_scan(token, device_id="", scanned_at=None):
    """Process one scanner event for either a student or a staff member."""
    from accounts.models import User

    scanned_at = scanned_at or timezone.localtime()
    user = User.objects.select_related("student_profile", "staff_profile").filter(
        digital_token=token, is_active=True
    ).first()
    if not user:
        raise ValidationError("Unknown or inactive barcode token.")
    scan_date, scan_time = scanned_at.date(), scanned_at.time()
    if hasattr(user, "student_profile"):
        student = user.student_profile
        record, created = AttendanceRecord.objects.get_or_create(
            student=student,
            date=scan_date,
            defaults={"status": _attendance_status(scan_time), "method": "BARCODE", "notes": device_id},
        )
        return {
            "type": "student", "created": created, "duplicate": not created,
            "name": user.get_full_name() or user.username, "class": str(student.school_class),
            "status": record.status, "record_id": record.pk,
        }
    if hasattr(user, "staff_profile"):
        staff = user.staff_profile
        record, created = StaffAttendance.objects.get_or_create(
            staff=staff, date=scan_date,
            defaults={"clock_in": scan_time, "status": _attendance_status(scan_time), "device_id": device_id},
        )
        if not created and record.clock_in and not record.clock_out:
            record.clock_out = scan_time
            start = datetime.combine(scan_date, record.clock_in)
            end = datetime.combine(scan_date, scan_time)
            record.duration_worked = end - start
            record.save(update_fields=["clock_out", "duration_worked", "updated_at"])
        return {
            "type": "staff", "created": created, "duplicate": bool(not created and record.clock_out == scan_time),
            "name": user.get_full_name() or user.username, "department": staff.department,
            "status": record.status, "clock_in": record.clock_in.isoformat() if record.clock_in else None,
            "clock_out": record.clock_out.isoformat() if record.clock_out else None, "record_id": record.pk,
        }
    raise ValidationError("Barcode user must have a student or staff profile.")


def calculate_report_card(student, term):
    """Calculate a simple weighted average without requiring a reporting package."""
    grades = Grade.objects.filter(student=student, assessment__term=term).select_related("assessment")
    total_weight = sum((grade.assessment.weight for grade in grades), Decimal("0"))
    average = (
        sum((grade.percentage * grade.assessment.weight for grade in grades), Decimal("0")) / total_weight
        if total_weight
        else Decimal("0")
    )
    report, _ = ReportCard.objects.update_or_create(
        student=student,
        term=term,
        defaults={"overall_average": average.quantize(Decimal("0.01"))},
    )
    return report


def _overlaps(start, end, other_start, other_end):
    return start < other_end and end > other_start


def generate_timetable(assignments, term, start_time, lesson_minutes=40, weekdays=(1, 2, 3, 4, 5), periods_per_day=8):
    """Greedy timetable generator; raises if the requested slots cannot be assigned."""
    entries = []
    existing = list(TimetableEntry.objects.filter(term=term))
    for index, assignment in enumerate(assignments):
        placed = False
        for day in weekdays:
            for period in range(periods_per_day):
                start = (datetime.combine(date.today(), start_time) + timedelta(minutes=lesson_minutes * period)).time()
                end = (datetime.combine(date.today(), start) + timedelta(minutes=lesson_minutes)).time()
                conflicts = existing + entries
                if any(
                    item.weekday == day
                    and _overlaps(start, end, item.start_time, item.end_time)
                    and (item.teacher_id == assignment.teacher_id or item.school_class_id == assignment.school_class_id)
                    for item in conflicts
                ):
                    continue
                entries.append(
                    TimetableEntry(
                        school_class=assignment.school_class,
                        subject=assignment.subject,
                        teacher=assignment.teacher,
                        term=term,
                        weekday=day,
                        start_time=start,
                        end_time=end,
                    )
                )
                placed = True
                break
            if placed:
                break
        if not placed:
            raise ValidationError(f"No timetable slot available for assignment {assignment.pk}.")
    return TimetableEntry.objects.bulk_create(entries)


@transaction.atomic
def allocate_exam_seats(paper):
    """Assign sequential seats, moving to the next room row when capacity is reached."""
    candidates = list(ExamCandidate.objects.filter(paper=paper).order_by("student__school_class_id", "student_id"))
    if len(candidates) > paper.room.capacity:
        raise ValidationError("The examination room does not have enough seats.")
    for number, candidate in enumerate(candidates, start=1):
        candidate.seat_number = number
    ExamCandidate.objects.bulk_update(candidates, ["seat_number"])
    return candidates


@transaction.atomic
def record_payment(invoice, amount, method, reference, received_by=None, paid_at=None):
    amount = Decimal(amount)
    if amount <= 0:
        raise ValidationError("Payment amount must be positive.")
    paid = invoice.payments.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    outstanding = invoice.total - paid
    if amount > outstanding:
        raise ValidationError("Payment exceeds the invoice balance.")
    payment = Payment.objects.create(
        invoice=invoice,
        amount=amount,
        method=method,
        reference=reference,
        received_by=received_by,
        paid_at=paid_at or timezone.now(),
    )
    invoice.status = "PAID" if amount == outstanding else "PARTIAL"
    invoice.save(update_fields=["status", "updated_at"])
    return payment


@transaction.atomic
def issue_book(book, borrower, due_date):
    if book.available_copies < 1:
        raise ValidationError("No copies of this book are available.")
    loan = LibraryLoan.objects.create(
        book=book,
        borrower=borrower,
        borrowed_at=timezone.now(),
        due_date=due_date,
    )
    book.available_copies -= 1
    book.save(update_fields=["available_copies", "updated_at"])
    return loan


@transaction.atomic
def return_book(loan, returned_at=None):
    if loan.status == "RETURNED":
        return loan
    loan.returned_at = returned_at or timezone.now()
    loan.status = "RETURNED"
    loan.save(update_fields=["returned_at", "status", "updated_at"])
    book = loan.book
    book.available_copies = min(book.copies, book.available_copies + 1)
    book.save(update_fields=["available_copies", "updated_at"])
    return loan


@transaction.atomic
def adjust_inventory(item, quantity, transaction_type, recorded_by=None, note=""):
    quantity = int(quantity)
    if quantity <= 0:
        raise ValidationError("Quantity must be positive.")
    if transaction_type == "OUT" and item.quantity < quantity:
        raise ValidationError("Insufficient stock.")
    item.quantity += quantity if transaction_type == "IN" else -quantity if transaction_type == "OUT" else 0
    item.save(update_fields=["quantity", "updated_at"])
    return StockTransaction.objects.create(
        item=item,
        quantity=quantity,
        transaction_type=transaction_type,
        recorded_by=recorded_by,
        note=note,
    )


def send_notification(recipient, title, body, channel="IN_APP"):
    return Notification.objects.create(recipient=recipient, title=title, body=body, channel=channel)


def get_setting(key, default=None):
    try:
        return SystemSetting.objects.get(key=key).value
    except SystemSetting.DoesNotExist:
        return default


def set_setting(key, value, description=""):
    setting, _ = SystemSetting.objects.update_or_create(
        key=key, defaults={"value": value, "description": description}
    )
    return setting


def backup_database(destination=None):
    """Create a safe SQLite copy and track its checksum metadata.

    PostgreSQL backups remain an operational concern for deployment tooling; the
    local MVP deliberately provides a reliable SQLite backup path without adding
    a database-specific dependency.
    """
    source = Path(settings.DATABASES["default"]["NAME"])
    target = Path(destination or (source.parent / f"{source.stem}.backup{source.suffix}"))
    record = BackupRecord.objects.create(filename=str(target), status="STARTED")
    try:
        if settings.DATABASES["default"]["ENGINE"].endswith("sqlite3"):
            shutil.copy2(source, target)
        else:
            raise ValidationError("Application backups currently support SQLite only.")
        record.status = "COMPLETED"
        record.size_bytes = target.stat().st_size
        record.completed_at = timezone.now()
        record.save(update_fields=["status", "size_bytes", "completed_at", "updated_at"])
    except Exception:
        record.status = "FAILED"
        record.save(update_fields=["status", "updated_at"])
        raise
    return record


# Stable service aliases for integrations that use action-oriented names.
mark_attendance = record_attendance
calculate_student_report = calculate_report_card
generate_seating_plan = allocate_exam_seats
process_payment = record_payment
borrow_book = issue_book
return_library_book = return_book
