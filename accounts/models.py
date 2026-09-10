from django.contrib.auth.models import AbstractUser
from django.db import models
import secrets


def generate_barcode_token():
    """Return a compact, collision-resistant token suitable for barcode encoding."""
    return f"SCH-{secrets.token_hex(12).upper()}"

class User(AbstractUser):
    # Define the RBAC roles for the system
    ROLE_CHOICES = (
        ('SUPER_ADMIN', 'Super Administrator'),
        ('PRINCIPAL', 'Principal/Head of School'),
        ('TEACHER', 'Teacher'),
        ('ACCOUNTANT', 'Accountant'),
        ('HR', 'HR Officer'),
        ('STUDENT', 'Student'),
        ('PARENT', 'Parent/Guardian'),
    )
    
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='STUDENT')
    
    digital_token = models.CharField(max_length=28, blank=True, null=True, unique=True, editable=False)

    def save(self, *args, **kwargs):
        if not self.digital_token:
            self.digital_token = generate_barcode_token()
        super().save(*args, **kwargs)

    def has_role(self, *roles):
        return self.role in roles

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"