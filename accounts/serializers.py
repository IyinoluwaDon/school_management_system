from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


def serialize_user(user):
    """Shared shape for "who is logged in" data, used by /api/token/ and /api/auth/me/."""
    profile_id, profile_type = None, None
    if hasattr(user, "student_profile"):
        profile_id, profile_type = user.student_profile.id, "STUDENT"
    elif hasattr(user, "staff_profile"):
        profile_id, profile_type = user.staff_profile.id, "STAFF"

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": user.get_full_name() or user.username,
        "role": user.role,
        "digital_token": user.digital_token,
        "profile_id": profile_id,
        "profile_type": profile_type,
        "is_active": user.is_active,
    }


class SchoolTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Issues the standard access/refresh pair, plus embedded role + profile data.

    Embedding the role in the JWT claims lets any downstream service trust the
    role without a database round trip; embedding the full ``user`` object in
    the response body lets the frontend populate its session store from this
    single call instead of firing a second request.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        token["full_name"] = user.get_full_name() or user.username
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = serialize_user(self.user)
        return data
