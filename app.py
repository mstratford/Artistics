from flask import Flask, render_template, request, redirect, send_from_directory
from markupsafe import escape
import musicbrainzngs as mbz
import requests
import html
import urllib.parse
import re
from multiprocessing import Pool
from typing import List
from functools import partial
from itertools import repeat
import datetime
import math

app = Flask(__name__)

class recording():

    def __init__(self, title, length, lyrics = None, cover_image = None):
        self.title = title
        self.length = length
        self.lyrics = lyrics
        self.cover_image = cover_image

    def __eq__(self, other):
        return self.title == other.title

    def __hash__(self):
        return hash(('title', self.title))

    def __lt__(self, other):
        return self.title < other.title


@app.template_filter('duration')
def timectime(s):
    if s != None:
        duration = int(s) / 1000
        mins = math.floor(duration / 60)
        secs = math.floor(duration % 60)
        return "{}:{:0>2d}".format(mins, secs)
    return None

# Render the homepage.
@app.route('/')
def page():
    return render_template('home.html', data=None)

# Render the search page with results.
@app.route('/search')
def page_search():
    result = None
    # Get the artist GET param value (if present)
    # If no term provided, template will show missing term message.
    term = request.args.get("artist")
    if term:
        # Call API for artists matching list.
        result = {
            "artist-list": api_search_artist(term),
            "term": term
        }
    return render_template('artist-list.html', data=result)


# Render the artist info page.
# id: MBID string from MusicBrainz.
@app.route('/artist/<string:id>')
def page_artist(id):

    artist = api_get_artist(id)

    # End early if we don't have an artist for the user's ID.
    # Template will render a 404.
    if artist:

        # Get recordings (songs) and releases (EP's, singles etc.) from this artist.
        recordings = api_get_recordings(id)
        releases = api_get_releases(id)

        # Remove duplicate tracks (with same name) based on class __eq__
        recordings = list(set(recordings))
        recordings.sort()

        # Add in a cover image url to each release. The API is called in api_get_cover_image on request.
        for release in releases:
            release["cover_image"] = "/cover/{}".format(release["id"])

        lyrics_lengths_avg = 0.0
        lyrics_count = 0

        # Get the lyrics for each song. The API is slow and we typically have lots of tracks.
        # We'll process each track as a separate process, upto 10 at once.
        with Pool(processes=10) as pool:
            lyrics = pool.starmap(
                api_get_lyrics,
                zip(
                    recordings, # Feed in all of the tracks to request.
                    repeat(artist["name"]) # All tracks share the same artist.
                )
            )

        # Once the lyrics have been retrieved from all processes, map them back to the recordings.
        for i in range(len(recordings)):
            recordings[i].lyrics = lyrics[i]

        # Count up the words and number of tracks with lyrics available.
        for lyric in lyrics:
            if lyric:
                lyrics_lengths_avg += lyric["word-count"]
                lyrics_count += 1

        # Calculate the average if we've got more than 0 tracks to divide by.
        if lyrics_count > 0:
            lyrics_lengths_avg /= lyrics_count

        result = {
            "artist": artist,
            "recordings": recordings,
            "releases": releases,
            "lyrics": {
                "recordings": lyrics_count,
                "avg_words": lyrics_lengths_avg
            }
        }
    else:
        result = {}

    return render_template('artist.html', data=result)

# Serve static files from the images folder.
@app.route('/images/<path:path>')
def serve_images(path):
    return send_from_directory('images', path)

# Retrieve artists matching a search term (name) from MusicBrainz
def api_search_artist(name):
    try:
        mbz.set_useragent("Artistics", "v1.0","hi@mstratford.net")
        result = mbz.search_artists(artist = name)
    except mbz.WebServiceError as exc:
        result = {}

    if "artist-list" in result:
        return result["artist-list"]
    return None

# Retrieve artist details matching a MBID from MusicBrainz
def api_get_artist(id):
    try:
        mbz.set_useragent("Artistics", "v1.0","hi@mstratford.net")
        result = mbz.get_artist_by_id(id)
    except mbz.WebServiceError as exc:
        result = {}

    if "artist" in result:
        return result["artist"]
    return None

# Get all recordings for an artist matching a MBID from MusicBrainz
def api_get_recordings(id):
    try:
        mbz.set_useragent("Artistics", "v1.0","hi@mstratford.net")
        result = mbz.browse_recordings(artist=id, limit=1000)
    except mbz.WebServiceError as exc:
        result = {}

    if "recording-list" in result:
        return [
            recording(
                recordings["title"],
                recordings["length"] if "length" in recordings else None
            )
            for recordings in result["recording-list"]
        ]

    return None

# Get all release(groups) for an artist matching a MBID from MusicBrainz
# Release groups is used because it combines CD/Download releases of an albumn etc.
def api_get_releases(id):
    try:
        mbz.set_useragent("Artistics", "v1.0","hi@mstratford.net")
        result = mbz.browse_release_groups(artist=id)
    except mbz.WebServiceError as exc:
        result = None

    if "release-group-list" in result:
        return result["release-group-list"]
    return None

# Endpoint to return the image for a release-group.
# This is done separately such that the browser can load these images after
# the rest of the page has loaded, since this API is quite slow.
#
# id: release-group MBID
@app.route('/cover/<id>')
def api_get_cover_image(id):
    try:
        mbz.set_useragent("Artistics", "v1.0","hi@mstratford.net")
        data = mbz.get_release_group_image_list(id)

        # There can be multiple, but the one we're looking for is the front cover.
        for image in data["images"]:
            if "Front" in image["types"] and image["approved"]:

                # Redirect the browser's request to the image URL the API provided.
                return redirect(image["thumbnails"]["large"], code=302)


    except mbz.WebServiceError as exc:
        pass

    # If we encounter an error with the API (eg 404, or only back image etc), return a placeholder image.
    return redirect("/images/question.png", code=302)


def api_get_lyrics(recording, artist):
    title = recording.title
    artist = urllib.parse.quote(
        html.escape(artist),
        safe=''
    )
    title = urllib.parse.quote(
        html.escape(title),
        safe=''
    )
    r = requests.get("https://api.lyrics.ovh/v1/{}/{}".format(artist, title))

    if r.status_code == 200:

        data = r.json()["lyrics"]

        string = html.escape(data)
        # Split the string up into an array of words by replacing any special chars with spaces
        # (excluding - and ', since these are commonly used in regular speech)
        # and splitting by these spaces

        words = re.sub("[^\w'-]", " ",  string).split()

        info = {
            "string": string,
            "words": words,
            "word-count": len(words)
        }
        return info


if __name__ == "__main__":
    # Run app in threaded mode such that cover images can be requested in parallel.
    app.run(host="0.0.0.0", port="5000", threaded=True)
