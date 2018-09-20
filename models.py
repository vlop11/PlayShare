from google.appengine.ext import ndb
from google.appengine.api import users

class User(ndb.Model):
    user_id = ndb.StringProperty()
    playlists = ndb.StringProperty(repeated=True)

    # method for deleting duplicates and making sure query is actually in title
    def sort_results(self, json_results, query):
        # iterates through results and grabs the uri of the track
        tracks = json_results['tracks'] #tracks is a dictionary
        items = tracks['items'] #items is a list with dictionaries as elements
        names = [] #list of artist names
        uris = [] #list of uris (to be filled later)
        for song in items:
            artists_list = song['artists'] #returns a list
            uri = song['uri'] #returns the uri
            json_name = song['name'].encode('ascii','ignore')
            title = json_name.lower()
            for i in artists_list:
                name = i['name'].encode('ascii','ignore') #returns artist name
                if name not in names and query in title:
                    names.append(name) #adds all artists to a names list
                    uris.append(uri)
        uri_set = set(uris) #creates a unique set of uris w/ no duplicates
        uris = list(uri_set) #converts it back to list for json
        return uris #returns the list of track uris w/no duplicates

class SharedPlaylists(ndb.Model):
    play_id = ndb.StringProperty()
    user_id = ndb.StringProperty()
    genres = ndb.StringProperty(repeated=True)
    moods = ndb.StringProperty(repeated=True)
