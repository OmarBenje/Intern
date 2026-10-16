# Company logos

New companies are automatically eligible for logo extraction. The catalogue worker
checks up to five due companies per cycle, before collecting offers. Downloads run
outside database transactions; a ten-minute lease prevents duplicate work. Failed
attempts retry after 10 minutes, 20 minutes, etc., capped at seven days. Successful
logos are reused, including when new offers reference the same company.

The extractor uses a company's website or registered recruitment pages. It recognizes
employer logos in page images and Ashby branding metadata, and uses icons only on
employer sites (never the generic icon of an ATS). It does not guess a company domain
from its name. A company without a usable source keeps its initial until extraction
succeeds. `logo_last_error`, `logo_attempts`, and `logo_next_attempt_at` expose status.

Employer domains are recorded independently of image downloads. A known website,
matching JobSpy/WTTJ `company_website`, a matching structured organization, or a
successful read of the employer's own page can establish the domain even when no
logo is found. Conflicting source websites remain unresolved, and existing valid
identities are preserved. HTTPS platform domains are excluded from this identity.

Downloaded raster images are size-limited, decoded and re-encoded as PNG, stored using
`PRIVATE_STORAGE_BACKEND`, and served through authenticated `/api/v1/companies/<id>/logo/`.
Every network hop validates HTTPS and public DNS and pins the resolved address.
SVG and HTML are not served as logos. Browser requests never trigger remote fetching.

## Running

The Compose `catalogue-worker` already consumes logos when the `app` profile runs.
For local development without the full catalogue worker:

```sh
uv run --project metier metier/app/manage.py migrate
uv run --project metier metier/app/manage.py run_company_logo_worker
```

Keep a worker running for automatic extraction. Both workers can run together safely.
A one-off backfill and an explicit verified source are also available:

```sh
uv run --project metier metier/app/manage.py extract_company_logos
uv run --project metier metier/app/manage.py extract_company_logos --company-id 1 --page-url https://example.com
uv run --project metier metier/app/manage.py extract_company_logos --company-id 1 --image-url https://example.com/logo.png
```

Backfill missing domains, including companies that already have a cached logo:

```sh
# Only use existing websites and source metadata; no HTTP requests.
uv run --project metier metier/app/manage.py enrich_company_domains --metadata-only --limit 500
# Read registered public pages for one bounded batch.
uv run --project metier metier/app/manage.py enrich_company_domains --limit 25
# Resume after the last company ID reported by the previous batch.
uv run --project metier metier/app/manage.py enrich_company_domains --after-id 123 --limit 25
```

Public reads use the same HTTPS/DNS protections as logo extraction, with at most
five pages and 45 seconds per company. The domain command never downloads logos
or modifies their cache and retry state. An unresolved identity remains empty.

## Optional Logo.dev fallback

Set `VITE_LOGO_DEV_PUBLISHABLE_KEY` to a publishable `pk_` key in
`frontend/.env.local` for local Vite, or in the root `.env.production` for
the VPS deployment. Docker passes this value as a frontend build argument.
It is embedded in the browser bundle; a secret API key is not accepted.

```sh
docker compose --env-file .env.production -f deploy/compose.yaml build frontend
docker compose --env-file .env.production -f deploy/compose.yaml up -d --no-deps frontend
```

Rebuilding is required after changing the key. With an empty key, the CDN fallback
and its attribution are disabled. With a publishable key, company images use the
local logo first, then Logo.dev for a known employer domain, then initials. The
public login page and the workspace display a link to Logo.dev. If the key has
allowed-domain restrictions, include the VPS hostname and local development host.

The existing 17 companies were backfilled on 2026-09-30 from their registered employer
pages or official websites. Fallback pages included Stripe, Nelly, Doctolib, Aircall,
Human Rights Watch, Maven Securities and Ubisoft. No logo API subscription is needed.
