#!/usr/bin/env python3

from copy import copy

from flask_wtf import FlaskForm, RecaptchaField
from wtforms import (StringField, PasswordField, BooleanField, RadioField,
                     FieldList)
from wtforms.validators import Email, EqualTo, InputRequired, Length, Optional

from wtforms.widgets.core import HTMLString, RadioInput
from wtforms.fields.core import SelectField, text_type

class BulmaCheckradioListWidget():
    def __init__(self, tags=None, prefix_label=True):
        self.prefix_label = prefix_label
        if tags is None:
            tags = []
        self.tags = tags
    def __call__(self, field, **kwargs):
        #kwargs.setdefault("id", field.id)
        html = []
        field_id = field.id
        i = 0
        for subfield in field:
            for tag in self.tags:
                html.append("<{0}>".format(tag))
            kwargs["id"] = "{0}-{1}".format(field_id, i)
            if self.prefix_label:
                html.append("{0} {1}".format(subfield.label,
                                             subfield(**kwargs)))
            else:
                html.append("{0} {1}".format(subfield(**kwargs),
                                             subfield.label))
            for tag in reversed(self.tags):
                html.append("</{0}>".format(tag))
            i += 1
        return HTMLString("".join(html))

class BulmaCheckradioField(SelectField):
    option_widget = RadioInput()
    def __init__(self, label=None, validators=None, coerce=text_type,
                 choices=None, tags=None, **kwargs):
        super(SelectField, self).__init__(label, validators, **kwargs)
        self.coerce = coerce
        self.choices = copy(choices)
        self.widget = BulmaCheckradioListWidget(tags=tags, prefix_label=False)

class NewPollForm(FlaskForm):
    title = StringField("Title", validators=[Length(min=6, max=200),
                                             InputRequired()])
    question = StringField("Question", validators=[Length(min=6, max=5000),
                                                   InputRequired()])
##    choices_json = StringField("Choices (separate with semicolon)",
##                               validators=[Length(min=1, max=100000),
##                                           InputRequired()])
    choices = FieldList(StringField("Choice", validators=[Length(max=10000)]),
                        min_entries=2, max_entries=12)
    close_in = BulmaCheckradioField("Close poll in",
                          choices=[("hour", "1 hour"),
                                   ("day", "1 day"),
                                   ("week", "1 week"),
                                   ("month", "1 month")],
                          default="month")
    password = PasswordField("Password to delete poll or close early "
                             "(will be randomly generated if left blank)",
                             validators=[Length(min=6, max=128),
                                         Optional(),
                                         EqualTo("password_confirm",
                                                 "Passwords must match")])
    password_confirm = PasswordField("Confirm password")
    email = StringField("Email to send deletion link to, should you "
                        "forget the password (not required)",
                        validators=[Optional(),
                                    Email(), EqualTo("email_confirm",
                                                     "Emails must match")])
    email_confirm = StringField("Confirm email",
                                validators=[Optional(), Email()])
    early_results = BooleanField("Early results - if checked a public preview "
                                 "of the results as the poll stands will "
                                 "be generated hourly",
                                 default="checked")

class NewPollFormWithCaptcha(NewPollForm):
    captcha = RecaptchaField()

class EnterPasswordForm(FlaskForm):
    password = PasswordField("Password", validators=[InputRequired()])

class SearchForm(FlaskForm):
    search_string = StringField("Search for",
                                validators=[Length(min=3, max=200),
                                            InputRequired()])
##    title_search = BooleanField("In titles")
##    text_search = BooleanField("In question texts")
##    search_open = BooleanField("Search open polls")
##    search_closed = BooleanField("Search closed polls")
    search_columns = BulmaCheckradioField("In these fields",
                                          choices=[("both","Title and text"),
                                                   ("title", "Title only"),
                                                   ("text", "Text only")],
                                          default="both",
                                          tags=["li"])
    search_open = BulmaCheckradioField("In these polls",
                                       choices=[("all", "All polls"),
                                                ("open", "Open polls"),
                                                ("closed", "Closed polls")],
                                       default="all",
                                       tags=["li"])
    order_by = BulmaCheckradioField("Order by",
                                    choices=[("rel", "Relevance"),
                                             ("date", "Close date")],
                                    default="rel",
                                    tags=["li"])
    order_dir = BulmaCheckradioField("Order direction",
                                     choices=[("desc", "Descending"),
                                              ("asc", "Ascending")],
                                     default="desc",
                                     tags=["li"])

class VoteForm(FlaskForm):
    ballot_json = StringField("Preferred choices")

class VoteFormWithCaptcha(VoteForm):
    captcha = RecaptchaField()
