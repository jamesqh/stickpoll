#!/usr/bin/env python3

import apsw

import click
from flask import current_app, g
from flask.cli import with_appcontext

def get_db():
    """Get cursor from database connection, opening a new one if necessary."""
    def row_factory(cursor, row):
        return {k[0]: row[i] for i, k in enumerate(cursor.getdescription())}
    if "db" not in g:
        g.db = apsw.Connection(
            current_app.config["DATABASE"]
            )
        g.db.setrowtrace(row_factory)
        g.db.cursor().execute("PRAGMA foreign_keys = ON")
    return g.db.cursor()

def close_db(e=None):
    """Close database connection, if open."""
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    """Execute main database schema."""
    db = get_db()
    with current_app.open_resource("schema.sql") as f:
        db.execute(f.read().decode("utf-8"))

def init_index_db():
    """Execute index database schema, for text search."""
    db = get_db()
    with current_app.open_resource("schema_index.sql") as f:
        db.execute(f.read().decode("utf-8"))
    db.execute("INSERT INTO Questions_index "
               "(rowid, title, text, open, close_date) "
               "SELECT id, title, text, open, close_date FROM Questions")

def query_db(query, args=(), one=False):
    """Run query against database, returning list() results from cursor."""
    cur = get_db().execute(query, args)
    rv = list(cur)
    cur.close()
    return (rv[0] if rv else None) if one else rv

@click.command("init-db")
@with_appcontext
def init_db_command():
    """Clear the existing data and create new tables."""
    init_db()
    click.echo("Initialized the database.")

@click.command("setup-index-db")
@with_appcontext
def init_index_db_command():
    """Clear and recreate search index table and triggers."""
    init_index_db()
    click.echo("Initialized search index table.")

@click.command("debug-db")
@with_appcontext
def debug_db_command():
    db = get_db()
    from pdb import set_trace
    set_trace()

@click.command("open-all-polls")
@with_appcontext
def open_all_polls_command():
    db = get_db()
    from datetime import datetime
    db.execute("UPDATE Questions SET open = 1, close_date = ?",
               (int(datetime.now().timestamp())+60*60*24*7,))

def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(init_index_db_command)
    app.cli.add_command(debug_db_command)
    app.cli.add_command(open_all_polls_command)
