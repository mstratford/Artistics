from flask import Flask, render_template, request, redirect, send_from_directory
from markupsafe import escape
import musicbrainzngs as mbz
import requests
import cgi
import urllib.parse
import re

app = Flask(__name__)

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

        recordings = api_get_recordings(id)
        releases = api_get_releases(id)
        for release in releases:
            release["cover_image"] = "/cover/{}".format(release["id"])

        lyrics_lengths_avg = 0.0
        lyrics_count = 0
        for recording in recordings:
            lyrics = api_get_lyrics(artist["name"], recording["title"])
            if (lyrics):
                lyrics_lengths_avg += lyrics["word-count"]
                lyrics_count += 1
            recording["lyrics"] = lyrics
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
        result = None

    if "artist-list" in result:
        return result["artist-list"]
    return None

# Retrieve artist details matching a MBID from MusicBrainz
def api_get_artist(id):
    try:
        mbz.set_useragent("Artistics", "v1.0","hi@mstratford.net")
        result = mbz.get_artist_by_id(id)
    except mbz.WebServiceError as exc:
        result = None

    if "artist" in result:
        return result["artist"]
    return None

# Get all recordings for an artist matching a MBID from MusicBrainz
def api_get_recordings(id):
    try:
        mbz.set_useragent("Artistics", "v1.0","hi@mstratford.net")
        result = mbz.browse_recordings(artist=id, limit=1000)
    except mbz.WebServiceError as exc:
        result = None

    if "recording-list" in result:
        return result["recording-list"]
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

def api_get_lyrics(artist, title):
    artist = urllib.parse.quote(
        cgi.escape(artist),
        safe=''
    )
    title = urllib.parse.quote(
        cgi.escape(title),
        safe=''
    )
    r = requests.get("https://api.lyrics.ovh/v1/{}/{}".format(artist, title))

    if r.status_code == 200:

        data = r.json()["lyrics"]

        print(data)

        string = cgi.escape(data)
        # Split the string up into an array of words by replacing any special chars with spaces
        # (excluding - and ', since these are commonly used in regular speech)
        # and splitting by these spaces
        words = re.sub("[^\w'-]", " ",  string).split()
        print(words)
        info = {
            "string": string,
            "words": words,
            "word-count": len(data)
        }
        return (info)
    else:
        return None


if __name__ == "__main__":
    # Run app in threaded mode such that cover images can be requested in parallel.
    app.run(host="0.0.0.0", port="5000", threaded=True)
