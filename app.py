#!/usr/bin/env python3

import logging, os
import logging.handlers

from flask import (Flask, has_request_context, redirect, render_template,
                   url_for, request)

import db, db_funcs, mail, polls, search

app = Flask(__name__, instance_relative_config=True)

class DefaultConfig:
    SECRET_KEY="placeholder_key"
    DATABASE=os.path.join(app.instance_path, "stickpoll.sqlite")
    TEMPLATES_AUTO_RELOAD=True
    ALLOW_REPEAT_VOTES=False
    SENDGRID_API_KEY="placeholder_key"
    SENDGRID_DEFAULT_FROM="noreply@stickpoll.com"
    UPDATE_INTERVAL=60

app.config.from_object(DefaultConfig)
app.config.from_pyfile("config.cfg", silent=True)

try:
    os.makedirs(app.instance_path)
except OSError:
    pass

class RequestFormatter(logging.Formatter):
    def format(self, record):
        if has_request_context():
            record.url = request.url
            record.remote_addr = request.remote_addr
        else:
            record.url = None
            record.remote_addr = None
        return super().format(record)

if not app.config["DEBUG"] or True:
    try:
        os.makedirs(os.path.join(app.instance_path, "logs"))
    except OSError:
        pass
    file_handler = logging.handlers.RotatingFileHandler(
        os.path.join(app.instance_path, "logs", "stickpoll.log"),
        maxBytes=10240,
        backupCount=10)
    file_handler.setFormatter(RequestFormatter(
        '[%(asctime)s] %(remote_addr)s requested %(url)s\n'
        '%(levelname)s in %(module)s: %(message)s'))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info("Startup")

db.init_app(app)

app.register_blueprint(polls.bp)
app.register_blueprint(search.bp)

@app.route("/")
def home():
    # Fetch the most recent 20 polls open and closed polls
    open_polls = db_funcs.get_recent_polls(20, True)
    closed_polls = db_funcs.get_recent_polls(20, False)
    return render_template("index.html", open_polls=open_polls,
                           closed_polls=closed_polls)

@app.route("/about")
def about():
    return render_template("about.html")

@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(500)
def internal_server_error(e):
    app.logger.error("Error 500")
    return render_template("500.html"), 500
