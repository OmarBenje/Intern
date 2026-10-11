from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import migrations, models

SEARCH_SQL = r"""
CREATE OR REPLACE FUNCTION intern_search_normalize(value text)
RETURNS text LANGUAGE sql STABLE STRICT AS $$
    SELECT regexp_replace(
        regexp_replace(
            regexp_replace(lower(unaccent(value)), '\mc\+\+', 'cpp', 'g'),
            '\mc#', 'csharp', 'g'
        ), '\.net\M', ' dotnet', 'g'
    );
$$;

CREATE OR REPLACE FUNCTION intern_offer_search_update()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE company_name text;
BEGIN
    SELECT name INTO company_name FROM jobboard_company WHERE id = NEW.company_id;
    NEW.search_title := intern_search_normalize(NEW.title);
    NEW.search_document :=
        setweight(to_tsvector('simple', NEW.search_title), 'A') ||
        setweight(to_tsvector('simple', intern_search_normalize(coalesce(company_name, ''))), 'A') ||
        setweight(to_tsvector('simple', intern_search_normalize(coalesce(NEW.description, ''))), 'C');
    RETURN NEW;
END;
$$;

CREATE TRIGGER intern_offer_search_trigger
BEFORE INSERT OR UPDATE OF title, description, company_id, search_document, search_title
ON jobboard_offer FOR EACH ROW EXECUTE FUNCTION intern_offer_search_update();

CREATE OR REPLACE FUNCTION intern_company_search_update()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    UPDATE jobboard_offer SET title = title WHERE company_id = NEW.id;
    RETURN NEW;
END;
$$;

CREATE TRIGGER intern_company_search_trigger
AFTER UPDATE OF name ON jobboard_company FOR EACH ROW
WHEN (OLD.name IS DISTINCT FROM NEW.name)
EXECUTE FUNCTION intern_company_search_update();

UPDATE jobboard_offer SET title = title;
"""

REVERSE_SQL = """
DROP TRIGGER IF EXISTS intern_company_search_trigger ON jobboard_company;
DROP TRIGGER IF EXISTS intern_offer_search_trigger ON jobboard_offer;
DROP FUNCTION IF EXISTS intern_company_search_update();
DROP FUNCTION IF EXISTS intern_offer_search_update();
DROP FUNCTION IF EXISTS intern_search_normalize(text);
"""


class Migration(migrations.Migration):
    dependencies = [("jobboard", "0024_offer_content")]

    operations = [
        # Shared extensions deliberately survive rollback of this migration.
        migrations.RunSQL(
            "CREATE EXTENSION IF NOT EXISTS unaccent", migrations.RunSQL.noop
        ),
        migrations.RunSQL(
            "CREATE EXTENSION IF NOT EXISTS pg_trgm", migrations.RunSQL.noop
        ),
        migrations.AddField(
            model_name="offer",
            name="search_document",
            field=SearchVectorField(editable=False, null=True),
        ),
        migrations.AddField(
            model_name="offer",
            name="search_title",
            field=models.TextField(default="", editable=False),
        ),
        migrations.RunSQL(SEARCH_SQL, REVERSE_SQL),
        migrations.AddIndex(
            model_name="offer",
            index=GinIndex(fields=["search_document"], name="offer_document_idx"),
        ),
        migrations.AddIndex(
            model_name="offer",
            index=GinIndex(
                fields=["search_title"],
                opclasses=["gin_trgm_ops"],
                name="offer_title_trgm_idx",
            ),
        ),
    ]
