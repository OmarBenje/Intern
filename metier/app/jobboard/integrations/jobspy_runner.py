"""Isolated, killable JobSpy process. Invoked by jobspy_catalogue only."""

import json
import sys


class UpstreamError(Exception):
    def __init__(self, code, retry_after=None):
        self.code, self.retry_after = code, retry_after


def observe_indeed_response(response):
    if response.status_code != 200:
        retry = response.headers.get("Retry-After", "")
        raise UpstreamError(
            "jobspy_rate_limited"
            if response.status_code == 429
            else "jobspy_upstream_http_error",
            int(retry) if retry.isdigit() else None,
        )
    try:
        data = response.json()
        if data.get("errors"):
            raise ValueError()
        search = data["data"]["jobSearch"]
        if not isinstance(search["results"], list) or not isinstance(
            search["pageInfo"], dict
        ):
            raise TypeError()
        return not search["results"] and not search["pageInfo"].get("nextCursor")
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise UpstreamError("jobspy_upstream_invalid_response") from exc


def main():
    from jobspy.glassdoor import Glassdoor
    from jobspy.indeed import Indeed
    from jobspy.linkedin import LinkedIn
    from jobspy.model import Country, DescriptionFormat, JobType, ScraperInput, Site

    options = json.load(sys.stdin)
    site = options["site"]
    adapter = {"linkedin": LinkedIn, "indeed": Indeed, "glassdoor": Glassdoor}[site]()
    empty_confirmed = False
    if site == "indeed":
        post = adapter.session.post

        def observed_post(*args, **kwargs):
            nonlocal empty_confirmed
            response = post(*args, **kwargs)
            empty_confirmed = observe_indeed_response(response)
            return response

        adapter.session.post = observed_post
    result = adapter.scrape(
        ScraperInput(
            site_type=[Site(site)],
            search_term=options["term"],
            location=options["location"],
            country=Country.from_string(options["country_name"]),
            job_type=JobType.INTERNSHIP,
            results_wanted=options["limit"],
            offset=options["offset"],
            hours_old=None,
            fetch_description=True,
            linkedin_fetch_description=True,
            description_format=DescriptionFormat.PLAIN,
            request_timeout=15,
        )
    )
    rows = []
    for job in result.jobs[: options["limit"]]:
        location = job.location
        country = location.country if location else None
        if isinstance(country, Country):
            country = country.value[0].split(",")[0]
        rows.append(
            {
                "id": job.id,
                "title": job.title,
                "company": job.company_name,
                "company_logo": job.company_logo,
                "company_website": job.company_url_direct,
                "url": job.job_url,
                "direct_url": job.job_url_direct,
                "description": job.description,
                "location": location.display_location() if location else "",
                "country": country or "",
                "job_types": [t.value[0] for t in job.job_type or []],
                "remote": job.is_remote is True,
                "date_posted": job.date_posted.isoformat() if job.date_posted else None,
            }
        )
    print(
        json.dumps(
            {"rows": rows, "empty_confirmed": empty_confirmed}
            if site == "indeed"
            else rows,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except UpstreamError as exc:
        print(json.dumps({"error": exc.code, "retry_after": exc.retry_after}))
