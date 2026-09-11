"""Standalone PDF report-card generation. No Django views/urls are touched here."""

from datetime import date
from decimal import Decimal
from io import BytesIO

from weasyprint import HTML

REPORT_CARD_TEMPLATE = """
<html>
<head>
<style>
  @page {{ size: A4; margin: 22mm 18mm; }}
  body {{ font-family: 'Helvetica', 'DejaVu Sans', sans-serif; color: #1a2634; font-size: 12px; }}
  h1 {{ font-size: 20px; margin-bottom: 2px; }}
  .school-name {{ font-size: 22px; font-weight: 700; letter-spacing: 0.5px; }}
  .meta-table {{ width: 100%; border-collapse: collapse; margin: 14px 0 18px; }}
  .meta-table td {{ padding: 3px 0; font-size: 12px; }}
  .meta-table td.label {{ color: #5a6b7b; width: 110px; }}
  table.scores {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
  table.scores th, table.scores td {{ border: 1px solid #c7d2db; padding: 6px 8px; font-size: 11.5px; text-align: left; }}
  table.scores th {{ background: #eef2f6; text-transform: uppercase; font-size: 10px; letter-spacing: 0.4px; }}
  table.scores td.num {{ text-align: center; }}
  .summary {{ display: flex; justify-content: space-between; margin-top: 18px; }}
  .summary-box {{ border: 1px solid #c7d2db; border-radius: 6px; padding: 10px 14px; width: 30%; }}
  .summary-box .value {{ font-size: 20px; font-weight: 700; }}
  .summary-box .label {{ font-size: 10.5px; color: #5a6b7b; text-transform: uppercase; }}
  .comment {{ margin-top: 18px; }}
  .comment h3 {{ font-size: 12px; margin-bottom: 4px; }}
  .signatures {{ display: flex; justify-content: space-between; margin-top: 40px; }}
  .signatures div {{ width: 40%; border-top: 1px solid #1a2634; padding-top: 4px; font-size: 11px; text-align: center; }}
</style>
</head>
<body>
  <div class="school-name">{school_name}</div>
  <h1>Student Report Card</h1>
  <table class="meta-table">
    <tr><td class="label">Student</td><td>{student_name} ({admission_number})</td>
        <td class="label">Term</td><td>{term_name}</td></tr>
    <tr><td class="label">Class</td><td>{class_name}</td>
        <td class="label">Session</td><td>{session_name}</td></tr>
  </table>

  <table class="scores">
    <thead><tr><th>Subject</th><th>CA (/{ca_max})</th><th>Exam (/{exam_max})</th><th>Total</th><th>Grade</th><th>Remark</th></tr></thead>
    <tbody>
      {subject_rows}
    </tbody>
  </table>

  <div class="summary">
    <div class="summary-box"><div class="value">{overall_average}%</div><div class="label">Overall average</div></div>
    <div class="summary-box"><div class="value">{attendance_present}/{attendance_total}</div><div class="label">Days present</div></div>
    <div class="summary-box"><div class="value">{position}</div><div class="label">Position in class</div></div>
  </div>

  <div class="comment"><h3>Teacher's comment</h3><p>{teacher_comment}</p></div>
  <div class="comment"><h3>Principal's comment</h3><p>{principal_comment}</p></div>

  <div class="signatures">
    <div>Class Teacher</div>
    <div>Principal</div>
  </div>

  <p style="margin-top:24px;color:#8393a1;font-size:10px;">Generated {generated_on}</p>
</body>
</html>
"""


def _row_html(subject):
    return (
        "<tr>"
        f"<td>{subject['name']}</td>"
        f"<td class=\"num\">{subject.get('ca_score', '-')}</td>"
        f"<td class=\"num\">{subject.get('exam_score', '-')}</td>"
        f"<td class=\"num\">{subject.get('total', '-')}</td>"
        f"<td class=\"num\">{subject.get('grade', '-')}</td>"
        f"<td>{subject.get('remark', '')}</td>"
        "</tr>"
    )


def generate_report_card_pdf(score_data: dict, school_name: str = "Northstar School") -> BytesIO:
    """Render a student's score dictionary into a PDF report card and return an in-memory buffer.

    Expected shape of ``score_data`` (extra keys are ignored, missing optional
    keys fall back to sensible blanks so a partially-filled dict won't crash):

        {
            "student": {"name": "...", "admission_number": "...", "class_name": "...",
                        "term_name": "...", "session_name": "..."},
            "subjects": [
                {"name": "Mathematics", "ca_score": 28, "exam_score": 55,
                 "total": 83, "grade": "A", "remark": "Excellent"},
                ...
            ],
            "ca_max": 30, "exam_max": 70,
            "overall_average": 78.5,
            "attendance": {"present": 80, "total": 84},
            "position": "3rd of 32",
            "teacher_comment": "...", "principal_comment": "...",
        }

    Returns a ``BytesIO`` positioned at 0, ready to stream out of a Django
    view (e.g. via ``FileResponse``) or write to storage.
    """
    student = score_data.get("student", {})
    attendance = score_data.get("attendance", {})
    subject_rows = "".join(_row_html(s) for s in score_data.get("subjects", []))

    html = REPORT_CARD_TEMPLATE.format(
        school_name=school_name,
        student_name=student.get("name", ""),
        admission_number=student.get("admission_number", ""),
        term_name=student.get("term_name", ""),
        class_name=student.get("class_name", ""),
        session_name=student.get("session_name", ""),
        ca_max=score_data.get("ca_max", "-"),
        exam_max=score_data.get("exam_max", "-"),
        subject_rows=subject_rows or "<tr><td colspan=\"6\">No scores recorded.</td></tr>",
        overall_average=score_data.get("overall_average", 0),
        attendance_present=attendance.get("present", "-"),
        attendance_total=attendance.get("total", "-"),
        position=score_data.get("position", "-"),
        teacher_comment=score_data.get("teacher_comment", "") or "—",
        principal_comment=score_data.get("principal_comment", "") or "—",
        generated_on=date.today().isoformat(),
    )

    buffer = BytesIO()
    HTML(string=html).write_pdf(buffer)
    buffer.seek(0)
    return buffer


def build_score_dict(student, term, school_name: str = "Northstar School") -> dict:
    """Optional helper: assemble the ``score_data`` dict above straight from your
    existing Grade/Assessment/AttendanceRecord models for one student + term.

    Not part of the original ask — only import this if your grading data
    already lives in those models and you'd rather not hand-build the dict.
    """
    from .models import AttendanceRecord, Grade, ReportCard

    grades = Grade.objects.filter(student=student, assessment__term=term).select_related("assessment__subject")
    by_subject = {}
    for grade in grades:
        subject_name = grade.assessment.subject.name
        entry = by_subject.setdefault(subject_name, {"name": subject_name, "ca_score": Decimal("0"), "exam_score": Decimal("0")})
        if "exam" in grade.assessment.assessment_type.lower():
            entry["exam_score"] += grade.score
        else:
            entry["ca_score"] += grade.score

    subjects = []
    for entry in by_subject.values():
        total = entry["ca_score"] + entry["exam_score"]
        entry["total"] = total
        entry["grade"] = "A" if total >= 70 else "B" if total >= 60 else "C" if total >= 50 else "D" if total >= 40 else "F"
        subjects.append(entry)

    attendance_qs = AttendanceRecord.objects.filter(student=student, date__range=(term.start_date, term.end_date))
    report_card = ReportCard.objects.filter(student=student, term=term).first()

    return {
        "student": {
            "name": student.user.get_full_name() or student.user.username,
            "admission_number": student.admission_number,
            "class_name": str(student.school_class),
            "term_name": str(term),
            "session_name": term.session.name,
        },
        "subjects": subjects,
        "overall_average": float(report_card.overall_average) if report_card else 0,
        "attendance": {
            "present": attendance_qs.filter(status="PRESENT").count(),
            "total": attendance_qs.count(),
        },
        "teacher_comment": report_card.teacher_comment if report_card else "",
        "principal_comment": "",
    }