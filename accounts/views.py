from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from rest_framework_simplejwt.views import TokenObtainPairView

from .authentication import jwt_login_required
from .serializers import SchoolTokenObtainPairSerializer, serialize_user


class SchoolTokenObtainPairView(TokenObtainPairView):
    """POST /api/token/ -> {access, refresh, user}.

    Thin subclass so the response includes the role-aware ``user`` payload
    the React session store expects, instead of just the raw token pair.
    """

    serializer_class = SchoolTokenObtainPairSerializer


@require_http_methods(["GET"])
@jwt_login_required
def current_user_api(request):
    """GET /api/auth/me/ -> the profile for the Bearer token's owner.

    Lets the frontend restore a session (e.g. after a page refresh) from a
    stored access token without re-submitting credentials.
    """
    return JsonResponse(serialize_user(request.user))
