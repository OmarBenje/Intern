from django.contrib import admin
from django.urls import include, path
from jobboard.api.health import live, ready

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("jobboard.api.auth")),
    path("api/v1/recruiter/", include("jobboard.api.recruiters")),
    path("api/v1/", include("jobboard.api.onboarding")),
    path("api/v1/", include("jobboard.api.catalogue")),
    path("api/v1/", include("jobboard.api.taxonomy")),
    path("api/v1/", include("jobboard.api.engine")),
    path("api/v1/", include("jobboard.api.dashboard")),
    path("api/v1/", include("jobboard.api.company_logos")),
    path("api/v1/", include("jobboard.api.companies")),
    path("api/v1/", include("jobboard.api.profiles")),
    path("api/v1/", include("jobboard.api.applications")),
    path("api/v1/", include("jobboard.api.accounts")),
    path("health/live/", live),
    path("health/ready/", ready),
]
handler404 = "jobboard.api.core.not_found"
handler500 = "jobboard.api.core.server_error"
