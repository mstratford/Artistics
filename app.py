from flask import Flask, render_template, request, redirect, send_from_directory
from markupsafe import escape
import musicbrainzngs as mbz
import requests
import cgi
import urllib.parse
import re

app = Flask(__name__)

@app.route('/')
def page():
    return render_template('home.html', data=None)

@app.route('/search')
def page_search():
    if request.args.get("artist"):
        term = request.args.get("artist")
        result = api_search_artist(term)
        result["term"] = term
        return render_template('artist-list.html', data=result)


@app.route('/artist/<id>')
def page_artist(id):
    result = {}
    artist = api_get_artist(id)

    # End early if we don't have an artist for the user's ID.
    if not artist:
        return render_template('artist.html', data=result), 404


    recordings = api_get_recordings(id)["recording-list"]
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

    result["artist"] = artist
    result["recordings"] = recordings
    result["releases"] = releases
    result["lyrics"] = {
        "recordings": lyrics_count,
        "avg_words": lyrics_lengths_avg
    }
    return render_template('artist.html', data=result)

def api_search_artist(name):
    try:
        mbz.set_useragent("Artistics", "v1.0","hi@mstratford.net")
        result = mbz.search_artists(artist = name)
    except mbz.WebServiceError as exc:
        result = None
    if "artist-list" in result:
        return result
    else:
        return None

def api_get_artist(id):
    try:
        mbz.set_useragent("Artistics", "v1.0","hi@mstratford.net")
        result = mbz.get_artist_by_id(id)
        if "artist" in result:
            result = result["artist"]

    except mbz.WebServiceError as exc:
        result = None

    return result

def api_get_recordings(id):
    try:
        mbz.set_useragent("Artistics", "v1.0","hi@mstratford.net")
        result = mbz.browse_recordings(artist=id, limit=1000)
    except mbz.WebServiceError as exc:
        result = None
    #if "artist" in result:
    return result

def api_get_releases(id):
    try:
        mbz.set_useragent("Artistics", "v1.0","hi@mstratford.net")
        result = mbz.browse_release_groups(artist=id)["release-group-list"]


    except mbz.WebServiceError as exc:
        result = None
    #if "artist" in result:
    return result
    #        return result
    #   else:
    #      return "Woops"

@app.route('/cover/<id>')
def api_get_cover_image(id):
    try:
        mbz.set_useragent("Artistics", "v1.0","hi@mstratford.net")
        data = mbz.get_release_group_image_list(id)
        for image in data["images"]:
            if "Front" in image["types"] and image["approved"]:
                return redirect(image["thumbnails"]["large"], code=302)


    except mbz.WebServiceError as exc:
        return redirect("/images/question.png", code=302)


@app.route('/images/<path:path>')
def serve_images(path):
    return send_from_directory('images', path)

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
