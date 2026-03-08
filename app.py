import json
import os
from datetime import datetime

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

import config
import db
from auth import login_required
from matcher import match_detected_to_inventory, normalize
from scanner import scan_shelf_photo

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max upload

app.teardown_appcontext(db.close_db)


@app.template_filter("todatetime")
def todatetime_filter(s):
    """Convert SQLite timestamp string to datetime."""
    if isinstance(s, datetime):
        return s
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except (ValueError, TypeError):
            continue
    return datetime.utcnow()


@app.template_filter("timeago")
def timeago_filter(s):
    """Convert timestamp to human-readable relative time."""
    dt = todatetime_filter(s)
    diff = datetime.utcnow() - dt
    seconds = int(diff.total_seconds())
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days < 30:
        return f"{days}d ago"
    months = days // 30
    return f"{months}mo ago"



@app.route("/")
@login_required
def inventory():
    books = db.get_current_inventory()
    stats = db.get_stats()
    now = datetime.utcnow()
    return render_template("inventory.html", books=books, stats=stats, now=now)


@app.route("/add", methods=["POST"])
@login_required
def add_book_manual():
    title = request.form.get("title", "").strip()
    author = request.form.get("author", "").strip() or None
    if not title:
        flash("Title is required.")
        return redirect(url_for("inventory"))
    db.add_book_manual(
        title, author, normalize(title), normalize(author or ""),
        "user",
    )
    flash(f"Added \"{title}\".")
    return redirect(url_for("inventory"))


@app.route("/book/<int:book_id>/checkout", methods=["POST"])
@login_required
def checkout_book(book_id):
    book = db.get_book(book_id)
    if not book:
        flash("Book not found.")
        return redirect(url_for("inventory"))
    db.checkout_book(book_id, "user")
    flash(f"Checked out \"{book['title']}\".")
    return redirect(url_for("inventory"))


@app.route("/book/<int:book_id>/delete", methods=["POST"])
@login_required
def delete_book(book_id):
    book = db.get_book(book_id)
    if not book:
        flash("Book not found.")
        return redirect(url_for("inventory"))
    db.delete_book(book_id, "user")
    flash(f"Deleted \"{book['title']}\".")
    return redirect(url_for("inventory"))


@app.route("/book/<int:book_id>/edit", methods=["POST"])
@login_required
def edit_book(book_id):
    book = db.get_book(book_id)
    if not book:
        flash("Book not found.")
        return redirect(url_for("inventory"))
    title = request.form.get("title", "").strip()
    author = request.form.get("author", "").strip() or None
    added_date = request.form.get("added_date", "").strip() or None
    if not title:
        flash("Title is required.")
        return redirect(url_for("book_detail", book_id=book_id))
    db.update_book(book_id, title, author, added_date)
    flash("Book updated.")
    return redirect(url_for("book_detail", book_id=book_id))


@app.route("/scan", methods=["GET", "POST"])
@login_required
def scan():
    if request.method == "GET":
        return render_template("scan.html")

    file = request.files.get("photo")
    if not file or not file.filename:
        flash("Please take or upload a photo.")
        return redirect(url_for("scan"))

    os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    ext = secure_filename(file.filename).rsplit(".", 1)[-1] if "." in file.filename else "jpg"
    filename = f"scan_{timestamp}.{ext}"
    filepath = os.path.join(config.UPLOAD_FOLDER, filename)
    file.save(filepath)

    scan_id = db.create_scan(filename, "user")

    try:
        detected, raw_response = scan_shelf_photo(filepath)
    except Exception as e:
        flash(f"Error scanning photo: {e}")
        return redirect(url_for("scan"))

    db.update_scan(scan_id, raw_response, json.dumps(detected))

    current = db.get_current_inventory()
    results = match_detected_to_inventory(detected, current)

    session["pending_scan"] = {
        "scan_id": scan_id,
        "results": {
            "matched": [
                {"detected": d, "inventory_id": inv_id, "score": s}
                for d, inv_id, s in results["matched"]
            ],
            "new": results["new"],
            "ambiguous": [
                {"detected": d, "inventory_id": inv_id, "score": s}
                for d, inv_id, s in results["ambiguous"]
            ],
            "missing": results["missing"],
        },
    }

    return redirect(url_for("scan_results", scan_id=scan_id))


@app.route("/scan/<int:scan_id>/results")
@login_required
def scan_results(scan_id):
    pending = session.get("pending_scan")
    if not pending or pending["scan_id"] != scan_id:
        flash("Scan results expired. Please scan again.")
        return redirect(url_for("scan"))

    results = pending["results"]

    # Resolve inventory book details for matched/ambiguous/missing
    matched_books = []
    for m in results["matched"]:
        book = db.get_book(m["inventory_id"])
        if book:
            matched_books.append({"detected": m["detected"], "book": dict(book), "score": m["score"]})

    ambiguous_books = []
    for a in results["ambiguous"]:
        book = db.get_book(a["inventory_id"])
        if book:
            ambiguous_books.append({"detected": a["detected"], "book": dict(book), "score": a["score"]})

    return render_template(
        "scan_results.html",
        scan_id=scan_id,
        matched=matched_books,
        new_books=results["new"],
        ambiguous=ambiguous_books,
        missing=results["missing"],
    )


@app.route("/scan/<int:scan_id>/confirm", methods=["POST"])
@login_required
def confirm_scan(scan_id):
    pending = session.get("pending_scan")
    if not pending or pending["scan_id"] != scan_id:
        flash("Scan results expired.")
        return redirect(url_for("scan"))

    added_ids = []
    removed_ids = []

    # Process new books that were checked
    new_books = json.loads(request.form.get("new_books_data", "[]"))
    for i, book_data in enumerate(new_books):
        checkbox = request.form.get(f"add_new_{i}")
        if checkbox:
            title = request.form.get(f"new_title_{i}", book_data.get("title", ""))
            author = request.form.get(f"new_author_{i}", book_data.get("author"))
            book_id = db.add_book(
                title, author, normalize(title), normalize(author or ""),
                scan_id, "user",
            )
            added_ids.append(book_id)

    # Process ambiguous books — user decides if they're new or matched
    ambiguous_data = json.loads(request.form.get("ambiguous_data", "[]"))
    for i, amb in enumerate(ambiguous_data):
        action = request.form.get(f"ambiguous_action_{i}")
        if action == "match":
            pass  # It's already in the library, no event needed
        elif action == "new":
            title = request.form.get(f"amb_title_{i}", amb["detected"].get("title", ""))
            author = request.form.get(f"amb_author_{i}", amb["detected"].get("author"))
            book_id = db.add_book(
                title, author, normalize(title), normalize(author or ""),
                scan_id, "user",
            )
            added_ids.append(book_id)

    # Process removals that were checked
    missing_data = json.loads(request.form.get("missing_data", "[]"))
    for i, book_data in enumerate(missing_data):
        checkbox = request.form.get(f"remove_{i}")
        if checkbox:
            book_id = book_data["id"]
            db.record_event(book_id, "CHECKED_OUT", scan_id, "user")
            removed_ids.append(book_id)

    db.confirm_scan(scan_id, added_ids, removed_ids)
    session.pop("pending_scan", None)

    flash(f"Scan confirmed! {len(added_ids)} added, {len(removed_ids)} removed.")
    return redirect(url_for("inventory"))


@app.route("/scan/<int:scan_id>/discard", methods=["POST"])
@login_required
def discard_scan(scan_id):
    db.update_scan(scan_id, None, None, status="discarded")
    session.pop("pending_scan", None)
    flash("Scan discarded.")
    return redirect(url_for("inventory"))


@app.route("/history")
@login_required
def history():
    page = request.args.get("page", 1, type=int)
    per_page = 30
    events = db.get_all_events(limit=per_page, offset=(page - 1) * per_page)
    unique_books = db.get_unique_books_count()
    return render_template("history.html", events=events, page=page, per_page=per_page, unique_books=unique_books)


@app.route("/book/<int:book_id>")
@login_required
def book_detail(book_id):
    book = db.get_book(book_id)
    if not book:
        flash("Book not found.")
        return redirect(url_for("inventory"))
    events = db.get_book_events(book_id)
    # Find the earliest ADDED event date for the edit form
    added_event = None
    for e in reversed(events):
        if e["event_type"] == "ADDED":
            added_event = e
            break
    return render_template("book_detail.html", book=book, events=events, added_event=added_event)


@app.route("/sw.js")
def service_worker():
    return app.send_static_file("sw.js"), 200, {"Content-Type": "application/javascript"}


# Initialize DB on first request
with app.app_context():
    db.init_db()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5151)
