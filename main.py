import os
import os.path
import requests
import requests_toolbelt.adapters.appengine
import json
import webapp2
import jinja2
import base64
from google.appengine.api import users
from models import User
from models import SharedPlaylists

# Use the App Engine Requests adapter. This makes sure that Requests uses URLFetch.
requests_toolbelt.adapters.appengine.monkeypatch()

jinja_current_directory = jinja2.Environment(
    loader = jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions = ['jinja2.ext.autoescape'],
    autoescape = True)

def get_logged_in_user(request_handler):
    # gets current user
    user = users.get_current_user()

    # if this user doesn't exist (aka no one is signed into Google)
    if not user:
        # send them to Google log-in url
        self.redirect('/login')
        return None

    # make sure user is signed in to PlayShare
    # do we have their Google ID in P.S. model (which is called User)?
    existing_user = User.get_by_id(user.user_id())
    return existing_user

# method for grabbing the access and refresh token
# returns a dict
def get_access_token(request_handler):
    # grabs the value for parameter code in the url
    code = request_handler.request.get("code")

    # post request body parameters
    data = {'grant_type': "authorization_code",
    'code': code,
    'redirect_uri': '', #redirect uri
    'client_id': '', #client id
    'client_secret': ''} #client secret

    # post request header parameters with base64 encoded credentials
    header = {'Authorization': 'Basic ' + base64.b64encode("%s:%s" % (client_id, client_secret))}

    # sends post request to token endpoint
    post_token = requests.post('https://accounts.spotify.com/api/token', headers=header, data=data)

    # grabs response json data
    json_data = json.loads(post_token.text)

    access_token = json_data['access_token']
    refresh_token = json_data['refresh_token']
    token_dict = {'access_token': access_token, 'refresh_token': refresh_token}
    return token_dict

# declares global variables to be changed later to actual values
access_token = ''
refresh_token = ''
user_id = ''
play_id = ''
playlist_title = ''
shared_playlists = []

class StartPage(webapp2.RequestHandler):
    def get(self):
        # render the home screen
        home_template = jinja_current_directory.get_template('templates/start.html')
        self.response.write(home_template.render())

class Login(webapp2.RequestHandler):
    def get(self):
        auth_template = jinja_current_directory.get_template('templates/authorize.html')
        user = users.get_current_user()

        # if the user is logged with Google
        if user:
            # get the user's Google ID.
            our_site_user = User.get_by_id(user.user_id())
            signout_link = users.create_logout_url('/')

            # if the user is logged in to both Google and P.S.
            if our_site_user:
                self.redirect('/authorize')

            # If the user is logged into Google but never been to P.S. before..
            else:
                user = users.get_current_user()
                our_user = User(id=user.user_id())
                our_user.put()
                self.response.write(auth_template.render())

        # Otherwise, the user isn't logged in to Google or P.S.
        else:
            self.redirect(users.create_login_url('/login'))

class Authorize(webapp2.RequestHandler):
    def get(self):
        # set query parameters
        payload = {'client_id': '', #client id
        'redirect_uri': '', #redirect uri
        'response_type': 'code',
        'state': None,
        'scope': 'playlist-modify-public'}

        # get request to accounts service
        get_auth = requests.get('https://accounts.spotify.com/authorize/', params=payload)

        auth_url = str(get_auth.url)

        self.redirect(auth_url)

class CallBack(webapp2.RequestHandler):
    def get(self):
        # creates dict of token values
        token_dict = get_access_token(self)
        # grabs tokens as variables
        local_access = token_dict['access_token']
        local_refresh = token_dict['refresh_token']
        # IMPORTANT
        # changes global token values to be the ACTUAL token values
        global access_token
        access_token = local_access
        global refresh_token
        refresh_token = local_refresh

        # redirects to search page
        self.redirect('/search')

class SearchPage(webapp2.RequestHandler):
    def get(self):
        global access_token
        global user_id
        current_user = get_logged_in_user(self)

        header = {'Authorization': 'Bearer ' + access_token}

        r = requests.get('https://api.spotify.com/v1/me', headers=header)
        json_data = json.loads(r.text)
        user_id = json_data['id']
        current_user.user_id = user_id #adds user id to user entity in db
        current_user.put()

        logout = {'logout_link' : users.create_logout_url('/')}
        search_template = jinja_current_directory.get_template('templates/search.html')
        self.response.write(search_template.render(logout))

    def post(self):
        global access_token
        global user_id
        global play_id
        global playlist_title
        current_user = get_logged_in_user(self)

        # grabs earch query and declares requests params and header
        query = self.request.get('search_word')
        search_h = {'Authorization': 'Bearer ' + access_token}
        params ={'q': query,
        'type': 'track',
        'limit': 30,
        'market': 'US'}
        # GET request to the search endpoint & loads json object with results
        s = requests.get('https://api.spotify.com/v1/search', headers=search_h, params=params)
        json_results = json.loads(s.text)
        uris = current_user.sort_results(json_results, query) #grabs list of track uris

        # this now creates a new playlist
        play_h = {'Authorization': 'Bearer ' + access_token,
        'Content-Type': 'application/json'}
        playlist_title = query
        play_b = {'name': playlist_title}
        play_url = str('https://api.spotify.com/v1/users/' + user_id + '/playlists')

        p = requests.post(play_url, headers=play_h, data=json.dumps(play_b))
        json_play = json.loads(p.text)
        play_id = json_play['id']

        # POST request to add tracks to new playlist
        add_url = str('https://api.spotify.com/v1/playlists/' + play_id + '/tracks')
        add_b = {'uris': uris}
        a = requests.post(add_url, headers=play_h, data=json.dumps(add_b))

        self.redirect('/playlist')

class PlaylistPage(webapp2.RequestHandler):
    def get(self):
        global user_id
        global play_id
        global playlist_title

        # src url for embed code in html
        src = str('https://open.spotify.com/embed/user/' + user_id + '/playlist/' + play_id)
        embed_dict = {'logout_link' : users.create_logout_url('/'), 'src': src, 'title': playlist_title}

        playlist_template = jinja_current_directory.get_template('templates/playlist.html')
        self.response.write(playlist_template.render(embed_dict))

class SharePage(webapp2.RequestHandler):
    def get(self):
        global access_token
        global shared_playlists
        shared_playlists = [] #resets every time so no duplicates

        header = {'Authorization': 'Bearer ' + access_token}

        r = requests.get('https://api.spotify.com/v1/me/playlists', headers=header)
        json_data = json.loads(r.text)
        items = json_data['items'] #returns a list
        for playlist in items:
            play_dict = {}
            name = playlist['name']
            id = playlist['id']
            play_dict['name'] = name
            play_dict['id'] = id
            shared_playlists.append(play_dict) #list of dictionaries

        share_dict = {'logout_link' : users.create_logout_url('/'), 'playlists': shared_playlists}

        share_template = jinja_current_directory.get_template('templates/share.html')
        self.response.write(share_template.render(share_dict))

    def post(self):
        global shared_playlists
        global user_id
        title = self.request.get('playlist')
        genres = self.request.get_all('genres')
        moods = self.request.get_all('moods')

        for playlist in shared_playlists:
            if playlist['name'] == title:
                id = playlist['id']
                playlist['genres'] = genres
                playlist['moods'] = moods
                entity = SharedPlaylists.query(SharedPlaylists.play_id == id).get() #checks for duplicates
                if entity: #playlist already exists in db
                    entity.genres = genres
                    entity.moods = moods
                    entity.put() #updates playlist
                else:
                    playlist_obj = SharedPlaylists(play_id=id, user_id=user_id, genres=genres, moods=moods)
                    playlist_obj.put() #creates new playlist obj

        self.redirect('/feed')

class FeedPage(webapp2.RequestHandler):
    def get(self):
        posted = SharedPlaylists.query().fetch() #list of shared playlists from ALL users
        shared_dict = {'logout_link' : users.create_logout_url('/'), 'playlists': posted}

        feed_template = jinja_current_directory.get_template('templates/feed.html')
        self.response.write(feed_template.render(shared_dict))

    # method for sorting based on similar genres and moods
    def sort_results(self, request_handler, playlist):
        count = 0 #playlists earn a point for every genre/mood in common with search query
        play_genres = playlist.genres #list of genres for each playlist
        play_moods = playlist.moods
        for item in play_genres:
            genres = request_handler.request.get_all('genres') #gets searched genres
            if item in genres:
                count+=1 #adds a point if the genre in tags
            else:
                pass
        for item in play_moods:
            moods = request_handler.request.get_all('moods') #searched moods
            if item in moods:
                count+=1
            else:
                pass
        return count #return "similarity" count i.e. how many genres/moods are relevant

    def post(self):
        posted = SharedPlaylists.query().fetch() #returns all shared playlists in the db
        feed_template = jinja_current_directory.get_template('templates/feed.html')

        if not self.request.get('genres') and not self.request.get('moods'): #if nothing is selected
            show_all = {'logout_link' : users.create_logout_url('/'), 'playlists': posted}
            self.response.write(feed_template.render(show_all)) #show all playlists
        else:
            matches = []
            for playlist in posted:
                sim_dict = {} #each playlist is represented by this dict
                similarity_count = self.sort_results(self, playlist) #returns number of similarities
                if similarity_count > 0:
                    id = playlist.play_id
                    user = playlist.user_id
                    genres = playlist.genres
                    moods = playlist.moods
                    sim_dict['play_id'] = id
                    sim_dict['user_id'] = user
                    sim_dict['genres'] = genres
                    sim_dict['moods'] = moods
                    sim_dict['count'] = similarity_count
                    matches.append(sim_dict) #makes a list with dicts as elements

            sorted_matches = sorted(matches, key=lambda k: k['count'], reverse=True) #sorts by highest count
            sorted_dict = {'logout_link' : users.create_logout_url('/'), 'playlists': sorted_matches}

            self.response.write(feed_template.render(sorted_dict))

app = webapp2.WSGIApplication([
    ('/', StartPage),
    ('/login', Login),
    ('/authorize', Authorize),
    ('/callback', CallBack),
    ('/search', SearchPage),
    ('/playlist', PlaylistPage),
    ('/share', SharePage),
    ('/feed', FeedPage)
], debug=True)
