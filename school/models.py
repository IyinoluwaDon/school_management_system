from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone


class AcademicSession(models.Model):
    name = models.CharField(max_length=20, unique=True)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=False)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return self.name


class Term(models.Model):
    TERM_CHOICES = [(1, "First Term"), (2, "Second Term"), (3, "Third Term")]
    session = models.ForeignKey(AcademicSession, on_delete=models.CASCADE, related_name="terms")
    number = models.PositiveSmallIntegerField(choices=TERM_CHOICES)
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        ordering = ["session", "number"]
        constraints = [
            models.UniqueConstraint(fields=["session", "number"], name="unique_term_per_session"),
        ]

    @property
    def name(self):
        return dict(self.TERM_CHOICES)[self.number]

    def __str__(self):
        return f"{self.name} - {self.session}"


class SchoolClass(models.Model):
    name = models.CharField(max_length=50)
    arm = models.CharField(max_length=20, default="A")
    level = models.CharField(max_length=30, blank=True)

    class Meta:
        ordering = ["name", "arm"]
        constraints = [
            models.UniqueConstraint(fields=["name", "arm"], name="unique_class_arm"),
        ]

    def __str__(self):
        return f"{self.name} {self.arm}"


class Subject(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_difficult = models.BooleanField(
        default=False,
        help_text="Flag cognitively demanding subjects (e.g. Maths, Physics) so the "
        "timetable engine spreads them across different days instead of clustering them.",
    )

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class StudentProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="student_profile")
    admission_number = models.CharField(max_length=30, unique=True)
    school_class = models.ForeignKey(SchoolClass, on_delete=models.PROTECT, related_name="students")
    date_of_birth = models.DateField(null=True, blank=True)
    guardian_name = models.CharField(max_length=150, blank=True)
    guardian_phone = models.CharField(max_length=30, blank=True)

    class Meta:
        ordering = ["admission_number"]

    def __str__(self):
        return f"{self.admission_number} - {self.user.get_full_name() or self.user.username}"


class StaffProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="staff_profile")
    staff_number = models.CharField(max_length=30, unique=True)
    job_title = models.CharField(max_length=100, blank=True)
    department = models.CharField(max_length=100, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["staff_number"]

    def __str__(self):
        return f"{self.staff_number} - {self.user.get_full_name() or self.user.username}"


class TimestampedModel(models.Model):
    """Common timestamps for operational records."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AttendanceConfig(models.Model):
    opening_time = models.TimeField(default="07:00")
    late_threshold = models.TimeField(default="07:45")
    absent_threshold = models.TimeField(default="10:00")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Attendance configuration"
        verbose_name_plural = "Attendance configuration"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def current(cls):
        config, _ = cls.objects.get_or_create(pk=1)
        return config


class StaffAttendance(TimestampedModel):
    STATUS_CHOICES = [
        ("PRESENT", "Present"), ("LATE", "Late"), ("ABSENT", "Absent"), ("ON_LEAVE", "On leave")
    ]
    staff = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, related_name="attendance_records")
    date = models.DateField(default=timezone.localdate)
    clock_in = models.TimeField(null=True, blank=True)
    clock_out = models.TimeField(null=True, blank=True)
    duration_worked = models.DurationField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="PRESENT")
    device_id = models.CharField(max_length=100, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["staff", "date"], name="unique_staff_attendance_day"),
        ]


class Enrollment(TimestampedModel):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name="enrollments")
    school_class = models.ForeignKey(SchoolClass, on_delete=models.PROTECT, related_name="enrollments")
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="enrollments")
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["student", "term"], name="unique_student_term_enrollment")]

    def __str__(self):
        return f"{self.student} - {self.term}"


class AttendanceRecord(TimestampedModel):
    STATUS_CHOICES = [("PRESENT", "Present"), ("ABSENT", "Absent"), ("LATE", "Late"), ("EXCUSED", "Excused")]
    METHOD_CHOICES = [("MANUAL", "Manual"), ("BARCODE", "Barcode"), ("IMPORT", "Import")]
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name="attendance_records")
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="PRESENT")
    method = models.CharField(max_length=10, choices=METHOD_CHOICES, default="MANUAL")
    notes = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["-date", "student"]
        constraints = [models.UniqueConstraint(fields=["student", "date"], name="unique_student_attendance_day")]


class SubjectAssignment(TimestampedModel):
    teacher = models.ForeignKey(StaffProfile, on_delete=models.PROTECT, related_name="subject_assignments")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="teacher_assignments")
    school_class = models.ForeignKey(SchoolClass, on_delete=models.PROTECT, related_name="subject_assignments")
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="subject_assignments")
    periods_per_week = models.PositiveSmallIntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(20)],
        help_text="How many timetable periods this subject/class pairing needs each week.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["teacher", "subject", "school_class", "term"], name="unique_subject_assignment"
            )
        ]


class Assessment(TimestampedModel):
    assessment_type = models.CharField(max_length=50, default="Continuous Assessment")
    title = models.CharField(max_length=120)
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="assessments")
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="assessments")
    max_score = models.DecimalField(max_digits=7, decimal_places=2, validators=[MinValueValidator(0)])
    weight = models.DecimalField(max_digits=5, decimal_places=2, default=100, validators=[MinValueValidator(0)])
    date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["term", "date", "title"]


class Grade(TimestampedModel):
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name="grades")
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name="grades")
    score = models.DecimalField(max_digits=7, decimal_places=2, validators=[MinValueValidator(0)])
    teacher_comment = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["assessment", "student"], name="unique_assessment_grade")]

    @property
    def percentage(self):
        return (self.score / self.assessment.max_score * 100) if self.assessment.max_score else 0


class ReportCard(TimestampedModel):
    STATUS_CHOICES = [
        ("DRAFT", "Draft"), ("SUBMITTED", "Submitted"), ("REVIEWED", "Reviewed"),
        ("APPROVED", "Approved"), ("PUBLISHED", "Published"),
    ]
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name="report_cards")
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="report_cards")
    published = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="DRAFT")
    overall_average = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    teacher_comment = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["student", "term"], name="unique_student_report_card")]


class Room(models.Model):
    name = models.CharField(max_length=80, unique=True)
    capacity = models.PositiveIntegerField(default=30)
    location = models.CharField(max_length=120, blank=True)
    rows = models.PositiveIntegerField(
        null=True, blank=True, help_text="Seating rows for exam hall layouts, e.g. 15 for a 15x10 hall."
    )
    columns = models.PositiveIntegerField(
        null=True, blank=True, help_text="Seating columns for exam hall layouts, e.g. 10 for a 15x10 hall."
    )

    def __str__(self):
        return self.name

    @property
    def seating_grid(self):
        """Return (rows, columns) for exam seating, falling back to a roughly square grid."""
        import math

        if self.rows and self.columns:
            return self.rows, self.columns
        columns = self.columns or max(1, math.ceil(math.sqrt(self.capacity)))
        rows = self.rows or max(1, math.ceil(self.capacity / columns))
        return rows, columns


class TimetableEntry(TimestampedModel):
    WEEKDAYS = [(i, day) for i, day in enumerate(("Monday", "Tuesday", "Wednesday", "Thursday", "Friday"), 1)]
    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE, related_name="timetable_entries")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="timetable_entries")
    teacher = models.ForeignKey(StaffProfile, on_delete=models.PROTECT, related_name="timetable_entries")
    room = models.ForeignKey(Room, on_delete=models.PROTECT, related_name="timetable_entries", null=True, blank=True)
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="timetable_entries")
    weekday = models.PositiveSmallIntegerField(choices=WEEKDAYS)
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        ordering = ["weekday", "start_time"]


class Examination(TimestampedModel):
    name = models.CharField(max_length=120)
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="examinations")
    start_date = models.DateField()
    end_date = models.DateField()
    instructions = models.TextField(blank=True)

    def __str__(self):
        return self.name


class ExamPaper(TimestampedModel):
    examination = models.ForeignKey(Examination, on_delete=models.CASCADE, related_name="papers")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="exam_papers")
    exam_date = models.DateField()
    start_time = models.TimeField()
    duration_minutes = models.PositiveIntegerField(default=90)
    room = models.ForeignKey(
        Room, on_delete=models.PROTECT, related_name="exam_papers",
        help_text="Primary/default hall. Add more halls via `overflow_rooms` for large candidate lists.",
    )
    overflow_rooms = models.ManyToManyField(
        Room, related_name="overflow_exam_papers", blank=True,
        help_text="Extra halls the seating engine may spill candidates into alongside `room`.",
    )

    class Meta:
        constraints = [models.UniqueConstraint(fields=["examination", "subject"], name="unique_exam_paper_subject")]

    @property
    def available_rooms(self):
        return [self.room, *self.overflow_rooms.all()]


class ExamCandidate(TimestampedModel):
    paper = models.ForeignKey(ExamPaper, on_delete=models.CASCADE, related_name="candidates")
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name="exam_candidates")
    room = models.ForeignKey(
        Room, on_delete=models.SET_NULL, null=True, blank=True, related_name="seated_candidates",
        help_text="Hall this candidate was allocated to by the seating engine.",
    )
    row = models.PositiveIntegerField(null=True, blank=True)
    column = models.PositiveIntegerField(null=True, blank=True)
    seat_number = models.PositiveIntegerField(null=True, blank=True)
    score = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["paper", "student"], name="unique_exam_candidate")]


class FeeStructure(TimestampedModel):
    name = models.CharField(max_length=120)
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="fee_structures")
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    mandatory = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["name", "term"], name="unique_fee_structure_term")]


class Invoice(TimestampedModel):
    STATUS_CHOICES = [("OPEN", "Open"), ("PARTIAL", "Partially paid"), ("PAID", "Paid"), ("VOID", "Void")]
    student = models.ForeignKey(StudentProfile, on_delete=models.PROTECT, related_name="invoices")
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="invoices")
    number = models.CharField(max_length=40, unique=True)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="OPEN")
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])


class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items")
    description = models.CharField(max_length=150)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])


class Payment(TimestampedModel):
    METHOD_CHOICES = [("CASH", "Cash"), ("BANK", "Bank transfer"), ("CARD", "Card"), ("ONLINE", "Online")]
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    method = models.CharField(max_length=10, choices=METHOD_CHOICES, default="CASH")
    reference = models.CharField(max_length=80, unique=True)
    paid_at = models.DateTimeField()
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)


class ParentProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="parent_profile")
    phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    students = models.ManyToManyField(StudentProfile, through="ParentStudent", related_name="parents")


class ParentStudent(models.Model):
    RELATIONSHIP_CHOICES = [("PARENT", "Parent"), ("GUARDIAN", "Guardian")]
    parent = models.ForeignKey(ParentProfile, on_delete=models.CASCADE, related_name="relationships")
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name="parent_relationships")
    relationship = models.CharField(max_length=10, choices=RELATIONSHIP_CHOICES, default="PARENT")
    is_primary = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["parent", "student"], name="unique_parent_student")]


class Announcement(TimestampedModel):
    AUDIENCE_CHOICES = [("ALL", "Everyone"), ("STAFF", "Staff"), ("STUDENTS", "Students"), ("PARENTS", "Parents")]
    title = models.CharField(max_length=150)
    body = models.TextField()
    audience = models.CharField(max_length=10, choices=AUDIENCE_CHOICES, default="ALL")
    published_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)


class Message(TimestampedModel):
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sent_messages")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="received_messages")
    subject = models.CharField(max_length=150)
    body = models.TextField()
    read_at = models.DateTimeField(null=True, blank=True)


class LeaveType(models.Model):
    name = models.CharField(max_length=80, unique=True)
    max_days = models.PositiveIntegerField(null=True, blank=True)
    requires_approval = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class LeaveRequest(TimestampedModel):
    STATUS_CHOICES = [("PENDING", "Pending"), ("APPROVED", "Approved"), ("REJECTED", "Rejected"), ("CANCELLED", "Cancelled")]
    staff = models.ForeignKey(StaffProfile, on_delete=models.CASCADE, related_name="leave_requests")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT, related_name="requests")
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="PENDING")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)


class PayrollRecord(TimestampedModel):
    staff = models.ForeignKey(StaffProfile, on_delete=models.PROTECT, related_name="payroll_records")
    period = models.DateField(help_text="Month represented by the first day of the month")
    gross_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    paid = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["staff", "period"], name="unique_staff_payroll_period")]

    @property
    def net_amount(self):
        return self.gross_amount - self.deductions


class AuditLog(models.Model):
    ACTION_CHOICES = [("CREATE", "Create"), ("UPDATE", "Update"), ("DELETE", "Delete"), ("LOGIN", "Login")]
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=100)
    object_id = models.CharField(max_length=64, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Notification(TimestampedModel):
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=150)
    body = models.TextField()
    read_at = models.DateTimeField(null=True, blank=True)
    channel = models.CharField(max_length=20, default="IN_APP")


class LibraryBook(TimestampedModel):
    isbn = models.CharField(max_length=30, unique=True)
    title = models.CharField(max_length=200)
    author = models.CharField(max_length=150)
    category = models.CharField(max_length=80, blank=True)
    copies = models.PositiveIntegerField(default=1)
    available_copies = models.PositiveIntegerField(default=1)


class LibraryLoan(TimestampedModel):
    STATUS_CHOICES = [("BORROWED", "Borrowed"), ("RETURNED", "Returned"), ("OVERDUE", "Overdue")]
    book = models.ForeignKey(LibraryBook, on_delete=models.PROTECT, related_name="loans")
    borrower = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="library_loans")
    borrowed_at = models.DateTimeField()
    due_date = models.DateField()
    returned_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="BORROWED")


class Vehicle(models.Model):
    registration_number = models.CharField(max_length=30, unique=True)
    driver_name = models.CharField(max_length=120, blank=True)
    capacity = models.PositiveIntegerField(default=30)
    active = models.BooleanField(default=True)


class TransportRoute(models.Model):
    name = models.CharField(max_length=100, unique=True)
    vehicle = models.ForeignKey(Vehicle, on_delete=models.SET_NULL, null=True, blank=True, related_name="routes")
    stops = models.JSONField(default=list, blank=True)
    fee = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])


class StudentTransport(models.Model):
    student = models.OneToOneField(StudentProfile, on_delete=models.CASCADE, related_name="transport")
    route = models.ForeignKey(TransportRoute, on_delete=models.PROTECT, related_name="students")
    pickup_stop = models.CharField(max_length=120, blank=True)
    active = models.BooleanField(default=True)


class InventoryItem(TimestampedModel):
    name = models.CharField(max_length=150)
    sku = models.CharField(max_length=40, unique=True)
    category = models.CharField(max_length=80, blank=True)
    quantity = models.IntegerField(default=0)
    reorder_level = models.PositiveIntegerField(default=0)
    unit = models.CharField(max_length=20, default="unit")


class StockTransaction(TimestampedModel):
    TRANSACTION_TYPES = [("IN", "Stock in"), ("OUT", "Stock out"), ("ADJUSTMENT", "Adjustment")]
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name="transactions")
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    quantity = models.PositiveIntegerField()
    note = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)


class DisciplinaryIncident(TimestampedModel):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name="disciplinary_incidents")
    incident_date = models.DateField()
    category = models.CharField(max_length=80)
    description = models.TextField()
    action_taken = models.TextField(blank=True)
    resolved = models.BooleanField(default=False)
    reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)


class MedicalRecord(TimestampedModel):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name="medical_records")
    visit_date = models.DateField()
    complaint = models.CharField(max_length=200)
    diagnosis = models.CharField(max_length=200, blank=True)
    treatment = models.TextField(blank=True)
    emergency_contacted = models.BooleanField(default=False)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)


class BackupRecord(TimestampedModel):
    STATUS_CHOICES = [("STARTED", "Started"), ("COMPLETED", "Completed"), ("FAILED", "Failed")]
    filename = models.CharField(max_length=255)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="STARTED")
    size_bytes = models.PositiveBigIntegerField(default=0)
    checksum = models.CharField(max_length=128, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)


class SystemSetting(models.Model):
    key = models.CharField(max_length=100, unique=True)
    value = models.JSONField(default=dict, blank=True)
    description = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.key


# Domain aliases keep integrations readable while the canonical model names stay
# explicit in migrations and the admin.
Attendance = AttendanceRecord
Exam = Examination
FeePayment = Payment
StaffLeave = LeaveRequest
Book = LibraryBook
