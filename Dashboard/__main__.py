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
        #bd = r.get('birthday')
        bdt = r.get('birthdate')
        #nz = r.get('tzname')
        dt = datetime.datetime(int(o[:o.find('-')]), int(o[o.find('-')+1:o.find('-')+3]), int(o[o.find('-')+4:o.find('-')+6]), int(o[o.find('T')+1:o.find(':')]), int(o[o.find(':')+1:]))
        decrement = int(bdt[bdt.find(':')+1:])
        while decrement % 5 != 0: decrement -= 1
        dt2 = datetime.datetime(2020, 1, 1, int(bdt[:bdt.find(':')]), decrement)
        if dt > d: difference = round((dt - d).seconds/3600)
        else: difference = round((dt - d).seconds/3600) - 24
        servers.update_one({"server_id": id}, {"$set": {
            "prefix": r.get('prefix'),
            'offset': difference,
            'tzname': r.get('tzname'),
            'jumpContext': r.get('jumpContext').lower() == 'true',
            'undoSuppression': r.get('undoSuppression').lower() == 'true',
            'redditComplete': r.get('redditComplete').lower() == 'true',
            'redditEnhance': int(r.get('redditEnhance')),
            'colorTheme': int(r.get('colorTheme')),
            'birthday': int(r.get('birthday')),
            'birthdate': dt2,
            'birthdayMode': int(r.get('birthdayMode')),
            'generalChannel': (int(r.get('generalChannel')), int(r.get('generalChannel')) != 0),
            'announcementsChannel': (int(r.get('announcementsChannel')), int(r.get('announcementsChannel')) != 0),
            'moderatorChannel': (int(r.get('moderatorChannel')), int(r.get('moderatorChannel')) != 0),
            'redditFeeds': [{
                'subreddit': r.getlist('subName')[i],
                'channel': int(r.getlist('subChannel')[i]),
                'truncateTitle': int(r.getlist('subTruncateTitle')[i]),
                'truncateText': int(r.getlist('subTruncateText')[i]),
                'media': int(r.getlist('subMedia')[i]),
                'creditAuthor': int(r.getlist('subCreditAuthor')[i]),
                'color': 'colorCode' if r.getlist('subColor')[i] == 'colorCode' else r.getlist('subCustomColor')[i],
                'timestamp': r.getlist('subTimestamp')[i].lower() == 'true',
            } for i in range(len(r.getlist('subName'))) if not r.getlist('delete')[i] == '1' and i != 0]
            }})
        return redirect(url_for('server', id=id))
    feeds = [{'template': True, 'subreddit': 'placeholder', 'channel': serv['channels'][1]['id'], 'truncateTitle': 100, 'truncateText': 400, 'media': 3, 'creditAuthor': 3, 'color': 'colorCode', 'timestamp': True}] + serv.get('redditFeeds', [])
    return render_template('general.html', servObj=serv, redditFeeds=feeds, date=d, date2=d2, id=id, redesign=True)

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
    return render_template('antispam.html', servid = id, servObj=servObj, automod = servObj.get("antispam"), channels=servObj.get("channels"), roles=servObj.get("roles"), members=servObj.get("members"), redesign=False)

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
        def boolConverter(input): return None if input == None else bool(input)
        moduleDict = {}
        for w in ['message', 'doorguard', 'server', 'channel', 'member', 'role', 'emoji', 'voice', 'misc']:
            moduleDict[w] = {
                'name': c[w]['name'], 'description': c[w]['description'], 'enabled': r.get(w) == 'True', 'channel': r.get(f'{w}Channel', type=int),
                'read': boolConverter(r.get(f'{w}read', None, type=int)),'library': r.get(f'{w}Library', None, type=int),
                'thumbnail': r.get(f'{w}Thumbnail', None, type=int), 'author': r.get(f'{w}Author', None, type=int),
                'context': (r.get(f'{w}TitleContext', None, type=int), r.get(f'{w}DescContext', None, type=int)), 'hoverLinks': None,
                'embedTimestamp': r.get(f'{w}EmbedTimestamp', None, type=int), 'botLogging': r.get(f'{w}BotLogging', None, type=int),
                'color': None if r.get(f'{w}Color') == 'default' else ['auto', 'auto', 'auto'] if r.get(f'{w}Color') == 'auto' else [r.get(f'{w}CreateColor'), r.get(f'{w}UpdateColor'), r.get(f'{w}DeleteColor')],
                'plainText': boolConverter(r.get(f'{w}PlainText', None, type=int)), 'flashText': boolConverter(r.get(f'{w}FlashText', None, type=int)),
                'tts': boolConverter(r.get(f'{w}TTS', None, type=int))}
        servers.update_one({"server_id": id}, {"$set": {"cyberlog": {
        "enabled": r.get('enabled').lower() == 'true',
        'ghostReactionEnabled': r.get('ghostReactionEnabled') == '1',
        'disguardLogRecursion': r.get('disguardLogRecursion') == '1',
        "image": r.get('imageLogging').lower() == 'true',
        "defaultChannel": r.get('defaultChannel', None, type=int),
        'library': r.get('defaultLibrary', type=int),
        'thumbnail': r.get('defaultThumbnail', type=int),
        'author': r.get('defaultAuthor', type=int),
        'context': (r.get('defaultTitleContext', type=int), r.get('defaultDescContext', type=int)),
        'hoverLinks': c.get('hoverlinks'),
        'embedTimestamp': r.get('defaultEmbedTimestamp', type=int),
        'botLogging': r.get('defaultBotLogging', type=int),
        'color': ['auto', 'auto', 'auto'] if r.get('defaultColor') == 'auto' else [r.get('defaultCreateColor'), r.get('defaultUpdateColor'), r.get('defaultDeleteColor')],
        'plainText': r.get('defaultPlainText') == '1',
        'read': r.get('read') == '1',
        'flashText': r.get('defaultFlashText') == '1',
        'tts': r.get('defaultTTS') == '1',
        'memberGlobal': r.get('memberGlobal', type=int),
        'onlyVCJoinLeave': True if r.get('voiceSpecial') == '0' else False,
        'onlyVCForceActions': True if r.get('voiceSpecial') == '1' else False,
        'voiceChatLogRecaps': r.get('voiceRecaps').lower() == 'true',
        'ghostReactionTime': r.get('ghostReactionTime', type=int),
        "channelExclusions": cex,
        "roleExclusions": rex,
        "memberExclusions": mex,
        "message": moduleDict['message'],
        'doorguard': moduleDict['doorguard'],
        'server': moduleDict['server'],
        'channel': moduleDict['channel'],
        'member': moduleDict['member'],
        'role': moduleDict['role'],
        'emoji': moduleDict['emoji'],
        'voice': moduleDict['voice'],
        'misc': moduleDict['misc']}}})
        return redirect(url_for('cyberlog', id=id))
    return render_template('cyberlog.html', servid=id, server=servObj, cyberlog=servObj.get("cyberlog"), channels=servObj.get("channels"), roles=servObj.get("roles"), members=servObj.get("members"), redesign=False)

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
    '''Returns time elapsed since the epoch (return type: datetime.timedelta)'''
    #Jan 19, 2021: Changed this approach from being single-line math to being start at a point & add it linearly, based on the new data type system. This eliminates the need for the pauseCompensation method.
    result = 0
    speedSectors = data.get('speedSectors')
    if len(speedSectors) < 2: return datetime.timedelta(seconds=0)
    for i, s in enumerate(speedSectors, 1):
        try: lastIndex = datetime.datetime.fromisoformat(s['timestamp'])
        except TypeError: lastIndex = s['timestamp']
        multiplier = s['multiplier']
        if i == len(speedSectors): currentIndex = datetime.datetime.utcnow()
        else: 
            try: currentIndex = datetime.datetime.fromisoformat(speedSectors[i]['timestamp'])
            except TypeError: currentIndex = speedSectors[i]['timestamp']
        result += (currentIndex - lastIndex).total_seconds() * multiplier
    return datetime.timedelta(seconds=result)
    #return ((datetime.datetime.utcnow() - bot.data['epoch'] - datetime.timedelta(seconds=bot.data['pausedDuration'])) - (datetime.datetime.utcnow() - bot.data['pausedTimestamp'] if bot.data['paused'] else datetime.timedelta(seconds=0))) * bot.data['timeMultiplier']


if __name__ == '__main__':
    app.run()
