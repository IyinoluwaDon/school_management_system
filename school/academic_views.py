import json
from django.http import JsonResponse
from accounts.authentication import jwt_login_required
from .models import Assessment, Grade, StudentProfile 

@jwt_login_required
def roster_api(request, assessment_id):
    # Fetches the roster for GradeEntryGrid.tsx using StudentProfile
    assessment = Assessment.objects.select_related('subject', 'school_class').get(pk=assessment_id)
    students = StudentProfile.objects.filter(school_class=assessment.school_class)
    
    roster = []
    for student in students:
        grade = Grade.objects.filter(student=student, assessment=assessment).first()
        roster.append({
            "student_id": student.id,
            "name": student.user.get_full_name() or student.user.username,
            "admission_number": student.admission_number,
            "score": float(grade.score) if grade else None
        })
        
    return JsonResponse({
        "assessment": {
            "id": assessment.id,
            "title": assessment.title,
            "subject": assessment.subject.name,
            "class_name": str(assessment.school_class),
            "max_score": float(assessment.max_score)
        },
        "roster": roster
    })

@jwt_login_required
def bulk_save_grades_api(request):
    # Saves the scores from GradeEntryGrid.tsx
    payload = json.loads(request.body)
    assessment = Assessment.objects.get(pk=payload["assessment_id"])
    
    for item in payload.get("scores", []):
        student = StudentProfile.objects.get(pk=item["student_id"])
        Grade.objects.update_or_create(
            student=student,
            assessment=assessment,
            defaults={"score": item["score"]}
        )
    return JsonResponse({"status": "success"})