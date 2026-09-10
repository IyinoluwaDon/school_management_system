import json
from collections import defaultdict
from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import User
from .models import (
    AcademicSession, Assessment, AttendanceConfig, AttendanceRecord, Examination, ExamCandidate, ExamPaper,
    FeeStructure, Grade, InventoryItem, Invoice, LibraryBook, Room, SchoolClass, StaffProfile, StudentProfile,
    Subject, SubjectAssignment, Term, TimetableEntry,
)
from .scheduling import allocate_exam_seating, generate_timetable
from .services import (
    adjust_inventory, calculate_report_card, issue_book, process_barcode_scan,
    record_attendance, return_book,
)


class PhaseOneModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="student1", password="strong-password",
            first_name="Ada", last_name="Lovelace",
        )
        self.session = AcademicSession.objects.create(
            name="2026/2027", start_date=date(2026, 9, 1), end_date=date(2027, 7, 31),
        )

    def test_user_gets_unique_barcode_token(self):
        other_user = User.objects.create_user(username="student2", password="strong-password")
        self.assertRegex(self.user.digital_token, r"^SCH-[0-9A-F]{24}$")
        self.assertNotEqual(self.user.digital_token, other_user.digital_token)

    def test_school_structure_and_student_profile(self):
        term = Term.objects.create(
            session=self.session, number=1,
            start_date=date(2026, 9, 1), end_date=date(2026, 12, 15),
        )
        school_class = SchoolClass.objects.create(name="JSS 1", arm="A")
        subject = Subject.objects.create(code="MATH", name="Mathematics")
        student = StudentProfile.objects.create(
            user=self.user, admission_number="STU-0001", school_class=school_class,
        )
        self.assertEqual(str(term), "First Term - 2026/2027")
        self.assertEqual(str(subject), "MATH - Mathematics")
        self.assertEqual(student.user.digital_token[:4], "SCH-")


class OperationalServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="ops-student", password="pass12345")
        self.school_class = SchoolClass.objects.create(name="JSS 2", arm="B")
        self.student = StudentProfile.objects.create(
            user=self.user, admission_number="OPS-0001", school_class=self.school_class
        )
        self.session = AcademicSession.objects.create(
            name="2027/2028", start_date=date(2027, 9, 1), end_date=date(2028, 7, 31)
        )
        self.term = Term.objects.create(
            session=self.session, number=1, start_date=date(2027, 9, 1), end_date=date(2027, 12, 15)
        )

    def test_attendance_and_report_card_services(self):
        record = record_attendance(self.student, date(2027, 9, 2), "PRESENT")
        self.assertEqual(record.status, "PRESENT")
        record_attendance(self.student, date(2027, 9, 2), "LATE")
        self.assertEqual(AttendanceRecord.objects.get(pk=record.pk).status, "LATE")
        subject = Subject.objects.create(code="OPS-MATH", name="Math")
        assessment = Assessment.objects.create(
            title="Test", subject=subject, term=self.term, max_score=100, weight=100
        )
        Grade.objects.create(assessment=assessment, student=self.student, score=75)
        self.assertEqual(calculate_report_card(self.student, self.term).overall_average, 75)

    def test_library_and_inventory_transactions_are_balanced(self):
        book = LibraryBook.objects.create(
            isbn="978-OPS", title="Operations", author="Staff", copies=1, available_copies=1
        )
        loan = issue_book(book, self.user, date(2027, 9, 30))
        self.assertEqual(book.__class__.objects.get(pk=book.pk).available_copies, 0)
        return_book(loan)
        self.assertEqual(book.__class__.objects.get(pk=book.pk).available_copies, 1)
        item = InventoryItem.objects.create(name="Chalk", sku="OPS-CHALK", quantity=2)
        adjust_inventory(item, 3, "IN")
        adjust_inventory(item, 1, "OUT")
        self.assertEqual(InventoryItem.objects.get(pk=item.pk).quantity, 4)

    def test_invoice_fee_structure_is_available(self):
        fee = FeeStructure.objects.create(name="Tuition", term=self.term, amount=500)
        invoice = Invoice.objects.create(
            student=self.student, term=self.term, number="INV-OPS-1", total=fee.amount
        )
        self.assertEqual(invoice.status, "OPEN")

    def test_barcode_scan_is_idempotent_and_uses_configured_lateness(self):
        AttendanceConfig.objects.create(late_threshold="07:45", absent_threshold="10:00")
        first = process_barcode_scan(self.user.digital_token, "front-gate")
        second = process_barcode_scan(self.user.digital_token, "front-gate")
        self.assertTrue(first["created"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(AttendanceRecord.objects.filter(student=self.student).count(), 1)


def _make_teacher(username, staff_number):
    user = User.objects.create_user(username=username, password="pass12345", role="TEACHER")
    return StaffProfile.objects.create(user=user, staff_number=staff_number, job_title="Teacher")


class TimetableEngineTests(TestCase):
    """Domain 2: the CP-SAT timetable engine (school/scheduling.py:generate_timetable)."""

    def setUp(self):
        self.session = AcademicSession.objects.create(
            name="2028/2029", start_date=date(2028, 9, 1), end_date=date(2029, 7, 31),
        )
        self.term = Term.objects.create(
            session=self.session, number=1, start_date=date(2028, 9, 1), end_date=date(2028, 12, 15),
        )
        self.classes = [SchoolClass.objects.create(name="JSS 3", arm=arm) for arm in ("A", "B", "C")]
        self.rooms = [Room.objects.create(name=f"Room {i}", capacity=40) for i in range(1, 4)]
        self.maths = Subject.objects.create(code="TT-MATH", name="Mathematics", is_difficult=True)
        self.physics = Subject.objects.create(code="TT-PHY", name="Physics", is_difficult=True)
        self.art = Subject.objects.create(code="TT-ART", name="Art", is_difficult=False)
        self.maths_teacher = _make_teacher("tt-maths", "TT-STAFF-1")
        self.physics_teacher = _make_teacher("tt-physics", "TT-STAFF-2")
        self.art_teacher = _make_teacher("tt-art", "TT-STAFF-3")

    def _assignments_for_all_classes(self, periods_per_week=2):
        assignments = []
        for school_class in self.classes:
            assignments.append(SubjectAssignment.objects.create(
                teacher=self.maths_teacher, subject=self.maths, school_class=school_class,
                term=self.term, periods_per_week=periods_per_week,
            ))
            assignments.append(SubjectAssignment.objects.create(
                teacher=self.physics_teacher, subject=self.physics, school_class=school_class,
                term=self.term, periods_per_week=periods_per_week,
            ))
            assignments.append(SubjectAssignment.objects.create(
                teacher=self.art_teacher, subject=self.art, school_class=school_class,
                term=self.term, periods_per_week=periods_per_week,
            ))
        return assignments

    def test_raises_without_any_assignments(self):
        with self.assertRaises(ValidationError):
            generate_timetable(self.term)

    def test_generates_the_expected_number_of_entries(self):
        assignments = self._assignments_for_all_classes(periods_per_week=2)
        summary = generate_timetable(self.term, rooms=self.rooms)
        self.assertEqual(summary["status"], "OPTIMAL")
        self.assertEqual(summary["entries_created"], len(assignments) * 2)
        self.assertEqual(TimetableEntry.objects.filter(term=self.term).count(), len(assignments) * 2)

    def test_no_teacher_class_or_room_is_ever_double_booked(self):
        self._assignments_for_all_classes(periods_per_week=3)
        generate_timetable(self.term, rooms=self.rooms)

        by_slot_teacher, by_slot_class, by_slot_room = defaultdict(int), defaultdict(int), defaultdict(int)
        for entry in TimetableEntry.objects.filter(term=self.term):
            slot = (entry.weekday, entry.start_time)
            by_slot_teacher[(slot, entry.teacher_id)] += 1
            by_slot_class[(slot, entry.school_class_id)] += 1
            by_slot_room[(slot, entry.room_id)] += 1

        self.assertTrue(all(count == 1 for count in by_slot_teacher.values()))
        self.assertTrue(all(count == 1 for count in by_slot_class.values()))
        self.assertTrue(all(count == 1 for count in by_slot_room.values()))

    def test_regenerating_replaces_the_previous_timetable(self):
        self._assignments_for_all_classes(periods_per_week=2)
        generate_timetable(self.term, rooms=self.rooms)
        first_count = TimetableEntry.objects.filter(term=self.term).count()
        generate_timetable(self.term, rooms=self.rooms, replace_existing=True)
        self.assertEqual(TimetableEntry.objects.filter(term=self.term).count(), first_count)

    def test_difficult_subjects_are_spread_across_different_days(self):
        # One class, two difficult subjects, plenty of days/periods available -
        # the soft constraint should keep them on separate days.
        school_class = self.classes[0]
        SubjectAssignment.objects.create(
            teacher=self.maths_teacher, subject=self.maths, school_class=school_class,
            term=self.term, periods_per_week=1,
        )
        SubjectAssignment.objects.create(
            teacher=self.physics_teacher, subject=self.physics, school_class=school_class,
            term=self.term, periods_per_week=1,
        )
        summary = generate_timetable(self.term, rooms=self.rooms)
        self.assertEqual(summary["difficult_subject_day_clashes"], 0)
        days = set(TimetableEntry.objects.filter(term=self.term).values_list("weekday", flat=True))
        self.assertEqual(len(days), 2)


class ExamSeatingEngineTests(TestCase):
    """Domain 2: the exam seating engine (school/scheduling.py:allocate_exam_seating)."""

    def setUp(self):
        self.session = AcademicSession.objects.create(
            name="2029/2030", start_date=date(2029, 9, 1), end_date=date(2030, 7, 31),
        )
        self.term = Term.objects.create(
            session=self.session, number=1, start_date=date(2029, 9, 1), end_date=date(2029, 12, 15),
        )
        self.examination = Examination.objects.create(
            name="Mid Term", term=self.term, start_date=date(2029, 10, 1), end_date=date(2029, 10, 5),
        )
        self.subject = Subject.objects.create(code="EX-MATH", name="Mathematics")
        self.hall = Room.objects.create(name="Main Hall", capacity=100, rows=10, columns=10)
        self.paper = ExamPaper.objects.create(
            examination=self.examination, subject=self.subject,
            exam_date=date(2029, 10, 1), start_time="09:00", room=self.hall,
        )

    def _register_candidates(self, class_sizes):
        """class_sizes: dict of {class_name: student_count}."""
        for class_name, count in class_sizes.items():
            school_class = SchoolClass.objects.create(name=class_name, arm="A")
            for i in range(count):
                user = User.objects.create_user(username=f"{class_name}-{i}", password="pass12345")
                student = StudentProfile.objects.create(
                    user=user, admission_number=f"{class_name}-{i:03d}", school_class=school_class,
                )
                ExamCandidate.objects.create(paper=self.paper, student=student)

    def test_raises_with_no_candidates(self):
        with self.assertRaises(ValidationError):
            allocate_exam_seating(self.paper)

    def test_raises_when_capacity_is_insufficient(self):
        self.hall.capacity = 2
        self.hall.save(update_fields=["capacity"])
        self._register_candidates({"JSS1": 3})
        with self.assertRaises(ValidationError):
            allocate_exam_seating(self.paper)

    def test_every_candidate_gets_a_unique_seat_within_capacity(self):
        self._register_candidates({"JSS1": 20, "JSS2": 20, "JSS3": 20})
        summary = allocate_exam_seating(self.paper)
        self.assertEqual(summary["seated"], 60)
        seats = list(ExamCandidate.objects.filter(paper=self.paper).values_list("room_id", "row", "column"))
        self.assertEqual(len(seats), len(set(seats)))  # no two candidates share a seat

    def test_same_class_students_are_never_seated_directly_beside_or_behind_each_other(self):
        # Three evenly-sized classes in a big hall: a fully conflict-free
        # arrangement exists, so the engine should find it (0 unresolved clashes).
        self._register_candidates({"JSS1": 30, "JSS2": 30, "JSS3": 30})
        summary = allocate_exam_seating(self.paper)
        self.assertEqual(summary["unresolved_adjacencies"], 0)

        grid = {}
        for candidate in ExamCandidate.objects.filter(paper=self.paper).select_related("student"):
            grid[(candidate.row, candidate.column)] = candidate.student.school_class_id

        for (row, col), class_id in grid.items():
            if (row, col - 1) in grid:
                self.assertNotEqual(grid[(row, col - 1)], class_id, f"same-class neighbours at col {col-1}/{col}")
            if (row - 1, col) in grid:
                self.assertNotEqual(grid[(row - 1, col)], class_id, f"same-class neighbours at row {row-1}/{row}")

    def test_overflow_room_is_used_when_the_primary_hall_is_full(self):
        overflow = Room.objects.create(name="Overflow Hall", capacity=50, rows=5, columns=10)
        self.hall.capacity = 10
        self.hall.rows, self.hall.columns = 2, 5
        self.hall.save(update_fields=["capacity", "rows", "columns"])
        self.paper.overflow_rooms.add(overflow)
        self._register_candidates({"JSS1": 15, "JSS2": 15})
        summary = allocate_exam_seating(self.paper)
        self.assertEqual(summary["seated"], 30)
        self.assertEqual(summary["rooms_used"], 2)


class SchedulingAPITests(TestCase):
    """End-to-end: login -> Bearer token -> the Domain 2 HTTP endpoints, with RBAC enforced."""

    def setUp(self):
        self.admin_user = User.objects.create_user(username="sched-admin", password="pass12345", role="SUPER_ADMIN")
        self.teacher_user = User.objects.create_user(username="sched-teacher", password="pass12345", role="TEACHER")

        self.session = AcademicSession.objects.create(
            name="2030/2031", start_date=date(2030, 9, 1), end_date=date(2031, 7, 31),
        )
        self.term = Term.objects.create(
            session=self.session, number=1, start_date=date(2030, 9, 1), end_date=date(2030, 12, 15),
        )
        self.room = Room.objects.create(name="API Room", capacity=40, rows=5, columns=8)
        self.school_class = SchoolClass.objects.create(name="SS 1", arm="A")
        self.subject = Subject.objects.create(code="API-MATH", name="Mathematics")
        self.teacher = _make_teacher("sched-api-teacher", "API-STAFF-1")
        SubjectAssignment.objects.create(
            teacher=self.teacher, subject=self.subject, school_class=self.school_class,
            term=self.term, periods_per_week=2,
        )

        self.examination = Examination.objects.create(
            name="API Exam", term=self.term, start_date=date(2030, 10, 1), end_date=date(2030, 10, 2),
        )
        self.paper = ExamPaper.objects.create(
            examination=self.examination, subject=self.subject,
            exam_date=date(2030, 10, 1), start_time="09:00", room=self.room,
        )
        student_user = User.objects.create_user(username="api-student", password="pass12345")
        student = StudentProfile.objects.create(
            user=student_user, admission_number="API-0001", school_class=self.school_class,
        )
        ExamCandidate.objects.create(paper=self.paper, student=student)

    def _token_for(self, username):
        response = self.client.post(
            "/api/token/", {"username": username, "password": "pass12345"}, content_type="application/json",
        )
        return response.json()["access"]

    def _auth_header(self, username):
        return {"HTTP_AUTHORIZATION": f"Bearer {self._token_for(username)}"}

    def test_generate_timetable_requires_authentication(self):
        response = self.client.post(
            "/api/scheduling/generate-timetable/", {"term_id": self.term.id}, content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_generate_timetable_rejects_non_admin_roles(self):
        response = self.client.post(
            "/api/scheduling/generate-timetable/", {"term_id": self.term.id},
            content_type="application/json", **self._auth_header("sched-teacher"),
        )
        self.assertEqual(response.status_code, 403)

    def test_generate_timetable_succeeds_for_admin_role(self):
        response = self.client.post(
            "/api/scheduling/generate-timetable/",
            {"term_id": self.term.id, "room_ids": [self.room.id]},
            content_type="application/json", **self._auth_header("sched-admin"),
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["entries_created"], 2)

    def test_generate_seating_and_read_back_the_plan(self):
        response = self.client.post(
            "/api/scheduling/generate-seating/", {"paper_id": self.paper.id},
            content_type="application/json", **self._auth_header("sched-admin"),
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["seated"], 1)

        response = self.client.get(
            f"/api/scheduling/seating/{self.paper.id}/", **self._auth_header("sched-teacher"),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["paper"]["subject"], "Mathematics")
        self.assertEqual(len(data["halls"][0]["seats"]), 1)

    def test_lookup_endpoints_require_auth_and_return_reference_data(self):
        for path in ("/api/terms/", "/api/classes/", "/api/rooms/", "/api/exams/papers/"):
            self.assertEqual(self.client.get(path).status_code, 401)

        headers = self._auth_header("sched-teacher")
        self.assertEqual(self.client.get("/api/terms/", **headers).json()["results"][0]["id"], self.term.id)
        self.assertEqual(self.client.get("/api/rooms/", **headers).json()["results"][0]["name"], "API Room")
        papers = self.client.get("/api/exams/papers/", **headers).json()["results"]
        self.assertEqual(papers[0]["subject"], "Mathematics")
        self.assertEqual(papers[0]["candidate_count"], 1)
