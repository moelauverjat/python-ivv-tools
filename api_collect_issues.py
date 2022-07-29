
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_mysqldb import MySQL
from requests.exceptions import HTTPError
import logging, requests, ast
from github3 import login
import logging

# token generated on Github
token = "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"

app = Flask(__name__)
CORS(app)

app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'ivvtools'
app.config['MYSQL_UNIX_SOCKET'] = '/opt/lampp/var/mysql/mysql.sock'

mysql = MySQL(app)

base = ["bug", "ivv"]
minor = "priority:minor"
major = "priority:major"
blocking = "priority:blocking"
priority = "priority:"
workaround = "workaround"

# Request to fill the database with all issues in github
@app.route('/fillissuesdatabase', methods=["GET"])
def collectIssues():
    # Login to Github
    try:
        gh = login(token=token)
        response = {{'valid': True}, {'error': ''}}
        fillIssuesDatabase(gh)
    except ValueError:
        print("Github connexion issue or token invalid")
        response = {{'valid': False}, {'error': 'Github connexion issue or token invalid'}}


    return response.json()

def fillIssuesDatabase(arg):
    print(arg)