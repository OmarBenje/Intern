"""Server-owned onboarding progression and validated candidate declarations."""

from django.db import transaction
from django.urls import path
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

from jobboard.api.core import APIError
from jobboard.api.serializers import StrictSerializer
from jobboard.models import CandidateProfile, WorkAuthorization
from jobboard.services.profiles import bump, locked_profile

COUNTRIES = ["AD", "AE", "AF", "AG", "AI", "AL", "AM", "AO", "AQ", "AR", "AS", "AT", "AU", "AW", "AX", "AZ", "BA", "BB", "BD", "BE", "BF", "BG", "BH", "BI", "BJ", "BL", "BM", "BN", "BO", "BQ", "BR", "BS", "BT", "BV", "BW", "BY", "BZ", "CA", "CC", "CD", "CF", "CG", "CH", "CI", "CK", "CL", "CM", "CN", "CO", "CR", "CU", "CV", "CW", "CX", "CY", "CZ", "DE", "DJ", "DK", "DM", "DO", "DZ", "EC", "EE", "EG", "EH", "ER", "ES", "ET", "FI", "FJ", "FK", "FM", "FO", "FR", "GA", "GB", "GD", "GE", "GF", "GG", "GH", "GI", "GL", "GM", "GN", "GP", "GQ", "GR", "GS", "GT", "GU", "GW", "GY", "HK", "HM", "HN", "HR", "HT", "HU", "ID", "IE", "IL", "IM", "IN", "IO", "IQ", "IR", "IS", "IT", "JE", "JM", "JO", "JP", "KE", "KG", "KH", "KI", "KM", "KN", "KP", "KR", "KW", "KY", "KZ", "LA", "LB", "LC", "LI", "LK", "LR", "LS", "LT", "LU", "LV", "LY", "MA", "MC", "MD", "ME", "MF", "MG", "MH", "MK", "ML", "MM", "MN", "MO", "MP", "MQ", "MR", "MS", "MT", "MU", "MV", "MW", "MX", "MY", "MZ", "NA", "NC", "NE", "NF", "NG", "NI", "NL", "NO", "NP", "NR", "NU", "NZ", "OM", "PA", "PE", "PF", "PG", "PH", "PK", "PL", "PM", "PN", "PR", "PS", "PT", "PW", "PY", "QA", "RE", "RO", "RS", "RU", "RW", "SA", "SB", "SC", "SD", "SE", "SG", "SH", "SI", "SJ", "SK", "SL", "SM", "SN", "SO", "SR", "SS", "ST", "SV", "SX", "SY", "SZ", "TC", "TD", "TF", "TG", "TH", "TJ", "TK", "TL", "TM", "TN", "TO", "TR", "TT", "TV", "TW", "TZ", "UA", "UG", "UM", "US", "UY", "UZ", "VA", "VC", "VE", "VG", "VI", "VN", "VU", "WF", "WS", "YE", "YT", "ZA", "ZM", "ZW"]
ADDRESS_FIELDS = (
    "street_address",
    "city",
    "postal_code",
    "district",
    "region",
    "country_code",
)
BASES = ("citizen", "permanent_resident", "work_permit", "student", "other", "none")


def next_step(profile):
    if not profile or not profile.current_resume_id:
        return "resume"
    if not all(
        getattr(profile, name) for name in ("street_address", "city", "country_code")
    ):
        return "address"
    if not profile.onboarding_completed_at:
        return "work-eligibility"
    return "complete"


def state(profile):
    return {
        "step": next_step(profile),
        "address": {name: getattr(profile, name, "") for name in ADDRESS_FIELDS},
        "citizenships": profile.citizenships if profile else [],
        "work_authorizations": list(
            profile.work_authorizations.values(
                "country_code", "authorized", "needs_sponsorship", "authorization_basis"
            )
        )
        if profile
        else [],
        "countries": COUNTRIES,
    }


class AddressSerializer(StrictSerializer):
    street_address = serializers.CharField(max_length=240)
    city = serializers.CharField(max_length=160)
    postal_code = serializers.CharField(max_length=32, allow_blank=True)
    district = serializers.CharField(max_length=160, allow_blank=True)
    region = serializers.CharField(max_length=160, allow_blank=True)
    country_code = serializers.ChoiceField(choices=COUNTRIES)


class AuthorizationSerializer(StrictSerializer):
    country_code = serializers.ChoiceField(choices=COUNTRIES)
    authorized = serializers.BooleanField()
    needs_sponsorship = serializers.BooleanField()
    authorization_basis = serializers.ChoiceField(choices=BASES)


class EligibilitySerializer(StrictSerializer):
    citizenships = serializers.ListField(
        child=serializers.ChoiceField(choices=COUNTRIES),
        max_length=20,
        allow_empty=True,
    )
    work_authorizations = AuthorizationSerializer(many=True, allow_empty=False)

    def validate_work_authorizations(self, value):
        codes = [row["country_code"] for row in value]
        if len(codes) > 30 or len(set(codes)) != len(codes):
            raise serializers.ValidationError("Select up to 30 distinct countries.")
        return value


@api_view(["GET"])
def onboarding(request):
    return Response(state(CandidateProfile.objects.filter(user=request.user).first()))


@api_view(["PUT"])
def address(request):
    serializer = AddressSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    with transaction.atomic():
        profile = locked_profile(request.user)
        if not profile.current_resume_id:
            raise APIError("onboarding_required", "Upload your resume first.", 409)
        for name, value in serializer.validated_data.items():
            setattr(profile, name, value)
        profile.save(update_fields=[*ADDRESS_FIELDS, "updated_at"])
        bump(profile)
        return Response(state(profile))


@api_view(["PUT"])
def eligibility(request):
    serializer = EligibilitySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    with transaction.atomic():
        profile = locked_profile(request.user)
        if next_step(profile) in ("resume", "address"):
            raise APIError(
                "onboarding_required", "Complete your resume and address first.", 409
            )
        data = serializer.validated_data
        codes = [row["country_code"] for row in data["work_authorizations"]]
        profile.work_authorizations.exclude(country_code__in=codes).delete()
        for row in data["work_authorizations"]:
            WorkAuthorization.objects.update_or_create(
                profile=profile,
                country_code=row["country_code"],
                defaults={**row, "confirmed_at": timezone.now()},
            )
        profile.citizenships = list(dict.fromkeys(data["citizenships"]))
        profile.onboarding_completed_at = timezone.now()
        profile.save(
            update_fields=["citizenships", "onboarding_completed_at", "updated_at"]
        )
        bump(profile)
        return Response(state(profile))


urlpatterns = [
    path("onboarding/", onboarding),
    path("onboarding/address/", address),
    path("onboarding/work-eligibility/", eligibility),
]
