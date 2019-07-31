#!/usr/bin/env python3

from flask import (abort, Blueprint, current_app, flash, g, make_response,
                   redirect, render_template, request, session, url_for)

from db import get_db, query_db
import db_funcs
from forms import (EnterPasswordForm, EnterPasswordFormWithCaptcha,
                   NewPollForm, NewPollFormWithCaptcha, VoteForm,
                   VoteFormWithCaptcha, CaptchaOnlyForm)
from mail import send_mail
import utils

import binascii
from collections import defaultdict
from datetime import datetime, timedelta
import hashlib
import hmac
import json
import os
import random

bp = Blueprint("polls", __name__, url_prefix="/polls")

time_diffs = {"hour": timedelta(hours=1),
              "day": timedelta(days=1),
              "week": timedelta(days=7),
              "month": timedelta(days=30)}


@bp.route("/new", methods=("GET", "POST"))
def new_poll():
    if utils.valid_session(session):
        # Looks like a normal user; we won't bother them.
        form = NewPollForm()
    else:
        # Check they're human.
        form = NewPollFormWithCaptcha()
    # No further logic necessary for GET requests.
    if request.method == "GET":
        return render_template("new_poll.html", form=form)
    # It's a POST: check the form
    if not form.validate_on_submit():
        for error_field, errors in form.errors.items():
            for error in errors:
                flash("{0}: {1}".format(error_field, error))
        return render_template("new_poll.html", form=form)
    title = form.title.data
    question = form.question.data
    # Make sure we only pay attention to non-empty choice inputs.
    choices = [field.data for field in form.choices if field.data.strip() != ""]
    if len(choices) < 2:
        flash("You must offer at least two non-empty choices")
        return render_template("new_poll.html", form=form)
    email = form.email.data
    # Calculate poll closing time.
    closing_time = (datetime.now() + time_diffs[form.close_in.data]
                    ).replace(second=0, microsecond=0)
    password = form.password.data
    if password == "":
        # User didn't enter a password, generate one.
        password = utils.generate_password()
        # We need to know whether to tell the user what their password is.
        random_password = True
    else:
        random_password = False
    early_results = form.early_results.data
    poll_id = db_funcs.add_poll(title, question, choices,
                                int(closing_time.timestamp()), early_results,
                                password, email)
    if random_password:
        # Redirect to a page telling them what their password is.
        return render_template("random_password.html", poll_id=poll_id,
                               password=password)
    else:
        # Send the user to their new poll.
        return redirect(url_for("polls.get_poll", poll_id=poll_id))


@bp.route("<int:poll_id>/", methods=("GET", "POST"))
def get_poll(poll_id):
    if not utils.valid_session(session):
        # User couldn't present valid credentials, so generate clean ones.
        # TODO: Fix DB stuff to do this all at once?
        cookie_id = db_funcs.new_cookie()
        cookie_hash = binascii.hexlify(os.urandom(32)).decode("ascii")
        session["id"] = cookie_id
        session["votes"] = []
        session["cookie_hash"] = cookie_hash
        db_funcs.update_cookie(cookie_id, cookie_hash,
                               int(datetime.now().timestamp()))
        current_app.logger.info("New session instantiated")
    # If the user looks trustworthy, don't ask them for a captcha.
    if len(session["votes"]) < 5:
        form = VoteFormWithCaptcha()
    else:
        form = VoteForm()
    if current_app.config["DEBUG"]:
        # Recaptcha probably won't work
        form = VoteForm()
    # Query database for poll details.
    row = db_funcs.get_poll(poll_id)
    if row is None:
        abort(404)
    if row["close_date"] < datetime.now().timestamp():
        # Poll is expired and should be closed.
        db_funcs.close_poll(poll_id)
        generate_results(poll_id)
        # Redirect to results.
        return redirect(url_for("polls.get_results", poll_id=poll_id))
    # Check if the poll is in the user's voting record already.
    if poll_id in session["votes"]:
        already_voted = True
    else:
        already_voted = False
    # TODO: Fix the HTML for that so it isn't awful?
    # Argh why can't I flash to current request.
    if request.method == "POST":
        if already_voted and not current_app.config["ALLOW_REPEAT_VOTES"]:
            # Users aren't allowed to vote twice.
            flash("You've already voted on this poll")
            return redirect(url_for("polls.get_poll", poll_id=poll_id))
        if not form.validate_on_submit():
            for error_field, errors in form.errors.items():
                for error in errors:
                    flash("{0}: {1}".format(error_field, error))
            return redirect(url_for("polls.get_poll", poll_id=poll_id))
        # TODO: more aggressively deny voting with no credential?
        # or does CSRF token work alone?

        # Which choices are recorded in the database?
        valid_choices = [row["choice_number"]
                         for row in db_funcs.get_choices(poll_id)]
        choices = []
        # User should've sent their choice preferences like 1;2;3;4.
        # Split and iterate over them.
        for choice in form.ballot_json.data.split(";"):
            try:
                # Is this choice a valid int? And is it in the database?
                if int(choice) in valid_choices:
                    # If so store it in 'choices'.
                    choices.append(int(choice))
            # If not, ignore it.
            except ValueError:
                continue
        if len(choices) == 0:
            flash("You have to select at least one valid choice")
            return redirect(url_for("polls.get_poll", poll_id=poll_id))
        # Serialise the vote for storage in database.
        ballot_string = ",".join(map(str, choices))
        db_funcs.add_vote(poll_id, ballot_string)
        # Vote was successfully recorded; add poll to user's voting record.
        session["votes"].append(poll_id)
        cookie_hash = binascii.hexlify(os.urandom(32)).decode("ascii")
        session["cookie_hash"] = cookie_hash
        db_funcs.update_cookie(session["id"], cookie_hash,
                               int(datetime.now().timestamp()))
        if row["early_results"]:
            # Early results enabled for this poll, send user to preview page.
            return redirect(url_for("polls.get_results", poll_id=poll_id))
        else:
            # Early results not enabled, redirect to homepage.
            return redirect(url_for("home"))
    # This is a GET request, prepare template with details for requested poll.
    title, question = row["title"], row["text"]
    close_date = datetime.fromtimestamp(row["close_date"])
    # TODO: handle more properly
    if datetime.now() >= close_date:
        return redirect(url_for("polls.get_results", poll_id=poll_id))
    early_results = row["early_results"]
    choices = {row["choice_number"]: row["text"] for row in
               db_funcs.get_choices(poll_id)}
    choices_json = [{"name": v, "num": k} for k, v in choices.items()]
    return render_template("poll.html", title=title,
                                        question=question,
                                        choices=choices,
                                        close_date=str(close_date),
                                        poll_id=poll_id,
                                        choices_json=choices_json,
                                        early_results=early_results,
                                        form=form,
                                        already_voted=already_voted)

def generate_results(poll_id):
    # Seed the RNG for consistent tie-breaking.
    random.seed(poll_id)
    choices = [row["choice_number"] for row in db_funcs.get_choices(poll_id)]
    choices = sorted(choices)
    # Fetch 'ballots' dict: vote counts keyed by ballot strings.
    # eg if 10 people voted 1,2,3 it's {"1,2,3": 10}.
    ballots = db_funcs.get_ballots(poll_id)
    # How many votes have been cast?
    total_ballots = sum(ballots.values())
    # Count how many ballots have each option as their first choice.
    votes = {choice: sum([count for ballot, count in ballots.items()
                          if ballot.split(",")[0] == str(choice)])
             for choice in choices}
    if total_ballots == 0:
        # We have no votes! End early.
        results_sequence = [votes]
        db_funcs.update_results(poll_id, json.dumps(results_sequence))
        return
    # Option that has the most first-preference votes this round.
    round_winner = max(choices, key=lambda x: votes[x])
    # Populate 'eliminated' set with choices that already have
    # no first-preference votes, so they don't get counted later.
    eliminated = set(c for c in choices if votes[c] == 0)
    # Store the first-preference votes for the first round in the results list.
    results_sequence = [votes]
    # Continue until there is a majority of outstanding ballots.
    while votes[round_winner] <= total_ballots/2:
        # Placeholder dict. Awkward to simply create this in a comprehension
        # because any number of keys from the first dict could be related
        # to one from the second.
        # eg 2,1 3,1 4,1 5,1 6,1 7,1 could all collapse to the key 1.
        new_ballots = defaultdict(lambda: 0)
        # Find the minimum vote number for options not already eliminated.
        # Could be any non-negative number including 0. But if we simply got
        # the minimum then eliminated options would be the minimum every time.
        # Voting wouldn't progress. So we keep track.
        lowest_votes = min([c for v, c in votes.items() if v not in eliminated])
        # 'losers': options that won the minimum number of votes.
        losers = [c for c in choices if votes[c] == lowest_votes]
        # Don't count eliminated options.
        losers = set(losers) - eliminated
        if len(losers) > 1:
            # Multiple losers. Can we eliminate all at once?
            # Only if the sum total of all loser votes is less than the
            # number of votes won by the next best option.
            second_lowest_votes = min(set(votes.values()) - set([lowest_votes]))
            if sum([votes[l] for l in losers]) >= second_lowest_votes:
                # It's possible that a loser might, if not eliminated now,
                # win enough votes to beat a non-loser.
                # We can't eliminate them all safely, so randomly tie-break.
                losers = set(random.sample(losers, 1))
            # 'losers' is now guaranteed to either be one candidate, or a set
            # of candidates that can safely be eliminated simultanenously.
        # Record the 'losers' as being eliminated, as that's what will happen.
        eliminated |= losers
        if eliminated == set(choices):
            # We've eliminated everyone. It's a draw. Shut down everything.
            db_funcs.update_results(poll_id, json.dumps(results_sequence))
            return
        for ballot, count in ballots.items():
            # Excise eliminated options from the ballot.
            new_ballot = ",".join([c for c in ballot.split(",")
                                   if not int(c) in eliminated])
            # Check that at least one option remains on the ballot!
            # No point counting it if not.
            if len(new_ballot) > 0:
                # Add the number of votes for the old ballot to the count
                # for the new ballot.
                new_ballots[new_ballot] += count
        if len(new_ballots) == 0:
            # With tie-breaking this probably isn't possible. But if so:
            # Every ballot consisted only of eliminated options.
            # End voting early.
            db_funcs.update_results(poll_id, json.dumps(results_sequence))
            return
        # Update the key variables, append this round's results to the list.
        ballots = new_ballots
        total_ballots = sum(ballots.values())
        votes = {choice: sum([count for ballot, count in ballots.items()
                              if ballot.split(",")[0] == str(choice)])
                 for choice in choices}
        round_winner = max(choices, key=lambda x: votes[x])
        results_sequence.append(votes)
    # Voting is finally over, a majority has been attained.
    db_funcs.update_results(poll_id, json.dumps(results_sequence))
    return


@bp.route("<int:poll_id>/results")
def get_results(poll_id):
    row = db_funcs.get_poll(poll_id)
    if row is None:
        abort(404)
    # If poll is open and early results disabled, no results are available.
    if not row["early_results"] and row["open"]:
        # Although it's possible that the poll should be closed now.
        if row["close_date"] < datetime.now().timestamp():
            db_funcs.close_poll(poll_id)
        else:
            # If not, send the user back whence they came.
            flash("Preview results not available for this poll")
            return redirect(url_for("polls.get_poll", poll_id=poll_id))
    title = row["title"]
    text = row["text"]
    poll_open = row["open"]
    row = db_funcs.get_results(poll_id)
    # Timestamp for earliest acceptable cached results.
    update_target = (int(datetime.now().timestamp())
                     - current_app.config["UPDATE_INTERVAL"])
    if row is None or row["last_update"] < update_target:
        # No up to date results found, so calculate some.
        generate_results(poll_id)
        row = db_funcs.get_results(poll_id)
    results = json.loads(row["results_json"])
    if sum(results[0].values()) == 0:
        if poll_open:
            flash("Insufficient votes have been cast to generate results")
            return redirect(url_for("polls.get_poll", poll_id=poll_id))
        else:
            flash("This poll closed without any votes being cast")
            return redirect(url_for("home"))
    rows = db_funcs.get_choices(poll_id)
    # Associate choice numbers with names/descriptions.
    choice_dict = {row["choice_number"]: row["text"] for row in rows}
    # Let's not rely on Javascript to identify the winner of each round.
    winners = [choice_dict[int(x)]
               for x in [y for y in results[-1].keys()
                         if results[-1][y] == max(results[-1].values())]]
    return render_template("results.html", results=results,
                           choice_dict=choice_dict,
                           winners=winners,
                           title=title,
                           text=text,
                           poll_id=poll_id,
                           poll_open=poll_open)

# DEPRECATED?
def update_open_polls():
    # Close expired polls and generate results for them.
    for poll_id in db_funcs.close_expired_polls():
        generate_results(poll_id)
        # TODO: Delete ballots too.
    # Generate results for polls that are still open and preview enabled.
    for poll_id in db_funcs.get_open_early_resultspolls():
        generate_results(poll_id)

@bp.route("<int:poll_id>/delete", methods=("GET", "POST"))
def delete_poll(poll_id):
    row = db_funcs.get_poll(poll_id)
    if current_app.config["DEBUG"]:
        # Recaptcha probably doesn't work.
        form = EnterPasswordForm()
    else:
        # Sorry, users. I'm concerned about bruteforcing.
        form = EnterPasswordFormWithCaptcha()
    if request.method == "GET":
        # Send user to form for them to fill in their password.
        if row is None:
            abort(404)
        return render_template("delete_poll.html", title=row["title"],
                               question=row["text"], email=row["email"],
                               poll_id=poll_id, form=form)
    if not form.validate_on_submit():
        for error in form.errors:
            flash(error)
            return render_template("delete_poll.html", title=row["title"],
                               question=row["text"], email=row["email"],
                               poll_id=poll_id, form=form)
    if row is None:
        abort(404)
    if current_app.config["DEBUG"] and form.password.data == "admin":
        # TODO: this probably shouldn't be deployed even with the DEBUG check
        current_app.logger.info("Admin deleted poll")
        db_funcs.delete_poll(poll_id)
        flash("Deletion successful!")
        return redirect(url_for("home"))
    # Salt: sha1(poll title + close_date)
    # Todo: integrate poll id?
    salt = hashlib.sha1(row["title"].encode("ascii")
                        + str(row["close_date"]).encode("ascii")).digest()
    # Get hash of password+salt
    token = utils.hash_password(form.password.data, salt)
    # Compare given hash with known hash using safe comparison function
    if not hmac.compare_digest(row["token"], token):
        current_app.logger.info("Incorrect password")
        flash("Incorrect password")
        return redirect(url_for("polls.delete_poll", poll_id=poll_id))
    db_funcs.delete_poll(poll_id)
    flash("Deletion successful!")
    return redirect(url_for("home"))


@bp.route("<int:poll_id>/delete_by_email", methods=("GET", "POST"))
def send_deletion_email(poll_id):
    # Query database for poll details.
    row = db_funcs.get_poll(poll_id)
    if row is None:
        abort(404)
    if row["email"] is None:
        flash("No email recorded for this poll")
        return redirect(url_for("polls.get_poll", poll_id=poll_id))
    form = CaptchaOnlyForm()
    if request.method == "GET":
        # Send user the captcha.
        return render_template("send_deletion_email.html", form=form)
    # It's a POST.
    # Check for captcha completion or ignore if debug
    if not form.validate_on_submit() and not current_app.config["DEBUG"]:
        for error in form.errors:
            flash(error)
            return render_template("send_deletion_email.html", form=form)
    # Create expiring single-use token recording poll id and deletion op.
    token = utils.create_token("delete_poll", poll_id)
    # Render the template to put in an email.
    email_html = render_template("EMAIL_deletion_link.html",
                                 poll_id=poll_id, title=row["title"],
                                 token=token)
    try:
        send_mail("Confirm poll deletion",
                  email_html,
                  "deletepoll@stickpoll.com",
                  row["email"])
        flash("Email sent")
        # Success, redirect back to poll.
        return redirect(url_for("polls.get_poll", poll_id=poll_id))
    except Exception as e:
        flash("Problem sending email, administrator notified")
        current_app.logger.error("Problem sending email: {0}".format(e))
        # Failure, redirect back to deletion page.
        return redirect(url_for("polls.delete_poll", poll_id=poll_id))


@bp.route("<int:poll_id>/delete_by_email/<token>")
def send_delete_token(poll_id, token):
    try:
        d = utils.read_token(token)
        if d["op"] == "delete_poll" and d["id"] == poll_id:
            db_funcs.delete_poll(poll_id)
            flash("Deletion successful!")
    except ValueError:
        current_app.logger.info("Bad token: {0}".format(token))
        flash("Bad token!")
    return redirect(url_for("home"))
