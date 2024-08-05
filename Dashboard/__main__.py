import datetime
import json

import flask_breadcrumbs
import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery
import pymongo
from flask import Flask, redirect, render_template, request, session, url_for

import authentication
import database
import oauth

REDIRECT_URI = 'https://disguard.herokuapp.com/callback'
DEV_REDIRECT_URI = 'http://localhost:5000/callback'

app = Flask(__name__)
flask_breadcrumbs.Breadcrumbs(app=app)

app.debug = True
app.config['SECRET_KEY'] = oauth.Oauth('discord').client_secret
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(days=30)

mongo = pymongo.MongoClient(oauth.mongo())
db = mongo.disguard
db = mongo.disguard_beta if app.debug else mongo.disguard
servers = db.servers
users = db.users


def token_updater(token):
    session['oauth2_token'] = token


def serverNameGen(*args, **kwargs):
    if 'server_id' not in session:
        return "You aren't supposed to be here"
    return [{'text': str(servers.find_one({'server_id': session.get('server_id')}).get('name')), 'url': '.'}]


def credentials_to_dict(credentials: google.oauth2.credentials.Credentials):
    return {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes,
    }


@app.route('/')
@flask_breadcrumbs.register_breadcrumb(app, '.', 'Dashboard')
def index(redir=None):
    if redir:
        session['redirect'] = redir
    if 'user_id' not in session:
        return redirect(url_for('authenticate'))
    else:
        return redirect(url_for('manage'))


@app.route('/authenticate')
def authenticate(redir=None, services=['Discord']):
    if redir:
        session['redirect'] = redir
    if session.get('redirect') and '/special' in session['redirect']:
        services = ['Discord', 'Google']
    if 'identity' not in session:
        return render_template('authenticate.html', services=services)
    else:
        return redirect(url_for('manage'))


@app.route('/authenticate/<string:service>/')
def authenticate_service(service):
    if service == 'discord':
        credentials = oauth.Oauth(service=service)
        oAuth = authentication.OAuth2Handler(
            service=service,
            CLIENT_ID=credentials.client_id,
            CLIENT_SECRET=credentials.client_secret,
            REDIRECT_URI=DEV_REDIRECT_URI if app.debug else REDIRECT_URI,
            API_BASE_URL='https://discordapp.com/api',
        )
        oAuth.setup(token_updater=token_updater)
        authorization_url = oAuth.authorization_url(scope='identify')
    elif service == 'google':
        credentials = oauth.Oauth(service=service)
        flow: google_auth_oauthlib.flow.Flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file('credentials.json', scopes=[credentials.scope])
        flow.redirect_uri = DEV_REDIRECT_URI if app.debug else REDIRECT_URI
        authorization_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true')
        oAuth = authentication.OAuth2Handler(
            service=service,
            CLIENT_ID=credentials.client_id,
            CLIENT_SECRET=credentials.client_secret,
            REDIRECT_URI=DEV_REDIRECT_URI if app.debug else REDIRECT_URI,
            API_BASE_URL='https://www.googleapis.com/oauth2/v3',
        )
        session['state'] = state
    else:
        return redirect(url_for('authenticate'))
    session['service'] = service
    return redirect(authorization_url)


@app.route('/callback')
def callback(redir=None):
    if session.get('redirect'):
        redir = session.get('redirect')
        session.pop('redirect')
    if 'identity' not in session:
        if request.values.get('error'):
            return request.values['error']
        credentials = oauth.Oauth(service=session['service'])
        if session['service'] == 'discord':
            oAuth = authentication.OAuth2Handler(
                service=session['service'],
                CLIENT_ID=credentials.client_id,
                CLIENT_SECRET=credentials.client_secret,
                REDIRECT_URI=DEV_REDIRECT_URI if app.debug else REDIRECT_URI,
                API_BASE_URL='https://discordapp.com/api',
            )
            flow = oAuth.make_session()
            token = flow.fetch_token(oAuth.TOKEN_URL, client_secret=oAuth.CLIENT_SECRET, authorization_response=request.url)
            session['oauth2_token'] = token
            flow = oAuth.make_session(token=session.get('oauth2_token'))
            user = flow.get(oAuth.API_BASE_URL + '/users/@me').json()
            session['user_id'], session['identity'], session['username'] = int(user.get('id')), int(user.get('id')), user.get('username')
        else:
            flow: google_auth_oauthlib.flow.Flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
                'credentials.json', scopes=None, state=session['state']
            )
            oAuth = authentication.OAuth2Handler(
                service=session['service'],
                CLIENT_ID=credentials.client_id,
                CLIENT_SECRET=credentials.client_secret,
                REDIRECT_URI=DEV_REDIRECT_URI if app.debug else REDIRECT_URI,
                API_BASE_URL='https://www.googleapis.com/oauth2/v3',
            )
            flow.redirect_uri = DEV_REDIRECT_URI if app.debug else REDIRECT_URI
            flow.fetch_token(code=request.args.get('code'), authorization_response=request.url)
            session['credentials'] = credentials_to_dict(flow.credentials)
            session['oath2_token'] = flow.credentials.token
            user = flow.oauth2session.get(oAuth.API_BASE_URL + '/userinfo').json()
            session['identity'], session['username'] = user['email'], user['email']
        session.permanent = True
        # if redir is None: return callback(request.url)
        # else: return callback(redir)
    # if redir is None: redir = request.url
    # if request.path == '/' or request.path == '/callback': return redirect(url_for('.manage'))
    if redir:
        return redirect(redir)
    else:
        return redirect(url_for('.manage'))


@app.route('/logout/')
def logout():
    session.clear()
    return redirect(request.args.get('redir'))


def EnsureVerification(id):
    """Check if the user is authorized to proceed to editing a server"""
    credentials = oauth.Oauth('discord')
    oAuth = authentication.OAuth2Handler('discord', credentials.client_id, credentials.client_secret, API_BASE_URL='https://discordapp.com/api')
    discord = oAuth.make_session(token=session.get('oauth2_token'))
    if 'user_id' not in session:
        return False
    return (
        id in [server.get('server_id') for server in iter(users.find_one({'user_id': int(session['user_id'])}).get('servers'))]
        and discord.get(oAuth.API_BASE_URL + '/users/@me').json().get('id') is not None
        or int(session['user_id']) == 247412852925661185
    )


def ReRoute(redir=None):
    """If a user isn't authorized to edit a server, determine what to do: send back to login to Discord or send to homepage"""
    if 'user_id' not in session:
        if redir:
            session['redirect'] = redir
        session.modified = True
        return url_for('index')
    else:
        return url_for('manage')


@app.route('/manage')
@flask_breadcrumbs.register_breadcrumb(app, '.manage', 'Select a Server')
def manage():
    if 'user_id' not in session:
        return redirect(url_for('authenticate'))
    credentials = oauth.Oauth('discord')
    oAuth = authentication.OAuth2Handler('discord', credentials.client_id, credentials.client_secret, API_BASE_URL='https://discordapp.com/api')
    discord = oAuth.make_session(token=session.get('oauth2_token'))
    user = discord.get(oAuth.API_BASE_URL + '/users/@me').json()
    shared = users.find_one({'user_id': int(user.get('id'))}).get('servers')
    return render_template('homepage.html', servers=shared, user=user.get('username'))


@app.route('/manage/<int:id>/')
@flask_breadcrumbs.register_breadcrumb(app, '.manage.id.', '', dynamic_list_constructor=serverNameGen)
def manageServer(id):
    if EnsureVerification(id):
        session['server_id'] = id
        session.modified = True
        return render_template('trio.html', server=id)
    else:
        return redirect(ReRoute(request.url))


@app.route('/manage/<int:id>/server', methods=['GET', 'POST'])
@flask_breadcrumbs.register_breadcrumb(app, '.manage.id.server', 'General Server Settings')
def server(id):
    if not EnsureVerification(id):
        return redirect(ReRoute(request.url))
    serv = servers.find_one({'server_id': id})
    d = (datetime.datetime.utcnow() + datetime.timedelta(hours=serv.get('offset'))).strftime('%Y-%m-%dT%H:%M')
    d2 = serv.get('birthdate').strftime('%H:%M')
    if request.method == 'POST':
        r = request.form
        d = datetime.datetime.utcnow()
        o = r.get('offset')
        # bd = r.get('birthday')
        bdt = r.get('birthdate')
        # nz = r.get('tzname')
        redEn = int(r.get('redditEnhance'))
        dt = datetime.datetime(
            int(o[: o.find('-')]),
            int(o[o.find('-') + 1 : o.find('-') + 3]),
            int(o[o.find('-') + 4 : o.find('-') + 6]),
            int(o[o.find('T') + 1 : o.find(':')]),
            int(o[o.find(':') + 1 :]),
        )
        decrement = int(bdt[bdt.find(':') + 1 :])
        while decrement % 5 != 0:
            decrement -= 1
        dt2 = datetime.datetime(2020, 1, 1, int(bdt[: bdt.find(':')]), decrement)
        if dt > d:
            difference = round((dt - d).seconds / 3600)
        else:
            difference = round((dt - d).seconds / 3600) - 24
        servers.update_one(
            {'server_id': id},
            {
                '$set': {
                    'prefix': r.get('prefix'),
                    'offset': difference,
                    'tzname': r.get('tzname'),
                    'jumpContext': r.get('jumpContext').lower() == 'true',
                    'undoSuppression': r.get('undoSuppression').lower() == 'true',
                    'redditComplete': r.get('redditComplete').lower() == 'true',
                    'redditEnhance': (False, False) if redEn == 0 else (False, True) if redEn == 1 else (True, False) if redEn == 2 else (True, True),
                    'colorTheme': int(r.get('colorTheme')),
                    'birthday': int(r.get('birthday')),
                    'birthdate': dt2,
                    'birthdayMode': int(r.get('birthdayMode')),
                    'generalChannel': (int(r.get('generalChannel')), int(r.get('generalChannel')) != 0),
                    'announcementsChannel': (int(r.get('announcementsChannel')), int(r.get('announcementsChannel')) != 0),
                    'moderatorChannel': (int(r.get('moderatorChannel')), int(r.get('moderatorChannel')) != 0),
                    'redditFeeds': [
                        {
                            'subreddit': r.getlist('subName')[i],
                            'channel': int(r.getlist('subChannel')[i]),
                            'truncateTitle': int(r.getlist('subTruncateTitle')[i]),
                            'truncateText': int(r.getlist('subTruncateText')[i]),
                            'media': int(r.getlist('subMedia')[i]),
                            'creditAuthor': int(r.getlist('subCreditAuthor')[i]),
                            'color': 'colorCode' if r.getlist('subColor')[i] == 'colorCode' else r.getlist('subCustomColor')[i],
                            'timestamp': r.getlist('subTimestamp')[i].lower() == 'true',
                        }
                        for i in range(len(r.getlist('subName')))
                        if not r.getlist('delete')[i] == '1' and i != 0
                    ],
                }
            },
        )
        return redirect(url_for('server', id=id))
    feeds = [
        {
            'template': True,
            'subreddit': 'placeholder',
            'channel': serv['channels'][1]['id'],
            'truncateTitle': 100,
            'truncateText': 400,
            'media': 3,
            'creditAuthor': 3,
            'color': 'colorCode',
            'timestamp': True,
        }
    ] + [feed for feed in serv.get('redditFeeds', {}).values()]
    return render_template('general.html', server=serv, redditFeeds=feeds, date=d, date2=d2, id=id, redesign=True)


@app.route('/manage/<int:id>/antispam', methods=['GET', 'POST'])
@flask_breadcrumbs.register_breadcrumb(app, '.manage.id.antispam', 'Antispam')
def antispam(id):
    if not EnsureVerification(id):
        return redirect(ReRoute(request.url))
    servObj = servers.find_one({'server_id': id})
    if request.method == 'POST':
        r = request.form
        antispam = servObj.get('antispam')
        if antispam.get('warn') != int(r.get('warn')):
            database.UpdateMemberWarnings(id, int(r.get('warn')))
        cex = list(map(int, r.getlist('channelExclusions')))  # HTML forms pass data as strings, but we need ints
        rex = list(map(int, r.getlist('roleExclusions')))  # rex = (R)ole(Ex)clusions
        mex = list(map(int, r.getlist('memberExclusions')))
        profane = antispam.get('filter')
        for word in r.getlist('removeCensorWords'):
            profane.remove(word)
        profane.extend(r.get('addCensorWords').split(', '))
        for w in profane:
            if len(w) < 1:
                profane.remove(w)  # Remove empty words, if they exist
        servers.update_one(
            {'server_id': id},
            {
                '$set': {
                    'antispam': {  # Save and convert values for DB
                        'enabled': r.get('enabled').lower() == 'true',
                        'whisper': r.get('whisper').lower() == 'true',
                        'log': [
                            None
                            if r.get('log').lower() == 'none' or r.get('log') is None
                            else [a.get('name') for a in iter(servObj.get('channels')) if a.get('id') == int(r.get('log'))][0],
                            None if r.get('log').lower() == 'none' else int(r.get('log')),
                        ],
                        'warn': int(r.get('warn')),
                        'delete': r.get('delete').lower() == 'true',
                        'muteTime': int(float(r.get('muteTime'))) * 60,
                        'action': int(r.get('action')),
                        'customRoleID': None
                        if r.get('customRoleID').lower() == 'none' or r.get('customRoleID') is None
                        else int(r.get('customRoleID')),
                        'congruent': [int(r.get('congruent0')), int(r.get('congruent1')), int(float(r.get('congruent2'))) * 60],
                        'emoji': int(r.get('emoji')),
                        'mentions': int(r.get('mentions')),
                        'selfbot': r.get('selfbot').lower() == 'true',
                        'caps': float(r.get('caps')),
                        'links': r.get('links').lower() == 'false',
                        'attachments': [
                            r.get('attachmentAttachment'),
                            r.get('mediaAttachment'),
                            r.get('uncommonAttachment'),
                            r.get('imageAttachment'),
                            r.get('audioAttachment'),
                            r.get('videoAttachment'),
                            r.get('staticAttachment'),
                            r.get('gifAttachment'),
                            r.get('tieAttachment'),
                        ],
                        'invites': r.get('invites').lower() == 'false',
                        'everyoneTags': int(r.get('everyoneTags')),
                        'hereTags': int(r.get('hereTags')),
                        'roleTags': int(r.get('roleTags')),
                        'quickMessages': [int(r.get('quickMessages0')), int(r.get('quickMessages1'))],
                        'consecutiveMessages': [int(r.get('consecutiveMessages0')), int(r.get('consecutiveMessages1'))],
                        'repeatedJoins': [
                            int(r.get('repeatedJoinsCountValue')),
                            int(r.get('repeatedJoinsThresholdValue')) * int(r.get('repeatedJoinsThresholdDividend')),
                            int(r.get('repeatedJoinsBanValue')) * int(r.get('repeatedJoinsBanDividend')),
                        ]
                        if r.get('repeatedJoinsEnabled')
                        else [0, 0, 0],
                        'ageKick': int(r.get('ageKickValue')) if r.get('ageKickEnabled') else None,
                        'ignoreRoled': r.get('ignoreRoled').lower() == 'true',
                        'exclusionMode': int(r.get('exclusionMode')),
                        'channelExclusions': cex,
                        'roleExclusions': rex,
                        'memberExclusions': mex,
                        'profanityEnabled': r.get('profanityEnabled').lower() == 'true',
                        'profanityTolerance': float(r.get('profanityTolerance')) / 100,
                        'filter': profane,
                    }
                }
            },
        )
        return redirect(url_for('antispam', id=id))
    return render_template(
        'antispam.html',
        servid=id,
        servObj=servObj,
        automod=servObj.get('antispam'),
        channels=servObj.get('channels'),
        roles=servObj.get('roles'),
        members=servObj.get('members'),
        redesign=False,
    )


@app.route('/manage/<int:id>/moderation')
@flask_breadcrumbs.register_breadcrumb(app, '.manage.id.moderation', 'Moderation')
def moderation(id):
    return 'This feature will be available later!'


@app.route('/manage/<int:id>/cyberlog', methods=['GET', 'POST'])
@flask_breadcrumbs.register_breadcrumb(app, '.manage.id.cyberlog', 'Logging')
def cyberlog(id):
    if not EnsureVerification(id):
        return redirect(ReRoute(request.url))
    servObj = servers.find_one({'server_id': id})
    if request.method == 'POST':
        r = request.form
        cex = list(map(int, r.getlist('channelExclusions')))  # HTML forms pass data as strings, but we need ints
        rex = list(map(int, r.getlist('roleExclusions')))  # rex = (R)ole(Ex)clusions
        mex = list(map(int, r.getlist('memberExclusions')))
        c = servObj.get('cyberlog')

        def boolConverter(input):
            return None if input is None else bool(input)

        moduleDict = {}
        for w in ['message', 'doorguard', 'server', 'channel', 'member', 'role', 'emoji', 'voice', 'misc']:
            moduleDict[w] = {
                'name': c[w]['name'],
                'description': c[w]['description'],
                'enabled': r.get(w),
                'channel': r.get(f'{w}Channel', type=int),
                'read': boolConverter(r.get(f'{w}read', None, type=int)),
                'library': r.get(f'{w}Library', None, type=int),
                'thumbnail': r.get(f'{w}Thumbnail', None, type=int),
                'author': r.get(f'{w}Author', None, type=int),
                'context': (r.get(f'{w}TitleContext', None, type=int), r.get(f'{w}DescContext', None, type=int)),
                'hoverLinks': None,
                'embedTimestamp': r.get(f'{w}EmbedTimestamp', None, type=int),
                'botLogging': r.get(f'{w}BotLogging', None, type=int),
                'color': None
                if r.get(f'{w}Color') == 'default'
                else ['auto', 'auto', 'auto']
                if r.get(f'{w}Color') == 'auto'
                else [r.get(f'{w}CreateColor'), r.get(f'{w}UpdateColor'), r.get(f'{w}DeleteColor')],
                'plainText': boolConverter(r.get(f'{w}PlainText', None, type=int)),
                'flashText': boolConverter(r.get(f'{w}FlashText', None, type=int)),
                'tts': boolConverter(r.get(f'{w}TTS', None, type=int)),
            }
        servers.update_one(
            {'server_id': id},
            {
                '$set': {
                    'cyberlog': {
                        'enabled': r.get('enabled'),
                        'ghostReactionEnabled': r.get('ghostReactionEnabled') == '1',
                        'disguardLogRecursion': r.get('disguardLogRecursion') == '1',
                        'image': r.get('imageLogging') == '1',
                        'defaultChannel': r.get('defaultChannel', None, type=int),
                        'library': r.get('defaultLibrary', type=int),
                        'thumbnail': r.get('defaultThumbnail', type=int),
                        'author': r.get('defaultAuthor', type=int),
                        'context': (r.get('defaultTitleContext', type=int), r.get('defaultDescContext', type=int)),
                        'hoverLinks': c.get('hoverlinks'),
                        'embedTimestamp': r.get('defaultEmbedTimestamp', type=int),
                        'botLogging': r.get('defaultBotLogging', type=int),
                        'color': ['auto', 'auto', 'auto']
                        if r.get('defaultColor') == 'auto'
                        else [r.get('defaultCreateColor'), r.get('defaultUpdateColor'), r.get('defaultDeleteColor')],
                        'plainText': r.get('defaultPlainText') == '1',
                        'read': r.get('read') == '1',
                        'flashText': r.get('defaultFlashText') == '1',
                        'tts': r.get('defaultTTS') == '1',
                        'memberGlobal': r.get('memberGlobal', type=int),
                        'onlyVCJoinLeave': True if r.get('voiceSpecial') == '0' else False,
                        'onlyVCForceActions': True if r.get('voiceSpecial') == '1' else False,
                        'voiceChatLogRecaps': r.get('voiceRecaps').lower() == 'true',
                        'ghostReactionTime': r.get('ghostReactionTime', type=int),
                        'channelExclusions': cex,
                        'roleExclusions': rex,
                        'memberExclusions': mex,
                        'message': moduleDict['message'],
                        'doorguard': moduleDict['doorguard'],
                        'server': moduleDict['server'],
                        'channel': moduleDict['channel'],
                        'member': moduleDict['member'],
                        'role': moduleDict['role'],
                        'emoji': moduleDict['emoji'],
                        'voice': moduleDict['voice'],
                        'misc': moduleDict['misc'],
                    }
                }
            },
        )
        return redirect(url_for('cyberlog', id=id))
    return render_template(
        'cyberlog.html',
        servid=id,
        server=servObj,
        cyberlog=servObj.get('cyberlog'),
        channels=servObj.get('channels'),
        roles=servObj.get('roles'),
        members=servObj.get('members'),
        redesign=True,
    )


@app.route('/manage/profile', methods=['GET', 'POST'])
def profile():
    # Make sure redirect works at the end
    if 'user_id' not in session:
        return redirect(ReRoute(request.url))
    uID = int(session['user_id'])
    user = users.find_one({'user_id': uID})
    credentials = oauth.Oauth(service='discord')
    if request.method == 'GET':
        oAuth = authentication.OAuth2Handler(
            service='discord',
            CLIENT_ID=credentials.client_id,
            CLIENT_SECRET=credentials.client_secret,
            REDIRECT_URI=DEV_REDIRECT_URI if app.debug else REDIRECT_URI,
            API_BASE_URL='https://discordapp.com/api',
        )
        flow = oAuth.make_session(token=session.get('oauth2_token'))
        userGet = flow.get(oAuth.API_BASE_URL + '/users/@me').json()
        user['avatar_url'] = f'https://cdn.discordapp.com/avatars/{uID}/{userGet["avatar"]}?size=2048'
    if request.method == 'POST':
        r = request.form
        updateDict = {
            'privacy': {
                'default': (int(r.get('defaultEnabled')), int(r.get('defaultVisibility'))),
                'profile': (int(r.get('profileEnabled')), int(r.get('profileVisibility'))),
                'bio': (int(r.get('bioEnabled')), int(r.get('bioVisibility'))),
                'timezone': (int(r.get('tzEnabled')), int(r.get('tzVisibility'))),
                'favColor': (int(r.get('favColorEnabled')), int(r.get('favColorVisibility'))),
                'colorTheme': (int(r.get('colorThemeEnabled')), int(r.get('colorThemeVisibility'))),
                'name': (int(r.get('nameEnabled')), int(r.get('nameVisibility'))),
                'lastOnline': (int(r.get('lastOnlineEnabled')), int(r.get('lastOnlineVisibility'))),
                'lastActive': (int(r.get('lastActiveEnabled')), int(r.get('lastActiveVisibility'))),
                'birthdayModule': (int(r.get('birthdayModuleEnabled')), int(r.get('birthdayModuleVisibility'))),
                'birthdayDay': (int(r.get('birthdayEnabled')), int(r.get('birthdayVisibility'))),
                'age': (int(r.get('ageEnabled')), int(r.get('ageVisibility'))),
                'wishlist': (int(r.get('wishlistEnabled')), int(r.get('wishlistVisibility'))),
                'birthdayMessages': (int(r.get('birthdayMessagesEnabled')), int(r.get('birthdayMessagesVisibility'))),
                'attributeHistory': (int(r.get('attributeHistoryEnabled')), int(r.get('attributeHistoryEnabled'))),
                'customStatusHistory': (int(r.get('customStatusHistoryEnabled')), int(r.get('customStatusHistoryVisibility'))),
                'usernameHistory': (int(r.get('usernameHistoryEnabled')), int(r.get('usernameHistoryVisibility'))),
                'avatarHistory': (int(r.get('avatarHistoryEnabled')), int(r.get('avatarHistoryVisibility'))),
            }
        }
        if r.get('defaultCOE') == 'on' or r.get('profileCOE') == 'on' or r.get('lastOnlineCOE') == 'on':
            updateDict.update({'lastOnline': datetime.datetime.min})
        if r.get('defaultCOE') == 'on' or r.get('profileCOE') == 'on' or r.get('lastActiveCOE') == 'on':
            updateDict.update({'lastActive': {'timestamp': datetime.datetime.min, 'reason': 'Not tracked yet'}})
        if r.get('defaultCOE') == 'on' or r.get('birthdayModuleCOE') == 'on' or r.get('birthdayCOE') == 'on':
            updateDict.update({'birthday': None})
        if r.get('defaultCOE') == 'on' or r.get('birthdayModuleCOE') == 'on' or r.get('ageCOE') == 'on':
            updateDict.update({'age': None})
        if r.get('defaultCOE') == 'on' or r.get('birthdayModuleCOE') == 'on' or r.get('wishlistCOE') == 'on':
            updateDict.update({'wishlist': []})
        if r.get('defaultCOE') == 'on' or r.get('birthdayModuleCOE') == 'on' or r.get('birthdayMessagesCOE') == 'on':
            updateDict.update({'birthdayMessages': []})
        if r.get('defaultCOE') == 'on' or r.get('attributeHistoryCOE') == 'on' or r.get('customStatusHistoryCOE') == 'on':
            updateDict.update({'customStatusHistory': []})
        if r.get('defaultCOE') == 'on' or r.get('attributeHistoryCOE') == 'on' or r.get('usernameHistoryCOE') == 'on':
            updateDict.update({'usernameHistory': []})
        if r.get('defaultCOE') == 'on' or r.get('attributeHistoryCOE') == 'on' or r.get('avatarHistoryCOE') == 'on':
            updateDict.update({'avatarHistory': []})
        users.update_one({'user_id': uID}, {'$set': updateDict})
        return redirect(url_for('profile'))
    return render_template('profile.html', user=user, userGet=userGet)


@app.route('/special/<string:landing>')
def specialLanding(landing):
    # # # authentication # # #
    # disguard = db.disguard.find_one({})
    if landing != 'timekeeper':
        if 'identity' not in session:
            session['redirect'] = request.url
            return redirect(url_for('authenticate'))
        credentials = oauth.Oauth(session['service'])
        oAuth = authentication.OAuth2Handler(
            session['service'],
            credentials.client_id,
            credentials.client_secret,
            API_BASE_URL='https://www.googleapis.com/oauth2/v3' if session['service'] == 'google' else 'https://discordapp.com/api',
        )
        if session['service'] == 'discord':
            capsule = oAuth.make_session(token=session.get('oauth2_token'))
            API_BASE_URL = oAuth.API_BASE_URL
            info = capsule.get(API_BASE_URL + '/users/@me').json()
            identity, username = int(info['id']), info['username']
        else:
            credentials = google.oauth2.credentials.Credentials(**session['credentials'])
            flow = googleapiclient.discovery.build('oauth2', 'v2', credentials=credentials)
            info = flow.userinfo().get().execute()
            identity, username = info['email'], info['email']
            session['credentials'] = credentials_to_dict(credentials)
        f = open('access.json')
        access = json.load(f)
        variables = {}
        variables['username'] = username
        disguard = mongo.disguard.disguard.find_one({})
        if landing in ('tylerBirthday2022', 'tylerq1arc'):
            variables['authorized'] = identity in access['tylerBirthday2022']
        else:
            variables['authorized'] = identity in access[landing]
    del disguard['_id']
    d = json.loads(json.dumps(disguard, default=jsonFormatter))
    if landing == 'timeKeeper':
        variables['keeperData'] = d['keeperData']
        variables['time'] = time(disguard['keeperData'])
    session.modified = True
    return render_template(f'{landing}.html', disguard=d, vars=variables)


def jsonFormatter(o):
    if type(o) is datetime.datetime:
        return o.isoformat()


def time(data):
    """Returns the time in sped-up terms (TIMEKEEPER)"""
    return (data['virtualEpoch'] + elapsed(data) + datetime.timedelta(hours=data['hoursFromUTC'])).isoformat()


def elapsed(data):
    """Returns time elapsed since the epoch (return type: datetime.timedelta)"""
    # Jan 19, 2021: Changed this approach from being single-line math to being start at a point & add it linearly, based on the new data type system. This eliminates the need for the pauseCompensation method.
    result = 0
    speedSectors = data.get('speedSectors')
    if len(speedSectors) < 2:
        return datetime.timedelta(seconds=0)
    for i, s in enumerate(speedSectors, 1):
        try:
            lastIndex = datetime.datetime.fromisoformat(s['timestamp'])
        except TypeError:
            lastIndex = s['timestamp']
        multiplier = s['multiplier']
        if i == len(speedSectors):
            currentIndex = datetime.datetime.utcnow()
        else:
            try:
                currentIndex = datetime.datetime.fromisoformat(speedSectors[i]['timestamp'])
            except TypeError:
                currentIndex = speedSectors[i]['timestamp']
        result += (currentIndex - lastIndex).total_seconds() * multiplier
    return datetime.timedelta(seconds=result)
    # return ((datetime.datetime.utcnow() - bot.data['epoch'] - datetime.timedelta(seconds=bot.data['pausedDuration'])) - (datetime.datetime.utcnow() - bot.data['pausedTimestamp'] if bot.data['paused'] else datetime.timedelta(seconds=0))) * bot.data['timeMultiplier']


if __name__ == '__main__':
    app.run()
