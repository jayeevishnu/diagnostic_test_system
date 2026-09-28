from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import ProtectedError
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler


class Conflict(APIException):
    """The request is valid but clashes with the current state of the resource."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "The request conflicts with the current state of the resource."
    default_code = "conflict"


def api_exception_handler(exc, context):
    # Turn common Django-level errors into clean API responses instead of 500s.
    if isinstance(exc, DjangoValidationError):
        exc = ValidationError(exc.message_dict if hasattr(exc, "error_dict") else exc.messages)
    elif isinstance(exc, ProtectedError):
        return Response(
            {"detail": "This resource is referenced by other records and cannot be deleted."},
            status=status.HTTP_409_CONFLICT,
        )
    return exception_handler(exc, context)
