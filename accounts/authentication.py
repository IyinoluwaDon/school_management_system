"""JWT helpers shared by DRF views and the project's plain Django views.

Most of the API surface in this project predates djangorestframework-simplejwt
and is written as ordinary Django view functions returning ``JsonResponse``.
Rather than rewriting every endpoint as a DRF ``APIView`` just to gain JWT
support, these helpers let any view function opt into Bearer-token auth with
a single decorator while DRF's own views (the token endpoints themselves)
keep using DRF machinery directly.
"""

import functools

from django.http import JsonResponse
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

_jwt_authenticator = JWTAuthentication()


def get_jwt_user(request):
    """Return the ``User`` for this request's Bearer token, or ``None``.

    ``JWTAuthentication.authenticate`` only needs ``request.META``, so it
    works fine against a plain ``HttpRequest`` as well as a DRF ``Request``.
    """
    try:
        result = _jwt_authenticator.authenticate(request)
    except (InvalidToken, TokenError):
        return None
    if result is None:
        return None
    user, _validated_token = result
    return user


def jwt_login_required(view_func):
    """Require a valid ``Authorization: Bearer <token>`` header.

    On success, ``request.user`` is set to the authenticated user before the
    view runs. On failure, a ``401`` JSON response is returned and the view
    is never called.
    """

    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = get_jwt_user(request)
        if user is None:
            return JsonResponse(
                {"error": "Authentication credentials were not provided or are invalid."},
                status=401,
            )
        request.user = user
        return view_func(request, *args, **kwargs)

    return wrapper


def jwt_role_required(*roles):
    """Require a valid Bearer token AND that the user has one of ``roles``.

    Usage::

        @jwt_role_required("SUPER_ADMIN", "PRINCIPAL")
        def generate_timetable_api(request):
            ...
    """

    def decorator(view_func):
        @functools.wraps(view_func)
        @jwt_login_required
        def wrapper(request, *args, **kwargs):
            if not request.user.has_role(*roles):
                return JsonResponse(
                    {"error": "You do not have permission to perform this action."},
                    status=403,
                )
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
