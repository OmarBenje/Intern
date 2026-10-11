"""Shared, bounded multilingual search for the catalogue and saved searches."""

import re
import unicodedata
from functools import reduce
from operator import and_, or_

from django.contrib.postgres.search import (
    SearchQuery,
    SearchRank,
    TrigramWordSimilarity,
)
from django.db.models import F, Func, TextField, Value

# Deliberately small, reviewed equivalents; never change the publication boundary.
ALIASES = (
    ("stage", "stages", "internship", "intern", "praktikum", "tirocinio"),
    (
        "développeur",
        "developpeur",
        "développeuse",
        "développeur logiciel",
        "développeuse logiciel",
        "développement logiciel",
        "software development",
        "software developer",
        "software engineer",
        "software engineering",
        "softwareentwicklung",
        "swe",
    ),
    ("science des données", "data science", "data scientist"),
    ("analyse de données", "data analyst", "data analytics"),
    ("apprentissage automatique", "machine learning"),
    ("ressources humaines", "human resources", "personalwesen"),
    ("comptabilité", "comptabilite", "accounting", "buchhaltung"),
    ("chaîne logistique", "supply chain"),
    ("cybersécurité", "cybersecurite", "cybersecurity", "cyber security"),
)


def normalized(value):
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(c)
    )


ALIAS_MAP = {normalized(alias): group for group in ALIASES for alias in group}
MAX_ALIAS_WORDS = max(len(alias.split()) for alias in ALIAS_MAP)


def search_text(text):
    """Use the same database normalizer as the stored document."""
    return Func(
        Value(text), function="intern_search_normalize", output_field=TextField()
    )


def clause(text, search_type="phrase"):
    return SearchQuery(search_text(text), config="simple", search_type=search_type)


class PreparedSearchQuery(SearchQuery):
    """An uncorrelated subquery prepares the tsquery once per SQL expression.

    Otherwise PostgreSQL can repeat normalization/parsing for every ranked row,
    especially with multilingual alternatives. The GIN still accepts this RHS.
    """

    template = "(SELECT %(expressions)s)"


def search_query(text):
    # Explicit web-search operators and quoted phrases retain PostgreSQL semantics.
    if re.search(r'"|(?:^|\s)-\S|\bOR\b', text):
        return clause(text, "websearch")
    words = text.split()
    clauses = []
    offset = 0
    while offset < len(words):
        for size in range(min(MAX_ALIAS_WORDS, len(words) - offset), 0, -1):
            phrase = " ".join(words[offset : offset + size])
            group = ALIAS_MAP.get(normalized(phrase))
            if group:
                clauses.append(
                    reduce(
                        or_,
                        (clause(alias) for alias in group),
                    )
                )
                offset += size
                break
        else:
            clauses.append(clause(words[offset], "plain"))
            offset += 1
    return reduce(and_, clauses) if clauses else clause("", "plain")


def search_offers(queryset, text):
    text = text.strip()
    if not text:
        return queryset
    query = PreparedSearchQuery(search_query(text))
    return queryset.filter(search_document=query).annotate(
        search_rank=SearchRank(
            F("search_document"), query, weights=[0.05, 0.1, 0.2, 1.0], normalization=32
        )
    )


def suggest_offers(queryset, text):
    """Explicit alternatives from an already filtered publication boundary.

    The operator (rather than a similarity-function WHERE) uses the trigram
    index. No correction of quotes, OR or exclusions, and no unbounded list.
    """
    text = text.strip()
    if (
        not 3 <= len(text) <= 100
        or len(text.split()) > 8
        or sum(character.isalnum() for character in text) < 3
        or re.search(r'"|(?:^|\s)-\S|\bOR\b', text)
    ):
        return []
    candidates = (
        queryset.filter(search_title__trigram_word_similar=search_text(text))
        .annotate(similarity=TrigramWordSimilarity(search_text(text), "search_title"))
        .order_by("-similarity", F("published_at").desc(nulls_last=True), "-id")
        .values("title", "search_title")[:12]
    )
    suggestions, seen = [], set()
    for item in candidates:
        if item["search_title"] in seen:
            continue
        seen.add(item["search_title"])
        suggestions.append({"query": item["title"]})
        if len(suggestions) == 3:
            break
    return suggestions
