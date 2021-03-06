import os
import pymongo
from flask import Flask, g, session, redirect, request, url_for, jsonify, render_template
import flask_breadcrumbs
from requests_oauthlib import OAuth2Session
from oauth import Oauth
import dns
import oauth
import database
import datetime
import json

OAUTH2_CLIENT_ID = Oauth.client_id
OAUTH2_CLIENT_SECRET = Oauth.client_secret
OAUTH2_REDIRECT_URI = 'https://disguard.herokuapp.com/callback'
#OAUTH2_REDIRECT_URI = 'http://localhost:5000/callback'

API_BASE_URL = 'https://discordapp.com/api'
AUTHORIZATION_BASE_URL = API_BASE_URL + '/oauth2/authorize'
TOKEN_URL = API_BASE_URL + '/oauth2/token'

app = Flask(__name__)
flask_breadcrumbs.Breadcrumbs(app=app)

app.debug = True
app.config['SECRET_KEY'] = Oauth.client_secret

mongo = pymongo.MongoClient(oauth.mongo()) #Database connection URL in another file so you peeps don't go editing the database ;)
db = mongo.disguard
#db = mongo.disguard_beta #Allows for dashboard to use test database if necessary
servers = db.servers
users = db.users

if 'http://' in OAUTH2_REDIRECT_URI:
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = 'true'


def token_updater(token):
    session['oauth2_token'] = token


def make_session(token=None, state=None, scope=None):
    return OAuth2Session(
        client_id=OAUTH2_CLIENT_ID,
        token=token,
        state=state,
        scope=scope,
        redirect_uri=OAUTH2_REDIRECT_URI,
        auto_refresh_kwargs={
            'client_id': OAUTH2_CLIENT_ID,
            'client_secret': OAUTH2_CLIENT_SECRET,
        },
        auto_refresh_url=TOKEN_URL,
        token_updater=token_updater)

def serverNameGen(*args, **kwargs):
    if 'server_id' not in session: return 'You aren\'t supposed to be here'
    return [{'text': str(servers.find_one({"server_id":session.get('server_id')}).get("name")), 'url': '.'}]

@app.route('/')
@flask_breadcrumbs.register_breadcrumb(app, '.', 'Dashboard')
def index(redir=None):
    scope = request.args.get(
        'scope',
        'identify')
    #discord = make_session(scope=scope.split(' '))
    #authorization_url = discord.authorization_url(AUTHORIZATION_BASE_URL)
    #session['oauth2_state'] = state
    if redir: session['redirect'] = redir
    if 'user_id' not in session:
        return redirect('https://discordapp.com/api/oauth2/authorize?client_id={}&redirect_uri={}&response_type=code&scope={}'.format(OAUTH2_CLIENT_ID, OAUTH2_REDIRECT_URI, scope))
    else:
        return redirect(url_for('manage'))

@app.route('/callback')
def callback(redir=None):
    if session.get('redirect'):
        redir = session.get('redirect')
        session['redirect'] = None
    if 'user_id' not in session:
        if request.values.get('error'):
            return request.values['error']
        discord = make_session()
        token = discord.fetch_token(
            TOKEN_URL,
            client_secret=OAUTH2_CLIENT_SECRET,
            authorization_response=request.url)
        session['oauth2_token'] = token
        discord = make_session(token=session.get('oauth2_token'))
        user = discord.get(API_BASE_URL + '/users/@me').json()
        session['user_id'] = user.get('id')
        session.permanent = True
        if redir is None: return callback(request.url)
        else: return callback(redir)
    #if redir is None: redir = request.url
    #if request.path == '/' or request.path == '/callback': return redirect(url_for('.manage'))
    if redir: return redirect(redir)
    else: return redirect(url_for('.manage'))

def EnsureVerification(id):
    '''Check if the user is authorized to proceed to editing a server'''
    discord = make_session(token=session.get('oauth2_token'))
    if 'user_id' not in session: return False
    return id in [server.get('server_id') for server in iter(users.find_one({"user_id": int(session['user_id'])}).get('servers'))] and discord.get(API_BASE_URL + '/users/@me').json().get('id') is not None or int(session['user_id']) == 247412852925661185

def ReRoute(redir=None):
    '''If a user isn't authorized to edit a server, determine what to do: send back to login to Discord or send to homepage'''
    if 'user_id' not in session:
        if redir: session['redirect'] = redir
        return url_for('index')
    else:
        return url_for('manage')

@app.route('/manage')
@flask_breadcrumbs.register_breadcrumb(app, '.manage', 'Select a Server')
def manage():
    discord = make_session(token=session.get('oauth2_token'))
    try:
        user = discord.get(API_BASE_URL + '/users/@me').json()
        shared = users.find_one({"user_id": int(user.get("id"))}).get("servers")
    except:
        session.clear()
        return redirect(url_for('index')) #If the website can't load servers
    return render_template('homepage.html', servers=shared, user=user.get("username"))

@app.route('/manage/<int:id>/')
@flask_breadcrumbs.register_breadcrumb(app, '.manage.id.', '', dynamic_list_constructor=serverNameGen)
def manageServer(id):
    if EnsureVerification(id):
        session['server_id'] = id
        return render_template('trio.html', server=id)
    else:
        return redirect(ReRoute(request.url))

@app.route('/manage/<int:id>/server', methods=['GET', 'POST'])
@flask_breadcrumbs.register_breadcrumb(app, '.manage.id.server', 'General Server Settings')
def server(id):
    if not EnsureVerification(id):
        return redirect(ReRoute(request.url))
    serv = servers.find_one({"server_id": id})
    d = (datetime.datetime.utcnow() + datetime.timedelta(hours=serv.get('offset'))).strftime('%Y-%m-%dT%H:%M')
    d2 = serv.get('birthdate').strftime('%H:%M')
    if request.method == 'POST':
        r = request.form
        d = datetime.datetime.utcnow()
        o = r.get('offset')
        bd = r.get('birthday')
        bdt = r.get('birthdate')
        nz = r.get('tzname')
        dt = datetime.datetime(int(o[:o.find('-')]), int(o[o.find('-')+1:o.find('-')+3]), int(o[o.find('-')+4:o.find('-')+6]), int(o[o.find('T')+1:o.find(':')]), int(o[o.find(':')+1:]))
        decrement = int(bdt[bdt.find(':')+1:])
        while decrement % 5 != 0: decrement -= 1
        dt2 = datetime.datetime(2020, 1, 1, int(bdt[:bdt.find(':')]), decrement)
        if dt > d: difference = round((dt - d).seconds/3600)
        else: difference = round((dt - d).seconds/3600) - 24
        servers.update_one({"server_id": id}, {"$set": {"prefix": r.get('prefix'), 'offset': difference, 'tzname': nz, 'jumpContext': r.get('jumpContext').lower() == 'true', 'birthday': int(bd), 'birthdate': dt2,
        'birthdayMode': int(r.get('birthdayMode'))}})
        return redirect(url_for('server', id=id)) 
    return render_template('general.html', servObj=serv, date=d, date2=d2, id=id)

@app.route('/manage/<int:id>/antispam', methods=['GET', 'POST'])
@flask_breadcrumbs.register_breadcrumb(app, '.manage.id.antispam', 'Antispam')
def antispam(id):
    if not EnsureVerification(id):
        return redirect(ReRoute(request.url))
    servObj = servers.find_one({"server_id": id})
    if request.method == 'POST':
        r = request.form
        antispam = servObj.get("antispam")
        if antispam.get('warn') != int(r.get('warn')): database.UpdateMemberWarnings(id, int(r.get('warn')))
        cex = list(map(int, r.getlist('channelExclusions'))) #HTML forms pass data as strings, but we need ints
        rex = list(map(int, r.getlist('roleExclusions'))) #rex = (R)ole(Ex)clusions
        mex = list(map(int, r.getlist('memberExclusions')))
        profane = antispam.get("filter")
        for word in r.getlist('removeCensorWords'):
            profane.remove(word)
        profane.extend(r.get('addCensorWords').split(', '))
        for w in profane:
            if len(w) < 1:
                profane.remove(w) #Remove empty words, if they exist
        servers.update_one({"server_id": id}, {"$set": {"antispam": { #Save and convert values for DB
            "enabled": r.get('enabled').lower() == 'true',
            "whisper": r.get("whisper").lower() == 'true',
            "log": [None if r.get("log").lower() == "none" or r.get("log") is None else [a.get("name") for a in iter(servObj.get("channels")) if a.get('id') == int(r.get("log"))][0], None if r.get('log').lower() == "none" else int(r.get("log"))],
            "warn": int(r.get("warn")),
            "delete": r.get("delete").lower() == 'true',
            "muteTime": int(float(r.get("muteTime"))) * 60,
            "action": int(r.get("action")),
            "customRoleID": None if r.get("customRoleID").lower() == "none" or r.get("customRoleID") is None else int(r.get("customRoleID")),
            "congruent": [int(r.get("congruent0")), int(r.get("congruent1")), int(float(r.get("congruent2"))) * 60],
            "emoji": int(r.get("emoji")),
            "mentions": int(r.get("mentions")),
            "selfbot": r.get("selfbot").lower() == 'true',
            "caps": float(r.get("caps")),
            "links": r.get("links").lower() == 'false',
            'attachments': [r.get('attachmentAttachment'), r.get('mediaAttachment'), r.get('uncommonAttachment'), r.get('imageAttachment'), r.get('audioAttachment'), r.get('videoAttachment'), r.get('staticAttachment'), r.get('gifAttachment'), r.get('tieAttachment')],
            "invites": r.get("invites").lower() == 'false',
            "everyoneTags": int(r.get("everyoneTags")),
            "hereTags": int(r.get("hereTags")),
            "roleTags": int(r.get('roleTags')),
            "quickMessages": [int(r.get("quickMessages0")), int(r.get("quickMessages1"))],
            'consecutiveMessages': [int(r.get('consecutiveMessages0')), int(r.get('consecutiveMessages1'))],
            'repeatedJoins': [int(r.get('repeatedJoinsCountValue')), int(r.get('repeatedJoinsThresholdValue')) * int(r.get('repeatedJoinsThresholdDividend')), int(r.get('repeatedJoinsBanValue')) * int(r.get('repeatedJoinsBanDividend'))] if r.get('repeatedJoinsEnabled') else [0, 0, 0],
            'ageKick': int(r.get('ageKickValue')) if r.get('ageKickEnabled') else None,
            "ignoreRoled": r.get("ignoreRoled").lower() == 'true',
            "exclusionMode": int(r.get('exclusionMode')),
            "channelExclusions": cex,
            "roleExclusions": rex,
            "memberExclusions": mex,
            "profanityEnabled": r.get('profanityEnabled').lower() == 'true',
            "profanityTolerance": float(r.get("profanityTolerance")) / 100,
            "filter": profane}}})
        return redirect(url_for('antispam', id=id))
    return render_template('antispam.html', servid = id, servObj=servObj, automod = servObj.get("antispam"), channels=servObj.get("channels"), roles=servObj.get("roles"), members=servObj.get("members"))

@app.route('/manage/<int:id>/moderation')
@flask_breadcrumbs.register_breadcrumb(app, '.manage.id.moderation', 'Moderation')
def moderation(id):
    return "This feature will be available later!"
    

@app.route('/manage/<int:id>/cyberlog', methods=['GET', 'POST'])
@flask_breadcrumbs.register_breadcrumb(app, '.manage.id.cyberlog', 'Cybersecurity/Logging')
def cyberlog(id):
    if not EnsureVerification(id):
        return redirect(ReRoute(request.url))
    servObj = servers.find_one({"server_id": id})
    if request.method == 'POST':
        r = request.form
        cex = list(map(int, r.getlist('channelExclusions'))) #HTML forms pass data as strings, but we need ints
        rex = list(map(int, r.getlist('roleExclusions'))) #rex = (R)ole(Ex)clusions
        mex = list(map(int, r.getlist('memberExclusions')))
        c = servObj.get("cyberlog")
        servers.update_one({"server_id": id}, {"$set": {"cyberlog": {
        "enabled": r.get('enabled').lower() == 'true',
        "image": r.get('imageLogging').lower() == 'true',
        "defaultChannel": None if r.get('defaultChannel').lower() == 'none' or r.get('defaultChannel') is None else int(r.get('defaultChannel')),
        'memberGlobal': int(r.get('memberGlobal')),
        #'summarize': int(r.get('summarize')),
        'onlyVCJoinLeave': True if r.get('voiceSpecial') == '0' else False,
        'onlyVCForceActions': True if r.get('voiceSpecial') == '1' else False,
        'voiceChatLogRecaps': r.get('voiceRecaps').lower() == 'true',
        "channelExclusions": cex,
        "roleExclusions": rex,
        "memberExclusions": mex,
        "message": {
            "name": c.get('message').get('name'),
            "description": c.get('message').get('description'),
            "embed": c.get('message').get('embed'),
            "read": r.get('messageRead').lower() == 'true',
            "enabled": r.get('message').lower() == 'true',
            "channel": None if r.get('messageChannel').lower() == 'none' or r.get('messageChannel') is None else int(r.get('messageChannel')),
            #'summarize': int(r.get('messageSummarize')),
            "color": c.get('message').get('color'),
            "advanced": c.get('message').get('advanced')},
        "doorguard": {
            "name": c.get('doorguard').get('name'),
            "description": c.get('doorguard').get('description'),
            "embed": c.get('doorguard').get('embed'),
            "read": r.get('doorRead').lower() == 'true',
            "enabled": r.get('doorguard').lower() == 'true',
            "channel": None if r.get('doorChannel').lower() == 'none' or r.get('doorChannel') is None else int(r.get('doorChannel')),
            #'summarize': int(r.get('doorSummarize')),
            "color": c.get('doorguard').get('color'),
            "advanced": c.get('doorguard').get('advanced')},
        "server": {
            "name": c.get('server').get('name'),
            "description": c.get('server').get('description'),
            "embed": c.get('server').get('embed'),
            "read": r.get('serverRead').lower() == 'true',
            "enabled": r.get('server').lower() == 'true',
            "channel": None if r.get('serverChannel').lower() == 'none' or r.get('serverChannel') is None else int(r.get('serverChannel')),
            #'summarize': int(r.get('serverSummarize')),
            "color": c.get('server').get('color'),
            "advanced": c.get('server').get('advanced')},
        "channel": {
            "name": c.get('channel').get('name'),
            "description": c.get('channel').get('description'),
            "embed": c.get('channel').get('embed'),
            "read": r.get('channelRead').lower() == 'true',
            "enabled": r.get('channel').lower() == 'true',
            "channel": None if r.get('channelChannel').lower() == 'none' or r.get('channelChannel') is None else int(r.get('channelChannel')),
            #'summarize': int(r.get('channelSummarize')),
            "color": c.get('channel').get('color'),
            "advanced": c.get('channel').get('advanced')},
        "member": {
            "name": c.get('member').get('name'),
            "description": c.get('member').get('description'),
            "embed": c.get('member').get('embed'),
            "read": r.get('memberRead').lower() == 'true',
            "enabled": r.get('member').lower() == 'true',
            "channel": None if r.get('memberChannel').lower() == 'none' or r.get('memberChannel') is None else int(r.get('memberChannel')),
            #'summarize': int(r.get('memberSummarize')),
            "color": c.get('member').get('color'),
            "advanced": c.get('member').get('advanced')},
        "role": {
            "name": c.get('role').get('name'),
            "description": c.get('role').get('description'),
            "embed": c.get('role').get('embed'),
            "read": r.get('roleRead').lower() == 'true',
            "enabled": r.get('role').lower() == 'true',
            "channel": None if r.get('roleChannel').lower() == 'none' or r.get('roleChannel') is None else int(r.get('roleChannel')),
            #'summarize': int(r.get('roleSummarize')),
            "color": c.get('role').get('color'),
            "advanced": c.get('role').get('advanced')},
        "emoji": {
            "name": c.get('emoji').get('name'),
            "description": c.get('emoji').get('description'),
            "embed": c.get('emoji').get('embed'),
            "read": r.get('emojiRead').lower() == 'true',
            "enabled": r.get('emoji').lower() == 'true',
            "channel": None if r.get('emojiChannel').lower() == 'none' or r.get('emojiChannel') is None else int(r.get('emojiChannel')),
            #'summarize': int(r.get('emojiSummarize')),
            "color": c.get('emoji').get('color'),
            "advanced": c.get('emoji').get('advanced')},
        "voice": {
            "name": c.get('voice').get('name'),
            "description": c.get('voice').get('description'),
            "embed": c.get('voice').get('embed'),
            "read": r.get('voiceRead').lower() == 'true',
            "enabled": r.get('voice').lower() == 'true',
            "channel": None if r.get('voiceChannel').lower() == 'none' or r.get('voiceChannel') is None else int(r.get('voiceChannel')),
            #'summarize': int(r.get('voiceSummarize')),
            "color": c.get('voice').get('color'),
            "advanced": c.get('voice').get('advanced')}}}})
        return redirect(url_for('cyberlog', id=id))
    return render_template('cyberlog.html', servid=id, server=servObj, cyberlog=servObj.get("cyberlog"), channels=servObj.get("channels"), roles=servObj.get("roles"), members=servObj.get("members"))

@app.route('/special/<string:landing>')
def specialLanding(landing):
    variables = {}
    #disguard = db.disguard.find_one({})
    disguard = mongo.disguard.disguard.find_one({})
    if landing == 'kaileyBirthday2020': #When multiple pages requiring verification exist, change to a tuple. This if statement forces user verification for those navigating to the page.
        discord = make_session(token=session.get('oauth2_token'))
        if 'user_id' in session and discord.get(API_BASE_URL + '/users/@me').json().get('id'):
            if landing == 'kaileyBirthday2020':
                variables['kailey'] = int(session['user_id']) in [596381991151337482, 247412852925661185]
        else: return redirect(ReRoute(request.url))
    del disguard['_id']
    d = json.loads(json.dumps(disguard, default=jsonFormatter))
    if landing == 'timeKeeper': 
        variables['keeperData'] = d['keeperData']
        variables['time'] = time(disguard['keeperData'])
    return render_template(f'{landing}.html', disguard=d, vars=variables)

def jsonFormatter(o):
    if type(o) is datetime.datetime: return o.isoformat()

def time(data):
    '''Returns the time in sped-up terms (TIMEKEEPER)'''
    return (data["virtualEpoch"] + elapsed(data) + datetime.timedelta(hours=data["hoursFromUTC"])).isoformat()

def elapsed(data):
    '''Returns time elapsed since the epoch (return type: datetime.timedelta) (TIMEKEEPER)'''
    #Jan 19, 2021: Changed this approach from being single-line math to being start at a point & add it linearly, based on the new data type system. This eliminates the need for the pauseCompensation method.
    result = 0
    speedSectors = data['speedSectors']
    if len(speedSectors) < 2: return datetime.timedelta(seconds=0)
    for i, s in enumerate(speedSectors, 1):
        lastIndex = speedSectors[i - 1]['timestamp']
        multiplier = speedSectors[i - 1]['multiplier']
        if i == len(speedSectors): currentIndex = datetime.datetime.utcnow()
        else: currentIndex = s['timestamp']
        result += (currentIndex - lastIndex).seconds * multiplier
    return datetime.timedelta(seconds=result)
    #return ((datetime.datetime.utcnow() - data['epoch'] - datetime.timedelta(seconds=data['pausedDuration'])) - (datetime.datetime.utcnow() - data['pausedTimestamp'] if data['paused'] else datetime.timedelta(seconds=0))) * data['timeMultiplier']


if __name__ == '__main__':
    app.run()
