'''Handles OAuth2 Sessions and authentication management'''
import os
from requests_oauthlib import OAuth2Session

class OAuth2Handler:
    def __init__(self, service: str, CLIENT_ID, CLIENT_SECRET, REDIRECT_URI=None, API_BASE_URL=None, AUTHORIZATION_BASE_URL=None, TOKEN_URL=None):
        self.service = service
        self.CLIENT_ID = CLIENT_ID
        self.CLIENT_SECRET = CLIENT_SECRET
        self.REDIRECT_URI = REDIRECT_URI
        self.API_BASE_URL = API_BASE_URL
        self.AUTHORIZATION_BASE_URL = AUTHORIZATION_BASE_URL or (API_BASE_URL + '/oauth2/authorize')
        self.TOKEN_URL = TOKEN_URL or API_BASE_URL + '/oauth2/token'

        if self.REDIRECT_URI and 'http://' in self.REDIRECT_URI:
            os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = 'true'  

    def setup(self, token=None, state=None, scope=None, token_updater = None):
        self.session = self.make_session(token, state, scope, token_updater)
    
    def make_session(self, token=None, state=None, scope=None, token_updater = None):
        return OAuth2Session(
            client_id=self.CLIENT_ID,
            token=token,
            state=state,
            scope=scope,
            redirect_uri=self.REDIRECT_URI,
            auto_refresh_kwargs={
                'client_id': self.CLIENT_ID,
                'client_secret': self.CLIENT_SECRET,
            },
            auto_refresh_url=self.TOKEN_URL,
            token_updater=token_updater)
    
    def authorization_url(self, scope):
        if self.service == 'discord':
            return f'https://discordapp.com/api/oauth2/authorize?client_id={self.CLIENT_ID}&redirect_uri={self.REDIRECT_URI}&response_type=code&scope={scope}'
        else:
            return f'https://accounts.google.com/o/oauth2/v2/auth'
