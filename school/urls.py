from django.urls import path
from . import finance_views
from . import academic_views

from . import views

urlpatterns = [
    path("health/", views.api_health, name="api-health"),
    path("attendance/", views.attendance_api, name="attendance-api"),
    path("attendance/scan/", views.barcode_scan_api, name="barcode-scan-api"),
    path("timetable/<int:term_id>/", views.timetable_api, name="timetable-api"),
    path("students/<int:student_id>/portal/", views.student_portal_api, name="student-portal-api"),
    path("announcements/", views.announcements_api, name="announcements-api"),
    path("terms/", views.terms_api, name="terms-api"),
    path("classes/", views.classes_api, name="classes-api"),
    path("rooms/", views.rooms_api, name="rooms-api"),
    path("exams/papers/", views.exam_papers_api, name="exam-papers-api"),
    path("scheduling/generate-timetable/", views.generate_timetable_api, name="generate-timetable-api"),
    path("scheduling/generate-seating/", views.generate_seating_api, name="generate-seating-api"),
    path("scheduling/seating/<int:paper_id>/", views.seating_plan_api, name="seating-plan-api"),
    # Finance Routes
    path('finance/invoices/', finance_views.invoices_api, name='invoices_api'),
    path('finance/paystack/initialize/', finance_views.paystack_initialize_api, name='paystack_initialize'),

    # Academic Routes
    path('academics/roster/<int:assessment_id>/', academic_views.roster_api, name='roster_api'),
    path('academics/grades/bulk-save/', academic_views.bulk_save_grades_api, name='bulk_save_grades'),

]
