import os
import sqlite3

from flask import g

import config


def get_db():
    if "db" not in g:
        os.makedirs(os.path.dirname(config.DATABASE_PATH), exist_ok=True)
        g.db = sqlite3.connect(config.DATABASE_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create tables from schema.sql."""
    os.makedirs(os.path.dirname(config.DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DATABASE_PATH)
    with open(os.path.join(os.path.dirname(__file__), "schema.sql")) as f:
        conn.executescript(f.read())
    conn.close()


def get_current_inventory():
    db = get_db()
    return db.execute(
        "SELECT * FROM current_inventory ORDER BY last_event_at DESC, title ASC"
    ).fetchall()


def get_book(book_id):
    db = get_db()
    return db.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()


def get_book_events(book_id):
    db = get_db()
    return db.execute(
        "SELECT be.*, s.photo_path FROM book_events be "
        "LEFT JOIN scans s ON be.scan_id = s.id "
        "WHERE be.book_id = ? ORDER BY be.created_at DESC",
        (book_id,),
    ).fetchall()


def get_all_events(limit=50, offset=0):
    db = get_db()
    return db.execute(
        "SELECT be.*, b.title, b.author FROM book_events be "
        "JOIN books b ON be.book_id = b.id "
        "WHERE be.event_type IN ('ADDED', 'CHECKED_OUT') "
        "ORDER BY be.created_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()


def get_unique_books_count():
    db = get_db()
    return db.execute("SELECT COUNT(*) FROM books").fetchone()[0]


def get_all_books_normalized():
    """Get all books with their normalized fields for matching."""
    db = get_db()
    return db.execute(
        "SELECT id, title, author, normalized_title, normalized_author FROM books"
    ).fetchall()


def create_scan(photo_path, scanned_by):
    db = get_db()
    cursor = db.execute(
        "INSERT INTO scans (photo_path, scanned_by) VALUES (?, ?)",
        (photo_path, scanned_by),
    )
    db.commit()
    return cursor.lastrowid


def update_scan(scan_id, claude_response, detected_books, status="pending"):
    db = get_db()
    db.execute(
        "UPDATE scans SET claude_response = ?, detected_books = ?, status = ? WHERE id = ?",
        (claude_response, detected_books, status, scan_id),
    )
    db.commit()


def confirm_scan(scan_id, added_book_ids, removed_book_ids):
    db = get_db()
    db.execute(
        "UPDATE scans SET books_added = ?, books_removed = ?, status = 'confirmed' WHERE id = ?",
        (str(added_book_ids), str(removed_book_ids), scan_id),
    )
    db.commit()


def add_book(title, author, normalized_title, normalized_author, scan_id, created_by):
    db = get_db()
    cursor = db.execute(
        "INSERT INTO books (title, author, normalized_title, normalized_author) VALUES (?, ?, ?, ?)",
        (title, author, normalized_title, normalized_author),
    )
    book_id = cursor.lastrowid
    db.execute(
        "INSERT INTO book_events (book_id, event_type, scan_id, created_by) VALUES (?, 'ADDED', ?, ?)",
        (book_id, scan_id, created_by),
    )
    db.commit()
    return book_id


def add_book_manual(title, author, normalized_title, normalized_author, created_by):
    """Add a book without a scan."""
    db = get_db()
    cursor = db.execute(
        "INSERT INTO books (title, author, normalized_title, normalized_author) VALUES (?, ?, ?, ?)",
        (title, author, normalized_title, normalized_author),
    )
    book_id = cursor.lastrowid
    db.execute(
        "INSERT INTO book_events (book_id, event_type, created_by) VALUES (?, 'ADDED', ?)",
        (book_id, created_by),
    )
    db.commit()
    return book_id


def checkout_book(book_id, created_by):
    """Mark a book as checked out (taken by a neighbor)."""
    db = get_db()
    db.execute(
        "INSERT INTO book_events (book_id, event_type, created_by) VALUES (?, 'CHECKED_OUT', ?)",
        (book_id, created_by),
    )
    db.commit()


def delete_book(book_id, created_by):
    """Permanently remove a book and all its records."""
    db = get_db()
    db.execute("DELETE FROM book_events WHERE book_id = ?", (book_id,))
    db.execute("DELETE FROM books WHERE id = ?", (book_id,))
    db.commit()


def update_book(book_id, title, author, added_date):
    """Update a book's fields."""
    from matcher import normalize
    db = get_db()
    db.execute(
        "UPDATE books SET title = ?, author = ?, normalized_title = ?, normalized_author = ? WHERE id = ?",
        (title, author, normalize(title), normalize(author or ""), book_id),
    )
    # Update the ADDED event timestamp if the user changed the date
    if added_date:
        timestamp = added_date + " 00:00:00" if len(added_date) == 10 else added_date
        db.execute(
            "UPDATE book_events SET created_at = ? "
            "WHERE id = (SELECT id FROM book_events WHERE book_id = ? AND event_type = 'ADDED' ORDER BY created_at ASC LIMIT 1)",
            (timestamp, book_id),
        )
    db.commit()


def get_checked_out_books():
    db = get_db()
    return db.execute("SELECT * FROM checked_out_books ORDER BY last_event_at DESC").fetchall()


def record_event(book_id, event_type, scan_id, created_by):
    db = get_db()
    db.execute(
        "INSERT INTO book_events (book_id, event_type, scan_id, created_by) VALUES (?, ?, ?, ?)",
        (book_id, event_type, scan_id, created_by),
    )
    db.commit()


def get_stats():
    db = get_db()
    total_books = db.execute("SELECT COUNT(*) FROM books").fetchone()[0]
    current_count = db.execute("SELECT COUNT(*) FROM current_inventory").fetchone()[0]
    total_removed = db.execute(
        "SELECT COUNT(DISTINCT book_id) FROM book_events WHERE event_type = 'CHECKED_OUT'"
    ).fetchone()[0]
    total_scans = db.execute(
        "SELECT COUNT(*) FROM scans WHERE status = 'confirmed'"
    ).fetchone()[0]
    return {
        "total_books": total_books,
        "current_count": current_count,
        "books_served": total_removed,
        "total_scans": total_scans,
    }
