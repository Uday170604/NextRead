"""Optional external data source: Open Library search API (https://openlibrary.org/dev/docs/api/search)."""
import httpx

SEARCH_URL = "https://openlibrary.org/search.json"


class ExternalSourceError(Exception):
    pass


def search_openlibrary(query: str, limit: int = 10) -> list[dict]:
    """Return books as dicts shaped like BookCreate. Raises ExternalSourceError on failure."""
    try:
        resp = httpx.get(
            SEARCH_URL,
            params={"q": query, "limit": limit,
                    "fields": "title,author_name,first_publish_year,subject,first_sentence"},
            timeout=10.0,
        )
        resp.raise_for_status()
        docs = resp.json().get("docs", [])
    except (httpx.HTTPError, ValueError) as exc:
        raise ExternalSourceError(f"Open Library request failed: {exc}") from exc

    books = []
    for d in docs:
        if not d.get("title") or not d.get("author_name"):
            continue
        sentence = d.get("first_sentence")
        if isinstance(sentence, list):
            sentence = sentence[0] if sentence else None
        subjects = [s for s in d.get("subject", []) if len(s) < 40][:3] or ["General"]
        books.append({
            "title": d["title"][:300],
            "description": (sentence or f"Imported from Open Library: {d['title']}")[:5000],
            "publication_year": d.get("first_publish_year"),
            "author_names": d["author_name"][:3],
            "genre_names": subjects,
        })
    return books
