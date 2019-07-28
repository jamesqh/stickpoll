#!/usr/bin/env python3

from db import get_db, query_db
import utils

from datetime import datetime
import hashlib

def add_poll(title, question, choices, close_date, early_results, password,
             email):
    """Add poll question to database and return id of new record.

    Args:
        title (str): Short title for poll.
        question (str): Poll question.
        choices (list of str): Poll answer choices.
        close_date (int): Timestamp of poll's closing time.
        early_results (bool): Whether preview results are available.
        password (str): Password for poll deletion.
        email (str): Email for poll deletion.

    Returns:
        int: Poll id number.
    """
    salt = hashlib.sha1(title.encode("utf-8")
                        + str(close_date).encode("utf-8")).digest()
    token = utils.hash_password(password, salt)
    statement = ("BEGIN; INSERT INTO Questions (title, text, open, "
                 "close_date, early_results, token, email) "
                 "VALUES (?, ?, ?, ?, ?, ?, ?); "
                 "SELECT last_insert_rowid(); COMMIT")
    db = get_db()
    c = db.execute(statement, (title, question, 1, close_date,
                               int(early_results), token, email))
    row = list(c)[0]
    poll_id = row["last_insert_rowid()"]
    statement = ("INSERT INTO Choices (text, question_id, choice_number) "
                 "VALUES (?, ?, ?)")
    db.executemany(statement, [(choice, poll_id, i)
                               for i, choice in enumerate(choices)])
    return poll_id

def get_cookie_hash(cookie_id):
    """Return valid hash for given cookie id."""
    statement = "SELECT hash FROM Cookies WHERE id = ?"
    row = query_db(statement, (cookie_id,), one=True)
    if row is not None:
        return row["hash"]
    else:
        return None

def new_cookie():
    """Insert new blank cookie record and return id."""
    statement = ("BEGIN; INSERT INTO Cookies (hash, last_seen) VALUES (?, ?); "
                 "SELECT last_insert_rowid(); COMMIT")
    db = get_db()
    c = db.execute(statement, ("", 0))
    row = list(c)[0]
    cookie_id = row["last_insert_rowid()"]
    return cookie_id

def get_poll(poll_id):
    """Return database record of given poll question id."""
    statement = "SELECT * FROM Questions WHERE id = ?"
    return query_db(statement, (poll_id,), one=True)

def get_choices(poll_id):
    """Return database records of choices for given poll question id."""
    statement = "SELECT * FROM Choices WHERE question_id = ?"
    return query_db(statement, (poll_id,))

def add_vote(poll_id, ballot_string):
    """Add one vote for given poll question id and ballot string."""
    statement = ("BEGIN; UPDATE Ballots SET count = count + 1 WHERE "
                 "question_id = ? AND ballot_string = ?; SELECT changes(); "
                 "COMMIT")
    db = get_db()
    c = db.execute(statement, (poll_id, ballot_string))
    row = list(c)[0]
    if row["changes()"] == 0:
        statement = ("INSERT INTO Ballots (ballot_string, question_id, count) "
                     "VALUES (?, ?, ?)")
        db.execute(statement, (ballot_string, poll_id, 1))

def update_cookie(cookie_id, cookie_hash, last_seen):
    """Update cookie record.

    Update record for given cookie id with new valid hash and last seen
    timestamp.
    """
    statement = "UPDATE Cookies SET hash = ?, last_seen = ? WHERE id = ?"
    db = get_db()
    db.execute(statement, (cookie_hash, last_seen, cookie_id))

def get_ballots(poll_id):
    """Return votes for given poll question id.

    Returns:
        (dict of int keyed by str): Number of votes for each ballot string
            keyed by the ballot strings.
    """
    statement = "SELECT ballot_string, count FROM Ballots WHERE question_id = ?"
    rows = query_db(statement, (poll_id,))
    ballots = {row["ballot_string"]: row["count"] for row in rows}
    return ballots

def update_results(poll_id, results_json):
    """Update stored results json for given poll question id."""
    statement = ("BEGIN; UPDATE Results SET results_json = ?, last_update = ? "
                 "WHERE question_id = ?; SELECT changes(); COMMIT")
    db = get_db()
    c = db.execute(statement, (results_json,
                               int(datetime.now().timestamp()),
                               poll_id))
    row = list(c)[0]
    if row["changes()"] == 0:
        statement = ("INSERT INTO Results (results_json, last_update, "
                     "question_id)  VALUES (?, ?, ?)")
        db.execute(statement, (results_json,
                               int(datetime.now().timestamp()),
                               poll_id))

def get_results(poll_id):
    """Return results json for given poll question id."""
    statement = "SELECT * FROM Results WHERE question_id = ?"
    return query_db(statement, (poll_id,), one=True)

def close_poll(poll_id):
    """Close poll."""
    statement = "UPDATE Questions SET open = 0 WHERE id = ?"
    db = get_db()
    db.execute(statement, (poll_id,))

def close_expired_polls():
    """Close polls whose closing date has passed. Return IDs of closed polls."""
    statement = ("SELECT id FROM Questions WHERE open = 1 "
                 "AND close_date >= ?")
    rows = query_db(statement, (datetime.now().timestamp(),))
    close_ids = [row["id"] for row in rows]
    db = get_db()
    statement = "UPDATE Questions SET open = 0 WHERE id = ?"
    db.executemany(statement, close_ids)
    return close_ids

def get_open_polls():
    """Return IDs of open polls."""
    statement = "SELECT id FROM Questions WHERE open = 1"
    return query_db(statement)

def get_open_early_results_polls():
    """Return IDs of open early_results polls."""
    statement = "SELECT id FROM Questions WHERE open = 1 and early_results = 1"
    return query_db(statement)

def delete_poll(poll_id):
    """Delete all records related to given poll question id from database."""
    statement = "DELETE FROM Questions WHERE id = ?"
    db = get_db()
    db.execute(statement, (poll_id,))

def search_db(search_string, search_open, search_columns, order_by, order_dir):
    """Search poll question database for some text.

    Args:
        search_string (str): The text to search for.
        search_open (str): Search open polls, closed polls, or both.
            (open/closed/all)
        search_columns (str): Search in poll titles, poll question text,
            or both (title/text/both).
        order_by (str): Order by relevance or closing date (rel/close_date).
        order_dir (str): Ascending or descending order (asc/desc).

    Returns:
        (list of dict): Records from index database matching the query.
    """
    snippet = "snippet(Questions_index, -1, '<b>', '</b>', '...', 10)"
    statement = ("SELECT rowid, title, open, close_date, {0} AS snippet "
                 "FROM Questions_index WHERE Questions_index MATCH ? "
                 ).format(snippet)
    if search_open == "open":
        statement += "AND open = 1 "
    elif search_open == "closed":
        statement += "AND open = 0 "
    statement += "ORDER BY "
    if order_by == "rel":
        statement += "bm25(Questions_index) "
    else:
        statement += "close_date "
    if order_dir == "desc":
        statement += "DESC, "
    else:
        statement += "ASC, "
    statement += "title DESC; "
    if search_columns == "both":
        query = ("title:{0} OR text:{0}".format(search_string),)
    elif search_columns == "title":
        query = ("title:{0}".format(search_string),)
    else:
        query = ("text:{0}".format(search_string),)
    return query_db(statement, query)

def get_recent_polls(number_polls, open_polls):
    statement = ("SELECT * FROM Questions WHERE open = ? "
                 "ORDER BY id DESC LIMIT ?")
    return query_db(statement, (int(open_polls), number_polls))
