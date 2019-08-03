"""Blueprint for search page."""

from flask import Blueprint, flash, render_template, request

import bleach

from apsw import SQLError
from forms import SearchForm
import db_funcs

bp = Blueprint("search", __name__, url_prefix="/search")

@bp.route("/", methods=("GET", "POST"))
def search_page():
    """View function for search page."""
    form = SearchForm()
    if request.method == "GET":
        return render_template("search.html", form=form)
    search_string = form.search_string.data
    search_open = form.search_open.data
    search_columns = form.search_columns.data
    order_by = form.order_by.data
    order_dir = form.order_dir.data
    try:
        search_results = db_funcs.search_db(search_string, search_open,
                                            search_columns, order_by, order_dir)
    except SQLError:
        flash("Invalid query text")
        return render_template("search.html", form=form)
    for row in search_results:
        row["snippet"] = bleach.clean(row["snippet"], tags=["b"])
    return render_template("search_results.html", search_results=search_results)
