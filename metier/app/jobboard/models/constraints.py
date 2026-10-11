"""Small constraint builders; migrations serialize their resulting Django expressions."""

from django.db import models
from django.db.models.lookups import Exact


def allowed(field, values, name):
    return models.CheckConstraint(
        condition=models.Q(**{f"{field}__in": tuple(values)}), name=name
    )


def json_type(field, kind, name):
    return models.CheckConstraint(
        condition=Exact(
            models.Func(
                models.F(field),
                function="jsonb_typeof",
                output_field=models.CharField(),
            ),
            models.Value(kind),
        ),
        name=name,
    )
