from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class SchoolUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("School access", {"fields": ("role", "digital_token")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("School access", {"fields": ("role",)}),
    )
    list_display = ("username", "email", "role", "is_active", "digital_token")
    list_filter = ("role", "is_active", "is_staff")
