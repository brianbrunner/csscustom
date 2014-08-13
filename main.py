#!/usr/bin/python

# Standard Library
import argparse
import json
import os
import re
import time
from collections import defaultdict
from threading import Lock
from urlparse import urlparse

# Third Party
import leveldb
import requests
from boto.s3.connection import S3Connection
from flask import Flask, redirect, jsonify, render_template, request, \
                  session, url_for

# Local


# set up level db
db = leveldb.LevelDB('./db')


# parse args
argParser = argparse.ArgumentParser(description='Run the Quarry server.')
argParser.add_argument('-d', '--debug', action='store_true', help='Turn on debug mode')
argParser.add_argument('-p', '--port', type=int, default=9000, help='Set the port')
argParser.add_argument('-H', '--host', type=str, default='127.0.0.1', help='Set the port')
args, _ = argParser.parse_known_args()

# put args in sensible all caps variables
DEBUG = args.debug
HOST = args.host
PORT = args.port


# create flask app
app = Flask(__name__, static_url_path='/static', static_folder='./static')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024


# Static page, no need to render it so just fucking load it
index_html = ''
with open('index.html') as f:
    index_html = f.read()

@app.route('/')
def index():

    return index_html

# Set up S3 junk
codeLock = Lock()
s3Conn = S3Connection()
bucketname = os.environ["BUCKET"]
bucket = s3Conn.get_bucket(bucketname)
bucket.set_acl('public-read')

@app.route('/upload_style', methods=['POST'])
def upload_style():

    name = request.form['name']
    if not re.match('^\w+$', name):
        return "Name must only contain letters, numbers and underscores.", 400
    code = request.form['code']
    style = request.form['style']

    match = False
    with codeLock:
        try:
            compareCode = db.Get(name)
            if code == compareCode:
                match = True
        except KeyError as e:
            db.Put(name, code)
            match = True
        if match:
            try:
                latest = json.loads(db.Get("*latest*"))
            except KeyError:
                latest = []
            latest.insert(0, name)
            latest = latest[:5]
            db.Put("*latest*", json.dumps(latest))

    if match:
        key = bucket.get_key('styles/%s' % name, validate=False)
        key.set_contents_from_string(style)
        return "Success!"
    else:
        return "Code didn't match :(", 404

@app.route("/latest")
def latest():

    return db.Get('*latest*')

# set up hn stuff
hnlock = Lock() 
hnfreshness = 60*1
hntimeout = 5
hncontent = defaultdict(lambda: defaultdict(int))

@app.route('/hn/<name>/<path:path>')
def render_hn(name, path)

@app.route('/hn/<name>/<path:path>')
def render_hn(name, path):

    if path == "newslogin":
        return "Not Allowed To Login On HNCustom.", 200

    query = urlparse(request.url).query
    if query:
        path += "?%s" % urlparse(request.url).query

    if time.time() - hnfreshness > hncontent[path]['updated']:
        with hnlock:
            
            # AVOID THE STAMPEDE!
            if time.time() - hnfreshness > hncontent[path]['updated']:

                print "UPDATING HN PAGE: %s" % path

                res = requests.get("http://news.ycombinator.com/%s" % path, timeout=5)

                content_type = res.headers['Content-Type']
                if content_type == "text/html; charset=utf-8":
                    hncontent[path]['content'] = res.text
                else:
                    hncontent[path]['content'] = res.content
                hncontent[path]['type'] = content_type
                hncontent[path]['updated'] = time.time()

    style_url = "https://%s.s3.amazonaws.com/styles/%s" % (bucketname, name)
    content_type = hncontent[path]['type']
    content = hncontent[path]['content']
    if content_type == "text/html; charset=utf-8":
        content = "<link rel='stylesheet' href='%s'>" % style_url + content

    return content, 200, {'Content-Type': content_type}

@app.route('/hn/<name>/')
def render_hn_bare(name):

    return render_hn(name, "")


if __name__ == "__main__":

    app.run(debug=DEBUG, port=PORT, host=HOST, threaded=True)
