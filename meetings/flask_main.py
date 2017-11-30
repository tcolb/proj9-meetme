import flask
from flask import render_template
from flask import request
from flask import url_for
import uuid
from times import Chunk, Block

import json
import logging

# Date handling
import arrow  # Replacement for datetime, based on moment.js
# import datetime but we still need time
from dateutil import tz  # For interpreting local times


# OAuth2  - Google library implementation for convenience
from oauth2client import client
import httplib2   # used in oauth2 flow

# Google API for services
from apiclient import discovery

# Pymongo
from pymongo import MongoClient


###
# Globals
###


import config
if __name__ == "__main__":
    CONFIG = config.configuration()
else:
    CONFIG = config.configuration(proxied=True)

app = flask.Flask(__name__)
app.debug = CONFIG.DEBUG
app.logger.setLevel(logging.DEBUG)
app.secret_key = CONFIG.SECRET_KEY

SCOPES = 'https://www.googleapis.com/auth/calendar.readonly'
CLIENT_SECRET_FILE = CONFIG.GOOGLE_KEY_FILE  # You'll need this
APPLICATION_NAME = 'MeetMe class project'

MONGO_CLIENT_URL = "mongodb://{}:{}@{}:{}/{}".format(
    CONFIG.DB_USER,
    CONFIG.DB_USER_PW,
    CONFIG.DB_HOST,
    CONFIG.DB_PORT,
    CONFIG.DB)

print("Using Mongo URL '{}'".format(MONGO_CLIENT_URL))


###
# DB Setup
###


try:
    dbclient = MongoClient(MONGO_CLIENT_URL)
    db = getattr(dbclient, CONFIG.DB)
    collection = db.schedules

except:
    print("Failure opening database.  Is Mongo running? Correct password?")
    sys.exit(1)


#############################
#
#  Pages (routed from URLs)
#
#############################


@app.route("/")
@app.route("/index")
def index():
    app.logger.debug("Entering index")
    if 'begin_date' not in flask.session:
        init_session_values()
    return render_template('index.html')


@app.route("/choose")
def choose():
    # We'll need authorization to list calendars
    # I wanted to put what follows into a function, but had
    # to pull it back here because the redirect has to be a
    # 'return'

    app.logger.debug("Checking credentials for Google calendar access")
    credentials = valid_credentials()
    if not credentials:
        app.logger.debug("Redirecting to authorization")
        return flask.redirect(flask.url_for('oauth2callback'))

    gcal_service = get_gcal_service(credentials)
    app.logger.debug("Returned from get_gcal_service")
    flask.session['calendars'] = list_calendars(gcal_service)
    return flask.redirect("/schedule/" + flask.session['uid'])


@app.route("/schedule/<unique_id>")
def schedule(unique_id):
    flask.session['uid'] = unique_id  # UID to redirect to after account selection

    schedule = []
    document = collection.find_one({ "uid":unique_id })
    for time in document["times"]:
        #schedule.append(arrow.get(time).isoformat())
        schedule.append(time)

    try:
        flask.g.calendars = flask.session['calendars']
    except KeyError:
        app.logger.debug("Calendars not defined")

    return render_template("schedule.html", times=schedule)


####
#
#  Google calendar authorization:
#      Returns us to the main /choose screen after inserting
#      the calendar_service object in the session state.  May
#      redirect to OAuth server first, and may take multiple
#      trips through the oauth2 callback function.
#
#  Protocol for use ON EACH REQUEST:
#     First, check for valid credentials
#     If we don't have valid credentials
#         Get credentials (jump to the oauth2 protocol)
#         (redirects back to /choose, this time with credentials)
#     If we do have valid credentials
#         Get the service object
#
#  The final result of successful authorization is a 'service'
#  object.  We use a 'service' object to actually retrieve data
#  from the Google services. Service objects are NOT serializable ---
#  we can't stash one in a cookie.  Instead, on each request we
#  get a fresh serivce object from our credentials, which are
#  serializable.
#
#  Note that after authorization we always redirect to /choose;
#  If this is unsatisfactory, we'll need a session variable to use
#  as a 'continuation' or 'return address' to use instead.
#
####

def valid_credentials():
    """
    Returns OAuth2 credentials if we have valid
    credentials in the session.  This is a 'truthy' value.
    Return None if we don't have credentials, or if they
    have expired or are otherwise invalid.  This is a 'falsy' value.
    """
    if 'credentials' not in flask.session:
      return None

    credentials = client.OAuth2Credentials.from_json(
        flask.session['credentials'])

    if (credentials.invalid or
        credentials.access_token_expired):
      return None
    return credentials

def get_gcal_service(credentials):
  """
  We need a Google calendar 'service' object to obtain
  list of calendars, busy times, etc.  This requires
  authorization. If authorization is already in effect,
  we'll just return with the authorization. Otherwise,
  control flow will be interrupted by authorization, and we'll
  end up redirected back to /choose *without a service object*.
  Then the second call will succeed without additional authorization.
  """
  app.logger.debug("Entering get_gcal_service")
  http_auth = credentials.authorize(httplib2.Http())
  service = discovery.build('calendar', 'v3', http=http_auth)
  app.logger.debug("Returning service")
  return service

@app.route('/oauth2callback')
def oauth2callback():
  """
  The 'flow' has this one place to call back to.  We'll enter here
  more than once as steps in the flow are completed, and need to keep
  track of how far we've gotten. The first time we'll do the first
  step, the second time we'll skip the first step and do the second,
  and so on.
  """
  app.logger.debug("Entering oauth2callback")
  flow =  client.flow_from_clientsecrets(
      CLIENT_SECRET_FILE,
      scope= SCOPES,
      redirect_uri=flask.url_for('oauth2callback', _external=True))
  # Note we are *not* redirecting above.  We are noting *where*
  # we will redirect to, which is this function.

  # The *second* time we enter here, it's a callback
  # with 'code' set in the URL parameter.  If we don't
  # see that, it must be the first time through, so we
  # need to do step 1.
  app.logger.debug("Got flow")
  if 'code' not in flask.request.args:
    app.logger.debug("Code not in flask.request.args")
    auth_uri = flow.step1_get_authorize_url()
    return flask.redirect(auth_uri)
    ## This will redirect back here, but the second time through
    ## we'll have the 'code' parameter set
  else:
    ## It's the second time through ... we can tell because
    ## we got the 'code' argument in the URL.
    app.logger.debug("Code was in flask.request.args")
    auth_code = flask.request.args.get('code')
    credentials = flow.step2_exchange(auth_code)
    flask.session['credentials'] = credentials.to_json()
    ## Now I can build the service and execute the query,
    ## but for the moment I'll just log it and go back to
    ## the main screen
    app.logger.debug("Got credentials")
    return flask.redirect(flask.url_for('choose'))


#############################
#
#  Processing callbacks
#
#############################


@app.route("/_create", methods=['POST', 'GET'])
def create():
    uid = request.json['id']

    daterange = request.json['daterange'].split()
    begin_date = arrow.get(interpret_date(daterange[0]))
    end_date = arrow.get(interpret_date(daterange[2]))
    diff = ((end_date - begin_date).days) + 1
    begin_time = arrow.get(interpret_time(request.json['begintime']))
    end_time = arrow.get(interpret_time(request.json['endtime']))
    begin = add_time(begin_date, begin_time)
    end = add_time(begin_date, end_time)

    initial = []
    for day in range(diff):
        initial.append({ 'begin': begin, 'end': end })
        begin = next_day(begin)
        end = next_day(end)

    # TODO check to see if id already used? or maybe not
    collection.insert({ "type": "schedule", "uid": uid,
                        "range": { "begin": add_time(begin_date, begin_time),
                                   "end": add_time(end_date, end_time) },
                        "times": initial })
    return flask.jsonify(True)


@app.route('/_events', methods=['POST', 'GET'])
def events():
    """
    Get event data for selected calendars and send back to frontend
    using AJAX
    """

    # Grab unique schedule id for DB querying
    uid = flask.session['uid']

    # Get GCal service
    service = get_gcal_service(valid_credentials())
    selected_cals = request.json['ids']

    # General date vars TODO get from DB
    db_schedule = collection.find_one({ "uid": uid })

    # Get vals from db schedule
    begin_query = arrow.get(db_schedule["range"]["begin"])
    end_query = arrow.get(db_schedule["range"]["end"])
    free_chunk = Chunk(begin_query, end_query)
    db_block = db_to_block(db_schedule["times"])

    # Iterate through selected ids
    for cal_id in selected_cals:
        block = Block()
        events = service.events().list(calendarId=cal_id, # Calendar selection
                                       timeMin=begin_query, # Open time
                                       timeMax=end_query, # Close time
                                       singleEvents=True, # No recurring event selection, fixes no summary index errors
                                       orderBy="startTime").execute() # Order events by startTime and execute query

        # Grab cal events for each id
        for event in events['items']:
            # Get arrow objects for start and end range
            arrow_start = arrow.get(event['start']['dateTime'])
            arrow_end = arrow.get(event['end']['dateTime'])

            # Add chunk to calendar block
            block.append(Chunk(arrow_start, arrow_end))

        block = block.complement(free_chunk)
        db_block = db_block.intersect(block)
    print(">>", block_to_db(db_block))
    collection.update_one({ "uid": uid },
                          { "$set": { "times": block_to_db(db_block) } })
    # TODO instead of returning to client, write to db and redirect
    return flask.jsonify(True)


#####
#
#  Option setting:  Buttons or forms that add some
#     information into session state.  Don't do the
#     computation here; use of the information might
#     depend on what other information we have.
#   Setting an option sends us back to the main display
#      page, where we may put the new information to use.
#
#####

@app.route('/setrange', methods=['POST'])
def setrange():
    """
    User chose a date range with the bootstrap daterange
    widget.
    """
    app.logger.debug("Entering setrange")
    flask.flash("Setrange gave us '{}' from '{}' to '{}'".format(
      request.form.get('daterange'),
      request.form.get('begintime'), request.form.get('endtime')))
    daterange = request.form.get('daterange')
    flask.session['daterange'] = daterange
    flask.session['timerange'] = {'begintime': request.form.get('begintime'),
                                  'endtime': request.form.get('endtime')}
    daterange_parts = daterange.split()

    flask.session['begin_date'] = interpret_date(daterange_parts[0])
    flask.session['end_date'] = interpret_date(daterange_parts[2])
    flask.session['begin_time'] = interpret_time(request.form.get('begintime'))
    flask.session['end_time'] = interpret_time(request.form.get('endtime'))

    app.logger.debug("Setrange parsed {} - {}  dates as {} - {} \n parsed {} - {} times as {} - {}".format(
      daterange_parts[0], daterange_parts[1],
      flask.session['begin_date'], flask.session['end_date'],
      flask.session['timerange']['begintime'], flask.session['timerange']['endtime'],
      flask.session['begin_time'], flask.session['end_time']))
    return flask.redirect(flask.url_for("choose"))


####
#
#   Initialize session variables
#
####

def init_session_values():
    """
    Start with some reasonable defaults for date and time ranges.
    Note this must be run in app context ... can't call from main.
    """
    # Default date span = tomorrow to 1 week from now
    now = arrow.now('local')     # We really should be using tz from browser
    tomorrow = now.replace(days=+1)
    nextweek = now.replace(days=+7)
    flask.session["begin_date"] = tomorrow.floor('day').isoformat()
    flask.session["end_date"] = nextweek.ceil('day').isoformat()
    flask.session["daterange"] = "{} - {}".format(
        tomorrow.format("MM/DD/YYYY"),
        nextweek.format("MM/DD/YYYY"))
    # Default time span each day, 9 to 5
    flask.session["begin_time"] = interpret_time("9am")
    flask.session["end_time"] = interpret_time("5pm")
    flask.session["timerange"] = {'begintime': '09:00 AM', 'endtime': '5:00 PM'}

def interpret_time( text ):
    """
    Read time in a human-compatible format and
    interpret as ISO format with local timezone.
    May throw exception if time can't be interpreted. In that
    case it will also flash a message explaining accepted formats.
    """
    app.logger.debug("Decoding time '{}'".format(text))
    time_formats = ["ha", "h:mma",  "h:mm a", "H:mm"]
    try:
        as_arrow = arrow.get(text, time_formats).replace(tzinfo=tz.tzlocal())
        as_arrow = as_arrow.replace(year=2016) #HACK see below
        app.logger.debug("Succeeded interpreting time")
    except:
        app.logger.debug("Failed to interpret time")
        flask.flash("Time '{}' didn't match accepted formats 13:30 or 1:30pm"
              .format(text))
        raise
    return as_arrow.isoformat()
    #HACK #Workaround
    # isoformat() on raspberry Pi does not work for some dates
    # far from now.  It will fail with an overflow from time stamp out
    # of range while checking for daylight savings time.  Workaround is
    # to force the date-time combination into the year 2016, which seems to
    # get the timestamp into a reasonable range. This workaround should be
    # removed when Arrow or Dateutil.tz is fixed.
    # FIXME: Remove the workaround when arrow is fixed (but only after testing
    # on raspberry Pi --- failure is likely due to 32-bit integers on that platform)


def interpret_date( text ):
    """
    Convert text of date to ISO format used internally,
    with the local time zone.
    """
    try:
      as_arrow = arrow.get(text, "MM/DD/YYYY").replace(
          tzinfo=tz.tzlocal())
    except:
        flask.flash("Date '{}' didn't fit expected format 12/31/2001")
        raise
    return as_arrow.isoformat()

def next_day(isotext):
    """
    ISO date + 1 day (used in query to Google calendar)
    """
    as_arrow = arrow.get(isotext)
    return as_arrow.replace(days=+1).isoformat()

def add_time(date_text, time_text):
    """
    Add hour and minute component from ISO date to another ISO date
    """
    date_arrow = arrow.get(date_text)
    time_arrow = arrow.get(time_text)

    return date_arrow.shift(hours=+time_arrow.hour,
                            minutes=+time_arrow.minute).isoformat()


####
#
#  Functions (NOT pages) that return some information
#
####

def list_calendars(service):
    """
    Given a google 'service' object, return a list of
    calendars.  Each calendar is represented by a dict.
    The returned list is sorted to have
    the primary calendar first, and selected (that is, displayed in
    Google Calendars web app) calendars before unselected calendars.
    """
    app.logger.debug("Entering list_calendars")
    calendar_list = service.calendarList().list().execute()["items"]
    result = [ ]
    for cal in calendar_list:
        kind = cal["kind"]
        id = cal["id"]
        if "description" in cal:
            desc = cal["description"]
        else:
            desc = "(no description)"
        summary = cal["summary"]
        # Optional binary attributes with False as default
        selected = ("selected" in cal) and cal["selected"]
        primary = ("primary" in cal) and cal["primary"]


        result.append(
          { "kind": kind,
            "id": id,
            "summary": summary,
            "selected": selected,
            "primary": primary
            })
    return sorted(result, key=cal_sort_key)


def cal_sort_key( cal ):
    """
    Sort key for the list of calendars:  primary calendar first,
    then other selected calendars, then unselected calendars.
    (" " sorts before "X", and tuples are compared piecewise)
    """
    if cal["selected"]:
       selected_key = " "
    else:
       selected_key = "X"
    if cal["primary"]:
       primary_key = " "
    else:
       primary_key = "X"
    return (primary_key, selected_key, cal["summary"])

# TODO this shit
def block_to_db(block):
    result = []
    for chunk in block._chunks:
        result.append({'begin': chunk._begin.isoformat(), 'end': chunk._end.isoformat()})
    return result


def db_to_block(arr):
    block = Block()
    for time in arr:
        block.append(Chunk(arrow.get(time['begin']), arrow.get(time['end'])))
    return block



#################
#
# Functions used within the templates
#
#################

@app.template_filter( 'fmtdate' )
def format_arrow_date( date ):
    try:
        normal = arrow.get( date )
        return normal.format("ddd MM/DD/YYYY")
    except:
        return "(bad date)"

@app.template_filter( 'fmttime' )
def format_arrow_time( time ):
    try:
        normal = arrow.get( time )
        return normal.format("HH:mm")
    except:
        return "(bad time)"

#############


if __name__ == "__main__":
  # App is created above so that it will
  # exist whether this is 'main' or not
  # (e.g., if we are running under green unicorn)
  app.run(port=CONFIG.PORT,host="0.0.0.0")
