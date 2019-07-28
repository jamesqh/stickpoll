#!/usr/bin/env python3

import db_funcs

import base64
import binascii
from datetime import date, datetime, timedelta
import hashlib
import hmac
import json
import os
import random
import string

from flask import current_app

def generate_password():
    """Securely generate 32 character alphanumeric password."""
    pw_len = 32
    alphabet = string.ascii_letters + string.digits
    pw_bytes = os.urandom(pw_len)
    return "".join([alphabet[b%len(alphabet)] for b in pw_bytes])

def hash_password(password, salt):
    """Return PBKDF2 (HMAC-SHA256) hash of password/salt."""
    bin_hash = hashlib.pbkdf2_hmac("sha256", password.encode("ascii"), salt,
                                   100000)
    return binascii.hexlify(bin_hash).decode("ascii")

def create_token(op_type, poll_id, expires=60*24*2):
    """Create signed token encoding op type, poll id and expiry date."""
    # Deprecated? Flask sessions used instead.
    try:
        key = current_app.config["SECRET_KEY"].encode("ascii")
    except AttributeError:
        key = current_app.config["SECRET_KEY"]
    json_serial = json.dumps({"op": op_type, "id": poll_id,
                              "exp": int((datetime.now()
                                          + timedelta(minutes=expires)
                                          ).timestamp())}).encode("ascii")
    tag = hmac.new(key, json_serial, digestmod="sha1").digest()
    return (base64.urlsafe_b64encode(json_serial)
            + b"."
            + base64.urlsafe_b64encode(tag)).decode("ascii")

def read_token(token):
    """Verify token signature valid and return contents."""
    # Deprecated? Flask sessions used instead.
    try:
        key = current_app.config["SECRET_KEY"].encode("ascii")
    except AttributeError:
        key = current_app.config["SECRET_KEY"]
    json_serial, tag = [base64.urlsafe_b64decode(s) for s in token.split(".")]
    correct_tag = hmac.new(key, json_serial, digestmod="sha1").digest()
    if not hmac.compare_digest(correct_tag, tag):
        raise ValueError
    else:
        json_dict = json.loads(json_serial.decode("ascii"))
        if json_dict["exp"] < datetime.now().timestamp():
            raise ValueError
        else:
            return json_dict

def valid_session(session):
    """Inspect Flask session for intact voting record data."""
    if "id" not in session or not isinstance(session["id"], int):
        return False
    if "votes" not in session or not isinstance(session["votes"], list):
        return False
    if "cookie_hash" not in session or not isinstance(session["cookie_hash"],
                                                      str):
        return False
    cookie_hash = db_funcs.get_cookie_hash(session["id"])
    if cookie_hash is None:
        return False
    if cookie_hash != session["cookie_hash"]:
        return False
    return True
