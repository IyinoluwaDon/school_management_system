from django.contrib import admin

from .models import (
    AcademicSession, Announcement, Assessment, AttendanceConfig, AttendanceRecord, AuditLog, BackupRecord,
    DisciplinaryIncident, Enrollment, ExamCandidate, ExamPaper, Examination, FeeStructure,
    Grade, InventoryItem, Invoice, InvoiceItem, LeaveRequest, LeaveType, LibraryBook,
    LibraryLoan, MedicalRecord, Message, Notification, ParentProfile, ParentStudent,
    Payment, PayrollRecord, ReportCard, Room, SchoolClass, StaffProfile, StudentProfile,
    StaffAttendance, StockTransaction, Subject, SubjectAssignment, SystemSetting, Term, TimetableEntry,
    TransportRoute, StudentTransport, Vehicle,
)


@admin.register(AcademicSession)
class AcademicSessionAdmin(admin.ModelAdmin):
    list_display = ("name", "start_date", "end_date", "is_active")
    list_filter = ("is_active",)


@admin.register(Term)
class TermAdmin(admin.ModelAdmin):
    list_display = ("name", "session", "start_date", "end_date")
    list_filter = ("number", "session")


@admin.register(SchoolClass)
class SchoolClassAdmin(admin.ModelAdmin):
    list_display = ("name", "arm", "level")
    search_fields = ("name", "arm", "level")


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("admission_number", "user", "school_class")
    search_fields = ("admission_number", "user__username", "user__first_name", "user__last_name")
    list_filter = ("school_class",)


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ("staff_number", "user", "job_title", "department")
    search_fields = ("staff_number", "user__username", "user__first_name", "user__last_name")


# Keep every operational module manageable from the existing Django admin.
for _model in (
    Enrollment, AttendanceConfig, AttendanceRecord, StaffAttendance, SubjectAssignment, Assessment, Grade, ReportCard,
    Room, TimetableEntry, Examination, ExamPaper, ExamCandidate, FeeStructure, Invoice,
    InvoiceItem, Payment, ParentProfile, ParentStudent, Announcement, Message, LeaveType,
    LeaveRequest, PayrollRecord, AuditLog, Notification, LibraryBook, LibraryLoan, Vehicle,
    TransportRoute, StudentTransport, InventoryItem, StockTransaction, DisciplinaryIncident,
    MedicalRecord, BackupRecord, SystemSetting,
):
    admin.site.register(_model)
