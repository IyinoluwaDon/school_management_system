import json
from datetime import date, time

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.exceptions import ValidationError

from accounts.authentication import jwt_login_required, jwt_role_required
from .models import (
    Announcement,
    AttendanceRecord,
    ExamCandidate,
    ExamPaper,
    Invoice,
    Room,
    SchoolClass,
    StudentProfile,
    Term,
    TimetableEntry,
)
from .scheduling import allocate_exam_seating, generate_timetable
from .services import process_barcode_scan, record_attendance

STAFF_ROLES = ("SUPER_ADMIN", "PRINCIPAL", "TEACHER", "ACCOUNTANT", "HR")
SCHEDULING_ROLES = ("SUPER_ADMIN", "PRINCIPAL")


def _parse_date(value):
    return date.fromisoformat(value) if value else date.today()


def _can_view_student(user, student):
    """RBAC scoping shared by the attendance and student-portal endpoints.

    Staff roles can view any student. A student can only view their own
    record. A parent can only view a student they are linked to.
    """
    if user.has_role(*STAFF_ROLES):
        return True
    if user.has_role("STUDENT"):
        return hasattr(user, "student_profile") and user.student_profile_id == student.id
    if user.has_role("PARENT"):
        return hasattr(user, "parent_profile") and user.parent_profile.students.filter(pk=student.id).exists()
    return False


def api_health(request):
    return JsonResponse({"service": "school-management", "status": "ok"})


@csrf_exempt
@require_http_methods(["POST"])
def barcode_scan_api(request):
    # Deliberately left open to Bearer auth: this is called by unattended
    # gate/scanner hardware identifying people by their own barcode token,
    # not by a logged-in portal user.
    try:
        payload = json.loads(request.body or "{}")
        result = process_barcode_scan(payload["barcode_token"], payload.get("device_id", ""))
        return JsonResponse(result, status=201 if result["created"] else 200)
    except (KeyError, ValueError, ValidationError) as error:
        return JsonResponse({"error": str(error)}, status=400)


@csrf_exempt
@require_http_methods(["GET", "POST"])
@jwt_login_required
def attendance_api(request):
    if request.method == "GET":
        records = AttendanceRecord.objects.select_related("student__user").all()
        requested_student = request.GET.get("student")
        if requested_student:
            try:
                student = StudentProfile.objects.get(pk=requested_student)
            except StudentProfile.DoesNotExist:
                return JsonResponse({"error": "Unknown student."}, status=404)
            if not _can_view_student(request.user, student):
                return JsonResponse({"error": "You cannot view this student's attendance."}, status=403)
            records = records.filter(student_id=requested_student)
        elif not request.user.has_role(*STAFF_ROLES):
            # Non-staff callers with no explicit ?student= are scoped to
            # themselves rather than seeing the whole school's records.
            if request.user.has_role("STUDENT") and hasattr(request.user, "student_profile"):
                records = records.filter(student_id=request.user.student_profile_id)
            elif request.user.has_role("PARENT") and hasattr(request.user, "parent_profile"):
                records = records.filter(student__in=request.user.parent_profile.students.all())
            else:
                records = records.none()
        if request.GET.get("date"):
            records = records.filter(date=_parse_date(request.GET["date"]))
        return JsonResponse(
            {
                "results": [
                    {
                        "id": record.id,
                        "student": record.student_id,
                        "date": record.date.isoformat(),
                        "status": record.status,
                        "method": record.method,
                        "notes": record.notes,
                    }
                    for record in records[:500]
                ]
            }
        )
    if not request.user.has_role(*STAFF_ROLES):
        return JsonResponse({"error": "Only staff can record manual attendance overrides."}, status=403)
    try:
        payload = json.loads(request.body or "{}")
        student = StudentProfile.objects.get(pk=payload["student_id"])
        record = record_attendance(
            student,
            _parse_date(payload.get("date")),
            payload.get("status", "PRESENT"),
            request.user,
            payload.get("method", "MANUAL"),
            payload.get("notes", ""),
        )
        return JsonResponse({"id": record.id, "status": record.status}, status=201)
    except (KeyError, ValueError, StudentProfile.DoesNotExist) as error:
        return JsonResponse({"error": str(error)}, status=400)


@jwt_login_required
def timetable_api(request, term_id):
    entries = TimetableEntry.objects.filter(term_id=term_id).select_related("subject", "school_class", "teacher__user")
    school_class = request.GET.get("class")
    if school_class:
        entries = entries.filter(school_class_id=school_class)
    return JsonResponse(
        {
            "term": term_id,
            "results": [
                {
                    "id": entry.id,
                    "weekday": entry.weekday,
                    "start": entry.start_time.isoformat(),
                    "end": entry.end_time.isoformat(),
                    "subject": entry.subject.name,
                    "class": str(entry.school_class),
                    "class_id": entry.school_class_id,
                    "teacher": entry.teacher.user.get_full_name() or entry.teacher.user.username,
                    "room": entry.room.name if entry.room_id else None,
                }
                for entry in entries
            ],
        }
    )


@jwt_login_required
def student_portal_api(request, student_id):
    try:
        student = StudentProfile.objects.select_related("user", "school_class").get(pk=student_id)
    except StudentProfile.DoesNotExist:
        return JsonResponse({"error": "Unknown student."}, status=404)
    if not _can_view_student(request.user, student):
        return JsonResponse({"error": "You cannot view this student's portal."}, status=403)
    attendance = AttendanceRecord.objects.filter(student=student)
    return JsonResponse(
        {
            "student": {
                "id": student.id,
                "name": student.user.get_full_name() or student.user.username,
                "admission_number": student.admission_number,
                "class": str(student.school_class),
            },
            "attendance": {
                "present": attendance.filter(status="PRESENT").count(),
                "absent": attendance.filter(status="ABSENT").count(),
                "late": attendance.filter(status="LATE").count(),
                "excused": attendance.filter(status="EXCUSED").count(),
            },
            "invoices": list(
                Invoice.objects.filter(student=student).values("number", "total", "status", "due_date")
            ),
        }
    )


@jwt_login_required
def terms_api(request):
    terms = Term.objects.select_related("session").order_by("-session__start_date", "number")
    return JsonResponse(
        {"results": [{"id": term.id, "name": str(term), "session": term.session.name} for term in terms]}
    )


@jwt_login_required
def classes_api(request):
    classes = SchoolClass.objects.order_by("name", "arm")
    return JsonResponse({"results": [{"id": cls.id, "name": str(cls)} for cls in classes]})


@jwt_login_required
def rooms_api(request):
    rooms = Room.objects.order_by("name")
    return JsonResponse(
        {"results": [{"id": room.id, "name": room.name, "capacity": room.capacity} for room in rooms]}
    )


@jwt_login_required
def exam_papers_api(request):
    papers = ExamPaper.objects.select_related("subject", "examination", "room").order_by("-exam_date")
    return JsonResponse(
        {
            "results": [
                {
                    "id": paper.id,
                    "subject": paper.subject.name,
                    "examination": paper.examination.name,
                    "exam_date": paper.exam_date.isoformat(),
                    "room": paper.room.name,
                    "candidate_count": paper.candidates.count(),
                }
                for paper in papers
            ]
        }
    )


def announcements_api(request):
    announcements = Announcement.objects.order_by("-published_at", "-created_at")
    return JsonResponse(
        {
            "results": [
                {"id": item.id, "title": item.title, "body": item.body, "audience": item.audience}
                for item in announcements[:100]
            ]
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
@jwt_role_required(*SCHEDULING_ROLES)
def generate_timetable_api(request):
    """POST /api/scheduling/generate-timetable/

    Body: {
      "term_id": 1,
      "room_ids": [1, 2, 3],           # optional, defaults to every Room
      "weekdays": [1, 2, 3, 4, 5],      # optional, 1=Monday .. 5=Friday
      "periods_per_day": 8,            # optional
      "period_minutes": 40,            # optional
      "day_start": "08:00",            # optional, "HH:MM"
      "replace_existing": true         # optional
    }
    """
    try:
        payload = json.loads(request.body or "{}")
        term = Term.objects.get(pk=payload["term_id"])
        kwargs = {}
        if payload.get("room_ids"):
            kwargs["rooms"] = list(Room.objects.filter(pk__in=payload["room_ids"]))
        if payload.get("weekdays"):
            kwargs["weekdays"] = tuple(payload["weekdays"])
        if payload.get("periods_per_day"):
            kwargs["periods_per_day"] = int(payload["periods_per_day"])
        if payload.get("period_minutes"):
            kwargs["period_minutes"] = int(payload["period_minutes"])
        if payload.get("day_start"):
            hour, minute = (int(part) for part in payload["day_start"].split(":")[:2])
            kwargs["day_start"] = time(hour, minute)
        if "replace_existing" in payload:
            kwargs["replace_existing"] = bool(payload["replace_existing"])

        summary = generate_timetable(term, **kwargs)
        return JsonResponse(summary, status=201)
    except KeyError as error:
        return JsonResponse({"error": f"Missing required field: {error}"}, status=400)
    except Term.DoesNotExist:
        return JsonResponse({"error": "Unknown term_id."}, status=404)
    except ValidationError as error:
        return JsonResponse({"error": str(error)}, status=422)
    except (ValueError, TypeError) as error:
        return JsonResponse({"error": str(error)}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
@jwt_role_required(*SCHEDULING_ROLES)
def generate_seating_api(request):
    """POST /api/scheduling/generate-seating/

    Body: {
      "paper_id": 1,
      "room_ids": [1, 2],   # optional, defaults to the paper's room + overflow_rooms
      "columns": 10          # optional, overrides each room's own grid width
    }
    """
    try:
        payload = json.loads(request.body or "{}")
        paper = ExamPaper.objects.select_related("room").get(pk=payload["paper_id"])
        kwargs = {}
        if payload.get("room_ids"):
            kwargs["rooms"] = list(Room.objects.filter(pk__in=payload["room_ids"]))
        if payload.get("columns"):
            kwargs["columns"] = int(payload["columns"])

        summary = allocate_exam_seating(paper, **kwargs)
        return JsonResponse(summary, status=201)
    except KeyError as error:
        return JsonResponse({"error": f"Missing required field: {error}"}, status=400)
    except ExamPaper.DoesNotExist:
        return JsonResponse({"error": "Unknown paper_id."}, status=404)
    except ValidationError as error:
        return JsonResponse({"error": str(error)}, status=422)
    except (ValueError, TypeError) as error:
        return JsonResponse({"error": str(error)}, status=400)


@jwt_login_required
def seating_plan_api(request, paper_id):
    """GET /api/scheduling/seating/<paper_id>/ -> the seating plan, grouped by hall."""
    try:
        paper = ExamPaper.objects.select_related("subject", "examination").get(pk=paper_id)
    except ExamPaper.DoesNotExist:
        return JsonResponse({"error": "Unknown paper_id."}, status=404)

    candidates = (
        ExamCandidate.objects.filter(paper=paper)
        .select_related("student__user", "student__school_class", "room")
        .order_by("room_id", "row", "column")
    )
    halls = {}
    for candidate in candidates:
        if candidate.room_id:
            room_key, room_name = candidate.room_id, candidate.room.name
            rows, columns = candidate.room.seating_grid
        else:
            room_key, room_name, rows, columns = "unassigned", "Unassigned", None, None
        hall = halls.setdefault(room_key, {"room": room_name, "rows": rows, "columns": columns, "seats": []})
        hall["seats"].append(
            {
                "student_id": candidate.student_id,
                "name": candidate.student.user.get_full_name() or candidate.student.user.username,
                "admission_number": candidate.student.admission_number,
                "class": str(candidate.student.school_class),
                "class_id": candidate.student.school_class_id,
                "row": candidate.row,
                "column": candidate.column,
                "seat_number": candidate.seat_number,
            }
        )
    return JsonResponse(
        {
            "paper": {
                "id": paper.id,
                "subject": paper.subject.name,
                "examination": paper.examination.name,
                "exam_date": paper.exam_date.isoformat(),
            },
            "halls": list(halls.values()),
        }
    )
