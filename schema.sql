CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    author TEXT,
    normalized_title TEXT NOT NULL,
    normalized_author TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS book_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id),
    event_type TEXT NOT NULL CHECK(event_type IN ('ADDED', 'CHECKED_OUT', 'DELETED')),
    scan_id INTEGER REFERENCES scans(id),
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_path TEXT NOT NULL,
    claude_response TEXT,
    detected_books TEXT,
    books_added TEXT,
    books_removed TEXT,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'confirmed', 'discarded')),
    scanned_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE VIEW IF NOT EXISTS current_inventory AS
SELECT b.*, latest.event_type, latest.created_at AS last_event_at
FROM books b
JOIN (
    SELECT book_id, event_type, created_at,
           ROW_NUMBER() OVER (PARTITION BY book_id ORDER BY created_at DESC) AS rn
    FROM book_events
) latest ON latest.book_id = b.id AND latest.rn = 1
WHERE latest.event_type = 'ADDED';

CREATE VIEW IF NOT EXISTS checked_out_books AS
SELECT b.*, latest.event_type, latest.created_at AS last_event_at
FROM books b
JOIN (
    SELECT book_id, event_type, created_at,
           ROW_NUMBER() OVER (PARTITION BY book_id ORDER BY created_at DESC) AS rn
    FROM book_events
) latest ON latest.book_id = b.id AND latest.rn = 1
WHERE latest.event_type = 'CHECKED_OUT';

CREATE INDEX IF NOT EXISTS idx_book_events_book_id ON book_events(book_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_books_normalized ON books(normalized_title, normalized_author);
