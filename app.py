import os
import pymongo
from flask import Flask, g, session, redirect, request, url_for, jsonify, render_template
from requests_oauthlib import OAuth2Session
import dns
import oauth
import database

OAUTH2_CLIENT_ID = oauth.Oauth.client_id
OAUTH2_CLIENT_SECRET = oauth.Oauth.client_secret
OAUTH2_REDIRECT_URI = 'https://disguard.herokuapp.com/callback'
#OAUTH2_REDIRECT_URI = 'http://localhost:5000/callback'

API_BASE_URL = 'https://discordapp.com/api'
AUTHORIZATION_BASE_URL = API_BASE_URL + '/oauth2/authorize'
TOKEN_URL = API_BASE_URL + '/oauth2/token'

app = Flask(__name__)

app.debug = True
app.config['SECRET_KEY'] = oauth.Oauth.client_secret

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


@app.route('/')
def index():
    scope = request.args.get(
        'scope',
        'identify guilds')
    #discord = make_session(scope=scope.split(' '))
    #authorization_url = discord.authorization_url(AUTHORIZATION_BASE_URL)
    #session['oauth2_state'] = state
    if 'user_id' not in session:
        return redirect('https://discordapp.com/api/oauth2/authorize?client_id={}&redirect_uri={}&response_type=code&scope={}'.format(OAUTH2_CLIENT_ID, OAUTH2_REDIRECT_URI, scope))
    else:
        return redirect(url_for('manage'))

@app.route('/callback')
def callback():
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
    return redirect(url_for('.manage'))

def EnsureVerification(id):
    return id in [server.get('server_id') for server in iter(users.find_one({"user_id": int(session['user_id'])}).get('servers'))]

@app.route('/manage')
def manage():
    discord = make_session(token=session.get('oauth2_token'))
    user = discord.get(API_BASE_URL + '/users/@me').json()
    shared = users.find_one({"user_id": int(user.get("id"))}).get("servers")
    return render_template('homepage.html', servers=shared, user=user.get("username"))

@app.route('/manage/<int:id>')
def manageServer(id):
    if EnsureVerification(id):
        return render_template('trio.html', server=servers.find_one({"server_id":id}).get("server_id"))
    else:
        return redirect(url_for('manage'))

@app.route('/manage/<int:id>/server', methods=['GET', 'POST'])
def server(id):
    if not EnsureVerification(id):
        return redirect(url_for('manage'))
    serv = servers.find_one({"server_id": id})
    if request.method == 'POST':
        r = request.form
        servers.update_one({"server_id": id}, {"$set": {"prefix": r.get('prefix')}})
        return redirect(url_for('server', id=id)) 
    return render_template('general.html', servObj=serv, id=id)

@app.route('/manage/<int:id>/antispam', methods=['GET', 'POST'])
def antispam(id):
    if not EnsureVerification(id):
        return redirect(url_for('manage'))
    if request.method == 'POST':
        r = request.form
        database.UpdateMemberWarnings(id, int(r.get('warn')))
        serv = servers.find_one({"server_id": id})
        antispam = serv.get("antispam")
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
            "log": [None if r.get("log").lower() == "none" or r.get("log") is None else [a.get("name") for a in iter(serv.get("channels")) if a.get('id') == int(r.get("log"))][0], int(r.get("log"))],
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
            "invites": r.get("invites").lower() == 'false',
            "everyoneTags": int(r.get("everyoneTags")),
            "hereTags": int(r.get("hereTags")),
            "roleTags": int(r.get('roleTags')),
            "quickMessages": [int(r.get("quickMessages0")), int(r.get("quickMessages1"))],
            "ignoreRoled": r.get("ignoreRoled").lower() == 'true',
            "exclusionMode": int(r.get('exclusionMode')),
            "channelExclusions": cex,
            "roleExclusions": rex,
            "memberExclusions": mex,
            "profanityEnabled": r.get('profanityEnabled').lower() == 'true',
            "profanityTolerance": float(r.get("profanityTolerance")) / 100,
            "filter": profane}}})
        return redirect(url_for('antispam', id=id))
    servObj = servers.find_one({"server_id": id})
    return render_template('antispam.html', servid = id, servObj=servObj, automod = servObj.get("antispam"), channels=servObj.get("channels"), roles=servObj.get("roles"), members=servObj.get("members"))

@app.route('/manage/<int:id>/moderation')
def moderation(id):
    return "This feature will be available later!"
    

@app.route('/manage/<int:id>/cyberlog', methods=['GET', 'POST'])
def cyberlog(id):
    if not EnsureVerification(id):
        return redirect(url_for('manage'))
    servObj = servers.find_one({"server_id": id})
    if request.method == 'POST':
        r = request.form
        c = servObj.get("cyberlog")
        servers.update_one({"server_id": id}, {"$set": {"cyberlog": {
        "enabled": r.get('enabled').lower() == 'true',
        "image": r.get('imageLogging').lower() == 'true',
        "message": {
            "name": c.get('message').get('name'),
            "description": c.get('message').get('description'),
            "embed": c.get('message').get('embed'),
            "read": r.get('messageRead').lower() == 'true',
            "enabled": r.get('message').lower() == 'true',
            "channel": None if r.get('messageChannel').lower() == 'none' or r.get('messageChannel') is None else int(r.get('messageChannel')),
            "color": c.get('message').get('color'),
            "advanced": c.get('message').get('advanced')},
        "doorguard": {
            "name": c.get('doorguard').get('name'),
            "description": c.get('doorguard').get('description'),
            "embed": c.get('doorguard').get('embed'),
            "read": r.get('doorRead').lower() == 'true',
            "enabled": r.get('doorguard').lower() == 'true',
            "channel": None if r.get('doorChannel').lower() == 'none' or r.get('doorChannel') is None else int(r.get('doorChannel')),
            "color": c.get('doorguard').get('color'),
            "advanced": c.get('doorguard').get('advanced')},
        "server": {
            "name": c.get('server').get('name'),
            "description": c.get('server').get('description'),
            "embed": c.get('server').get('embed'),
            "read": r.get('serverRead').lower() == 'true',
            "enabled": r.get('server').lower() == 'true',
            "channel": None if r.get('serverChannel').lower() == 'none' or r.get('serverChannel') is None else int(r.get('serverChannel')),
            "color": c.get('server').get('color'),
            "advanced": c.get('server').get('advanced')},
        "channel": {
            "name": c.get('channel').get('name'),
            "description": c.get('channel').get('description'),
            "embed": c.get('channel').get('embed'),
            "read": r.get('channelRead').lower() == 'true',
            "enabled": r.get('channel').lower() == 'true',
            "channel": None if r.get('channelChannel').lower() == 'none' or r.get('channelChannel') is None else int(r.get('channelChannel')),
            "color": c.get('channel').get('color'),
            "advanced": c.get('channel').get('advanced')},
        "member": {
            "name": c.get('member').get('name'),
            "description": c.get('member').get('description'),
            "embed": c.get('member').get('embed'),
            "read": r.get('memberRead').lower() == 'true',
            "enabled": r.get('member').lower() == 'true',
            "channel": None if r.get('memberChannel').lower() == 'none' or r.get('memberChannel') is None else int(r.get('memberChannel')),
            "color": c.get('member').get('color'),
            "advanced": c.get('member').get('advanced')},
        "role": {
            "name": c.get('role').get('name'),
            "description": c.get('role').get('description'),
            "embed": c.get('role').get('embed'),
            "read": r.get('roleRead').lower() == 'true',
            "enabled": r.get('role').lower() == 'true',
            "channel": None if r.get('roleChannel').lower() == 'none' or r.get('roleChannel') is None else int(r.get('roleChannel')),
            "color": c.get('role').get('color'),
            "advanced": c.get('role').get('advanced')},
        "emoji": {
            "name": c.get('emoji').get('name'),
            "description": c.get('emoji').get('description'),
            "embed": c.get('emoji').get('embed'),
            "read": r.get('emojiRead').lower() == 'true',
            "enabled": r.get('emoji').lower() == 'true',
            "channel": None if r.get('emojiChannel').lower() == 'none' or r.get('emojiChannel') is None else int(r.get('emojiChannel')),
            "color": c.get('emoji').get('color'),
            "advanced": c.get('emoji').get('advanced')}}}})
        return redirect(url_for('cyberlog', id=id))
    return render_template('cyberlog.html', servid=id, cyberlog=servObj.get("cyberlog"), channels=servObj.get("channels"))

if __name__ == '__main__':
    app.run()
