import re

from rapidfuzz import fuzz, process

MATCH_THRESHOLD = 80
AMBIGUOUS_THRESHOLD = 55


def normalize(text):
    """Lowercase, collapse whitespace, strip punctuation."""
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def match_detected_to_inventory(detected_books, inventory):
    """
    Compare Claude's detected books against current inventory.

    Args:
        detected_books: list of dicts from Claude {title, author, ...}
        inventory: list of sqlite3.Row from current_inventory view

    Returns dict with keys: matched, new, ambiguous, missing
    """
    inventory_map = {row["id"]: row for row in inventory}
    inventory_titles = {row["id"]: row["normalized_title"] for row in inventory}

    matched = []  # (detected_book, inventory_id, score)
    new_books = []  # detected books with no match
    ambiguous = []  # (detected_book, inventory_id, score)
    matched_inventory_ids = set()

    for det in detected_books:
        det_title = det.get("title", "")
        det_normalized = normalize(det_title)

        if not det_normalized or det_normalized.startswith("unknown"):
            new_books.append(det)
            continue

        if not inventory_titles:
            new_books.append(det)
            continue

        result = process.extractOne(
            det_normalized,
            inventory_titles,
            scorer=fuzz.token_sort_ratio,
            score_cutoff=AMBIGUOUS_THRESHOLD,
        )

        if result is None:
            new_books.append(det)
        elif result[1] >= MATCH_THRESHOLD:
            inv_id = result[2]
            matched.append((det, inv_id, result[1]))
            matched_inventory_ids.add(inv_id)
        else:
            inv_id = result[2]
            ambiguous.append((det, inv_id, result[1]))

    missing = [
        dict(row) for row in inventory if row["id"] not in matched_inventory_ids
    ]

    return {
        "matched": matched,
        "new": new_books,
        "ambiguous": ambiguous,
        "missing": missing,
    }
