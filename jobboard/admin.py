from django.contrib import admin

from . import models as m


class CompanyProfileInline(admin.StackedInline):
    model = m.CompanyProfile
    extra = 0


@admin.register(m.Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "domain",
        "logo_source_kind",
        "logo_fetched_at",
        "logo_last_error",
    )
    search_fields = ("name", "domain")
    readonly_fields = ("logo_source_url", "logo_source_kind", "logo_fetched_at")
    inlines = (CompanyProfileInline,)


@admin.register(m.Role, m.Skill, m.JobDomain, m.JobSubdomain)
class TaxonomyAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(m.Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("name", "country_code", "region", "canonical_key")
    search_fields = ("name", "canonical_key")
    list_filter = ("country_code",)


class OfferLocationInline(admin.TabularInline):
    model = m.OfferLocation
    extra = 0
    autocomplete_fields = ("location",)


class OfferSkillInline(admin.TabularInline):
    model = m.OfferSkill
    extra = 0
    autocomplete_fields = ("skill",)


@admin.register(m.Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "company",
        "contract_type",
        "work_mode",
        "status",
        "job_subdomain",
        "taxonomy_status",
    )
    list_filter = (
        "status",
        "contract_type",
        "work_mode",
        "taxonomy_status",
        "job_subdomain__domain",
    )
    search_fields = ("title", "company__name")
    autocomplete_fields = ("company", "role", "job_subdomain", "secondary_subdomains")
    readonly_fields = (
        "created_at",
        "updated_at",
        "search_vector",
        "search_document",
        "search_title",
        "taxonomy_status",
        "taxonomy_version",
        "taxonomy_input_hash",
        "taxonomy_manual",
        "taxonomy_evidence",
    )
    inlines = (OfferLocationInline, OfferSkillInline)

    def save_model(self, request, obj, form, change):
        from jobboard.services.job_taxonomy import VERSION, input_hash

        if (
            "job_subdomain" in form.changed_data
            or "secondary_subdomains" in form.changed_data
        ):
            obj.taxonomy_manual = True
            obj.taxonomy_status = (
                ("broad" if obj.job_subdomain.generalist else "classified")
                if obj.job_subdomain
                else "unclassified"
            )
            obj.taxonomy_version = VERSION
            obj.taxonomy_input_hash = input_hash(obj)
            obj.taxonomy_evidence = {"method": "manual", "source": "admin"}
        elif (
            change
            and obj.taxonomy_manual
            and obj.taxonomy_input_hash != input_hash(obj)
        ):
            obj.taxonomy_status = "needs_review"
        super().save_model(request, obj, form, change)


class OperationalReadOnlyAdmin(admin.ModelAdmin):
    """Inspection only: admin must not bypass approval and document lifecycle services.

    Private application data is restricted to superusers. Normal staff catalogue
    permissions do not implicitly grant access to resumes, answers or runs.
    """

    actions = None
    list_per_page = 50

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


for model in (
    m.CandidateProfile,
    m.CandidateSkill,
    m.Document,
    m.Experience,
    m.Education,
    m.Project,
    m.WorkAuthorization,
    m.SearchPreference,
    m.PreferenceRole,
    m.PreferenceLocation,
    m.PreferenceContract,
    m.PreferenceWorkMode,
    m.SourceBoard,
    m.ImportRun,
    m.OfferSource,
    m.CompensationBand,
    m.SavedOffer,
    m.Application,
    m.ApplicationRevision,
    m.RevisionDocument,
    m.SubmissionAuthorization,
    m.AgentRun,
    m.ApplicationEvent,
    m.Interview,
    m.ApplicationTask,
    m.OutboxMessage,
    m.DeletionRequest,
):
    admin.site.register(model, OperationalReadOnlyAdmin)


@admin.register(m.OfferEnrichment)
class InternshipReviewAdmin(OperationalReadOnlyAdmin):
    list_display = (
        "offer",
        "classification",
        "review_reason",
        "europe_status",
        "extractor_version",
    )
    list_filter = ("classification", "europe_status")
    search_fields = ("offer__title", "offer__company__name")
    list_select_related = ("offer",)

    @admin.display(description="Motif du classement")
    def review_reason(self, obj):
        reason = obj.facts.get("classification", {}).get("reason", "")
        return {
            "uncorroborated_ats_contract": "Contrat ATS sans confirmation dans le texte",
            "contract_conflict": "Contrat contradictoire",
            "mixed_contract_title": "Stage ou alternance à clarifier",
            "excluded_role_title": "Autre poste ou événement",
            "placement_description": "Stage précisé dans la description",
            "danish_placement_period": "Période de stage précisée en danois",
            "title_and_contract": "Titre et contrat concordants",
        }.get(reason, reason or "—")
