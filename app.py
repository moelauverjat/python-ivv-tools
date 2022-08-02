from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_mysqldb import MySQL
from requests.exceptions import HTTPError
import logging, requests, ast, json
from github3 import login
from passlib.hash import pbkdf2_sha256

app = Flask(__name__)
CORS(app)


# MySQL access
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'ivvtools'
app.config['MYSQL_UNIX_SOCKET'] = '/opt/lampp/var/mysql/mysql.sock'

mysql = MySQL(app)

# SQUASH API urls and headers
squash_api = "https://squash.coprs.esa-copernicus.eu/squash"
squash_get_all = squash_api + "/api/rest/latest/users"

headers = {'Accept': 'application/json'}

# SQUASH access
squash_user = "IVV_tools"
squash_pwd = "IVV_tools"

# Strings
# Default password use when creating a new user in the database
password = "motdepasse"
# Token generated on Github
token = "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"
othertoker = "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"
# Others strings
base = ["bug", "ivv"]
workaround = "workaround"


###########################################################################
################## All requests from angular ##############################
###########################################################################

# Request all issues in the database
@app.route('/getallissues', methods=["GET"])
def getAllIssues():
    try:
        # Collect all issues in database
        issues = collectAllIssuesInBDD()
    except mysql.connection.Error as err:
        print(err)

    # Return a json with the list of all issues
    return jsonify(issues)

# Request all tags in the database
@app.route('/getalltags', methods=["GET"])
def getAllTags():
    try:
        # Collect all tags in database
        tags = collectAllTagsInBDD()
    except mysql.connection.Error as err:
        print(err)

    # Return a json with the list of all tags
    return jsonify(tags)


# Request to fill the database with all issues in github and generate the tags database with all tags
@app.route('/fillissuesdatabase', methods=["GET"])
def collectIssues():

    # Variable to store the response. By default, return valid.
    response = {'valid': True, 'error': ''}

    # Login to Github
    try:
        gh = login(token=token)
    except ValueError:
        print("Github connexion issue or token invalid")
        response = {'valid': False, 'error': 'Github connexion issue or token invalid'}
    
    # Create a the list of all issues in a good format for MySQL request
    issues = formateIssuesListForMySQL(gh)
    

    # Ask to fill issues database
    try:
        fillIssuesDatabase(issues)
    except:
        print("Database connexion issue or invalid MySQL request")
        response = {'valid': False, 'error': 'Database connexion issue or invalid MySQL request'}

    # Extract the tags of title, every string between a '[' and a ']' is added as a tag
    tagList = extractTagsOfIssuesfromTitle(issues)

    # Ask to fill tags database
    try:
        fillTagsDatabase(tagList)
    except:
        print("Database connexion issue or invalid MySQL request")
        response = {'valid': False, 'error': 'Database connexion issue or invalid MySQL request'}

    # Return a json : {'valid':boolean,'error':string}
    return jsonify(response)

# Request to fill the database with all users in squash API
@app.route('/fillusersdatabase', methods=["GET"])
def getAllUsers():

    # Variable to store the response. By default, return valid.
    response = {'valid': True, 'error': ''}

    # Ask the list of all users in Squash API
    try:
        squashResponse = requests.get(squash_get_all, auth=(squash_user, squash_pwd), headers=headers)
        squashResponse.raise_for_status()
    except HTTPError as http_err:
        print(f'HTTP error occurred: {http_err}')
        response = {'valid': False, 'error': 'Something went wrong with squash API'}
    except Exception as err:
        print(f'Other error occurred: {err}')
        response = {'valid': False, 'error': 'Something went wrong with squash API'}

    # Extract the number of users in Squash API
    data = squashResponse.json()['page']
    totalUsers = data['totalElements']
    totalUsers = {'totalUsers': totalUsers}

    # Fill the DataBase with all new users
    try:
        fillUsersDataBase(squashResponse.json())
    except:
        response = {'valid': False, 'error': 'Something went wrong with MySQL Database'}

    # Return a json : {'valid':boolean,'error':string}
    return jsonify(response)


# Validate the email and password of the user. 
# Return {'valid' : true} if the email and password are the same as in the database
# Return {'error' : message d'erreur} if something if the email or password is incorrect or if the API couldn't connect to the phpmyadmin
@app.route('/validateuser', methods=["POST"])
def validateUser():
    response = validateUserMySQLRequest()
    
    # Return a json : {'valid':boolean,'error':string}
    return jsonify(response)


###########################################################################
############ All requests to MySQL database ###############################
###########################################################################

# Ask for the list of issues in the database
def collectAllIssuesInBDD():
    cursor = mysql.connection.cursor()
    query = "SELECT * FROM issues;"
    cursor.execute(query)
    mysqlresponse = cursor.fetchall()
    
    # Format response to json
    issues = []
    for i in mysqlresponse:
        issue = dict()
        issue.update({'number': i[0]})
        issue.update({'title': i[1]})
        issue.update({'link': i[2]})
        if i[3] == 0:
            issue.update({'workaround': False})
        else:
            issue.update({'workaround': True})

        creation = i[4].strftime("%Y-%m-%d")
        issue.update({'creation': creation})


        if i[5] != None:
            issue.update({'closure': i[5].strftime("%Y-%m-%d")})
        else:
            issue.update({'closure': i[5]})
        issues.append(issue)
    cursor.close()
    return issues

# Fill the user DataBase
def fillUsersDataBase(json):
    allUsers = getUsers(json)

    cursor = mysql.connection.cursor()
        
    # Executing SQL Statements
    for user in allUsers:
        # if the email isn't in the database, don't enter the person
        try:
            # Save the hashed password
            v = str(user['id']) + ", '"+user['email']+"', '"+pbkdf2_sha256.hash(password)+"'"
            query = "INSERT INTO users (id, email, password) values (" + v + ");"
            cursor.execute(query)
        except mysql.connection.Error as err:
            print(user['email']+" is already in the database or something go wrong with mysql.connection.")

    #Saving the Actions performed on the DB
    mysql.connection.commit()
 
    #Closing the cursor
    cursor.close()

    return True

# Delete and create a new database to store all issues
def fillIssuesDatabase(issues):

    # Create a cursor for connect to the database
    cursor = mysql.connection.cursor()

    # Suppress the table for recreate it
    query = "DROP TABLE IF EXISTS issues"
    cursor.execute(query)

    # Create a new Database with all the required field
    query = """CREATE TABLE issues (
    number INT PRIMARY KEY NOT NULL,
    title VARCHAR(255) NOT NULL,
    link VARCHAR(255) NOT NULL,
    workaround BOOLEAN NOT NULL,
    creation DATE,
    closure DATE)"""
    cursor.execute(query)

    # Insert issue in the database one by one
    for issue in issues:
        try:
            # Format the values
            number = str(issue['number'])
            title = "'" + issue['title'].replace("'", "\\'") + "'"
            link = "'" + issue['link'] + "'"
            workaround = str(issue['workaround'])
            if issue['creation'] != None :
                creation = "'" + issue['creation'] + "'"
            else:
                creation = "NULL"
            if issue['closure'] != None :
                closure = "'" + issue['closure'] + "'"
            else:
                closure = "NULL"

            values = number + ", " + title + ", " + link + ", " + workaround + ", " + creation + ", " + closure

            # The query mysql to send at the database
            query = 'INSERT INTO issues (number, title, link, workaround, creation, closure) VALUES (' + values + ');'

            # Sending of the query to the database
            cursor.execute(query)

            mysql.connection.commit()
        except mysql.connection.Error as err:
            print(err)
    
    cursor.close()

# Fill the tags DataBase
def fillTagsDatabase(tagList):
    # Create a cursor for connect to the database
    cursor = mysql.connection.cursor()

    # Suppress the table for recreate it
    query = "DROP TABLE IF EXISTS tags"
    cursor.execute(query)

    # Create a new Database with all the required field
    query = """CREATE TABLE tags (
    id INT PRIMARY KEY NOT NULL AUTO_INCREMENT,
    tag VARCHAR(50) NOT NULL)"""
    cursor.execute(query)

    # # Insert issue in the database one by one
    for tag in tagList:
        try:
            # Format the values
            value = "'" + tag + "'"

            # The query mysql to send at the database
            query = 'INSERT INTO tags (tag) VALUES (' + value + ');'

            # Sending of the query to the database
            cursor.execute(query)
            mysql.connection.commit()

        except mysql.connection.Error as err:
            print(err)

    cursor.close()

# Ask for the list of tags in the database
def collectAllTagsInBDD():
    cursor = mysql.connection.cursor()
    query = "SELECT * FROM tags;"
    cursor.execute(query)
    mysqlresponse = cursor.fetchall()
    
    # Format response to json
    tags = []
    for t in mysqlresponse:
        tags.append({'tag':t[1]})

    cursor.close()

    return tags

# Verify in the database if the user email and password are correct
def validateUserMySQLRequest():
    cursor = mysql.connection.cursor()
    input_json = request.get_json(force=True) 
    query = "SELECT email, password FROM users WHERE email = '"+input_json['email']+"';"
    cursor.execute(query)
    # row_count count the number of row return by the mysql database. If this email isn't in the database, return 0.
    row_count = cursor.rowcount
    if row_count == 0:
        # Return an error if the email isn't in the database
        response = {'valid' : False, 'error': 'This email isn\'t allowed to connect to IVV TOOLS.'}
    else:
        mysqlresponse = cursor.fetchall()
        for row in mysqlresponse :
            password = row[1] 
        # Verify if it's the same password; knowing the password in the database is hashed
        if pbkdf2_sha256.verify(input_json['password'], password):
            response = {'valid': True, 'error': 'None'}
        else:
            # Return an error if the password isn't the same as the one in the database
            response = {'valid' : False, 'error': 'The password is incorrect.'}
    cursor.close()
    return response

# ! Not used function
# Ask if an user is in the DataBase
# Return True if the email is in the database
# Return False if the email isn't in the database
def findOneUserEmail(email):

    cursor = mysql.connection.cursor()

    query = "SELECT email FROM users WHERE email = '"+email+"';"
    
    cursor.execute(query)
    row_count = cursor.rowcount

    mysql.connection.commit()
 
    cursor.close()

    if row_count == 0:
        # Return False if the email isn't in the database
        return False
    else:
        # Return True if the email is in the database
        return True

###########################################################################
############ Others functions #############################################
###########################################################################

# Get User's email 
# Need the id in squash api of the User in parameter
def getUserEmail(id):
    # Create the url for requesting a user by his id
    getOneUser_api = squash_get_all + "/" + str(id)

    try:
        response = requests.get(getOneUser_api, auth=(squash_user, squash_pwd), headers=headers)
        response.raise_for_status()
    except HTTPError as http_err:
        print(f'HTTP error occurred: {http_err}')
        
    except Exception as err:
        print(f'Other error occurred: {err}')

    user = {'email' : response.json()['email']}

    return user

# Get a json with the id and the email of all Users in the json
# The json must be the json given by squash API
def getUsers(json):

    allUsersId = getUsersId(json)

    allUsers = []

    for id in allUsersId:
        userEmail = getUserEmail(id)

        # if the user have no email, don't save him
        if userEmail['email'] != '':
            emailAndId = {'id': id, 'email': userEmail['email']}
            allUsers.append(emailAndId)
    
    return allUsers

# Get all users' id in the json given by squash getAllUser function
def getUsersId(json):
    allUsers = json['_embedded']

    allUsersId = []

    for user in allUsers['users']:
        allUsersId.append(user['id'])       

    return allUsersId

# Extract data from the list of all issues received from github API
# Keep only the data that have a 'ivv' or 'bug' tag
# Save only : the number, the title, the html_url, the creation date, the closure date and workaround
def formateIssuesListForMySQL(githubresponse):
    issues = []
    for state in ["open","closed"]:          
        listing = githubresponse.issues_on("COPRS", "rs-issues", state=state)
        for i in listing:
            # Save this bug only if labels are 'bug' and 'ivv'
            if all(x in str(i.original_labels) for x in base):
                issue = dict()
                issue.update({'number': i.number})
                issue.update({'title': i.title.replace("[BUG]", "")})
                issue.update({'link': i.html_url})
                if i.created_at is not None:
                    issue.update({'creation': i.created_at.strftime("%Y-%m-%d")})
                else:
                    issue.update({'creation': None})
                if i.closed_at is not None:
                    issue.update({'closure': i.closed_at.strftime("%Y-%m-%d")})
                else:
                    issue.update({'closure': None})
                if (workaround in str(i.original_labels)):
                    issue.update({'workaround': True})
                else:
                    issue.update({'workaround': False})
                issues.append(issue)
    return issues

# Extract the tags of title, every string between a '[' and a ']' is added as a tag
# Return a set with all tags
def extractTagsOfIssuesfromTitle(formatedIssuesList):
    tagList = set()
    for issue in formatedIssuesList:
        # Prevent the possibility to obtain the same tag many time like [Infra] and [infra]
        # Make all character of the title in lower case
        lowerTitle = issue['title'].lower()
        tag = ""
        captureTag = False
        # Run through every character of the title one by one
        for character in lowerTitle:

            # Identify the end of the tag, save the tag in the set
            if(character == "]"):
                captureTag = False
                tagList.add(tag)
                tag = ""
            
            # Save the tag name character by character
            if(captureTag == True):
                tag = tag + character

            # Identify the beginning of a tag
            if(character == "["):
                captureTag = True;

    return tagList

###########################################################################
################### Unit Test #############################################
###########################################################################

# Request all issues in the database
@app.route('/unittestnumberofbugs', methods=["POST"])
def unitTest():

    # Login to Github
    try:
        githubresponse = login(token=token)
    except ValueError:
        print("Github connexion issue or token invalid")
        response = {'valid': False, 'error': 'Github connexion issue or token invalid'}

    allCount = dict()
    allCount.update({"all":count(["open", "closed"], githubresponse)})
    allCount.update({"NotClose":count(["open"], githubresponse)})
    allCount.update({"Close":(allCount['all']-allCount['NotClose'])})
    allCount.update({"Workaround":countWorkaround(githubresponse)})
    allCount.update({"NoWorkaround":(allCount['all']-allCount['Workaround'])})

    return allCount

def count(test, githubresponse):
    count = 0
    for state in test:          
        listing = githubresponse.issues_on("COPRS", "rs-issues", state=state)
        for i in listing:
            # Save this bug only if labels are 'bug' and 'ivv'
            if all(x in str(i.original_labels) for x in base):
                count = count + 1
    return count

def countWorkaround(githubresponse):
    count = 0
    for state in ["open","closed"]:      
        listing = githubresponse.issues_on("COPRS", "rs-issues", state=state)
        for i in listing:
            # Save this bug only if labels are 'bug' and 'ivv'
            if all(x in str(i.original_labels) for x in base):
                if (workaround in str(i.original_labels)):
                    count = count + 1
    return count

def countNoWorkaround(githubresponse):
    count = 0
    for state in ["open","closed"]:      
        listing = githubresponse.issues_on("COPRS", "rs-issues", state=state)
        for i in listing:
            # Save this bug only if labels are 'bug' and 'ivv'
            if all(x in str(i.original_labels) for x in base):
                if not (workaround in str(i.original_labels)):
                    count = count + 1
    return count