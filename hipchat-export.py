#!/usr/bin/env python
# encoding: utf-8
"""
hipchat_export.py

Created by Adam Mikeal on 2016-04-13.
Copyright (c) 2016 Adam Mikeal. All rights reserved.
"""

import requests
import sys
import io
import os
from urlparse import urlparse
from os.path import splitext, basename
import getopt
import json
from datetime import date, datetime
from time import sleep
import time
import dateutil.parser
import urllib

help_message = '''
A simple script to export 1-to-1 messages from HipChat using the v2 API
found at http://api.hipchat.com/v2.

Usage: python hipchat_export.py [options]

Options:
  -v                  Run verbosely
  -h, --help          Show this help file
  -l, --list          List the active users that will be queried
  -u, --user_token    Your API user token
                        *** Generate this token online at
                        https://coa.hipchat.com/account/api ***

Example:
  hipchat_export.py --user_token jKHxU8x6Jj25rTYaMuf6yTe7YpQ6TV413EUkBd0Z

After execution, a 'hipchat_export' folder will be created in the current
working directory, and folders will be created for each person it will ask
for 1-to-1 chat history (this list is determined by a dictionary in the main()
function). Uploaded binary files will be found in an 'uploads' folder, with a
path that partially matches the filepath recorded in the API data (the domain
and common URI path information is stripped).

The message data is stored as the raw JSON file, in files named 0.txt through
n.txt; as many as needed to fetch all the messages between you and that user.

NOTE: HipChat rate limits the API calls you can make with a user token to 100
call every 5 minutes. This script will track how many calls have been made to
the API, and before it hits 100 will insert a 5 minute pause.
'''

# Flag for verbosity
VERBOSE = False
EXPORT_DIR = os.path.join(os.getcwd(), 'hipchat_export')
TOTAL_REQUESTS = 0
reload(sys)  
sys.setdefaultencoding('utf8')

def RateLimited(maxPerSecond):
    minInterval = 1.0 / float(maxPerSecond)
    def decorate(func):
        lastTimeCalled = [0.0]
        def rateLimitedFunction(*args,**kargs):
            elapsed = time.clock() - lastTimeCalled[0]
            leftToWait = minInterval - elapsed
            if leftToWait>0:
                time.sleep(leftToWait)
            ret = func(*args,**kargs)
            lastTimeCalled[0] = time.clock()
            return ret
        return rateLimitedFunction
    return decorate

def log(msg):
    if msg[0] == "\n":
        msg = msg[1:]
        log(' ')
    logit = '[%s] %s' % (datetime.now(), msg)
    print logit.encode('utf8')

def vlog(msg):
    if VERBOSE:
        log(msg)

@RateLimited(.50)  # .5 per second at most
def rated_requests(url, user_token=None):
    vlog('requesting: ' + str(url))
    if user_token:
        # Set HTTP header to use user token for auth
        headers = {'Authorization': 'Bearer ' + user_token }
        res = requests.get(url, headers=headers)
    else:
        res = requests.get(url)

    if 'X-RateLimit-Remaining' in res.headers:    
        api_limit = res.headers['X-RateLimit-Remaining']
    else:
        api_limit = 'Unlimited'
    vlog('api limit:' + str(api_limit) + ' status: ' + str(res.status_code) + ' url:' + url)
    if res.status_code == 429:
        log('rate limit reached, sleeping for 30 seconds')
        sleep(30)
        res = rated_requests(url, user_token)
    return res

def get_user_list(user_token):

    # Return value will be a dictionary
    user_list = {}

    # Fetch the user list from the API
    url = "http://api.hipchat.com/v2/user"
    more_people = True
    while more_people:
        r = rated_requests(url, user_token)
        vlog('user count: ' + str(len(r.json()['items'])))
        vlog('message: ' + str(r.json()))
        # Iterate through the users and make a dict to return
        for person in r.json()['items']:
            person_req = rated_requests(person['links']['self'], user_token)
            person_details = person_req.json()
            new_person = {'name': person['name'], 
                          'email': person_details['email'], 
                          'person':person, 
                          'details': person_details}
            user_list[str(person['id'])] = new_person
            # if len(user_list) > 2:
            #    break
        # check for more records to process
        if 'next' in r.json()['links']:
            url = r.json()['links']['next']
            LEVEL += 1
        else:
            more_people = False
           
        
    # Return the dict
    return user_list

def display_userlist(user_list):
    print "\nThe following users are active and will be queried for 1-to-1 messages:\n"
    for id, person in user_list.items():
        log(person['name'] + ' <' + person['email'] + '>, id: ' + str(id))

def message_export(user_token, user_id, person):
    log('processing: ' + person['name'] + ' <' + person['email'] + '>, id: ' + str(user_id))

    # create dirs for current user
    dir_name =  os.path.join(EXPORT_DIR, person['name'])
    if not os.path.isdir(dir_name):
        os.makedirs(dir_name)

    # flag to control pagination
    MORE_RECORDS = True

    # flag to track iteration through pages
    LEVEL = 0

    # track the total number of requests made, so we can avoid the rate limit
    global TOTAL_REQUESTS

    # Set initial URL with correct user_id, current time
    utc_time = datetime.utcnow().isoformat()
    url = "http://api.hipchat.com/v2/user/%s/history?date=%s&reverse=false&max-results=1000" % (user_id, utc_time)

    start_html = '''
    <!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01//EN"
        "http://www.w3.org/TR/html4/strict.dtd">
    <html lang="en">
      <head>
        <meta http-equiv="content-type" content="text/html; charset=utf-8">
        <title>%s</title>
        <link rel="stylesheet" type="text/css" href="style.css">
        <script type="text/javascript" src="script.js"></script>
    '''
    
    end_html = '''
            
      </body>
    </html>
    '''
    message_css = ''' 
    <style>
    p { margin:0; padding:0}
            .message {
                display: table-cell;
                padding: 0 10px;
                line-height: 20px;
                max-width: 0px;
            }

            .message-self {
                background: #e0eaf3;
                border-top: solid #fff 1px; 
            }

            .author {
                color: #4a6785;
                font-family: Helvetica Neue, Helvetica, Arial, sans-serif;
                vertical-align: top;
                margin-left: 20px; 
                font-weight: 500;
                height: auto; 
                float: left;
                line-height: 1.42857142857143;
            }

            .chat-row {
                font-size: 14px;
                line-height: 20px;
                display: table;
                table-layout: fixed;
                width: 100%;
                padding: 8px 0px;
                border-top: 1px solid #e9e9e9;
                box-sizing: border-box;
                position: relative;
                overflow: hidden;
                transition: background-color 150ms ease-in-out;
            }

            .text {
                /*float: left; */
                color: #333;
                font-family: Helvetica Neue, Helvetica, Arial, sans-serif;
                font-size: 14px;
                line-height: 20px;
                margin: 0;
                padding-left: 20px;
                display: block;
            }

            .time {
                vertical-align: top;
                color: #999999;
                text-align: left;
                font-size: 11px;
                white-space: nowrap;
                font-family: Helvetica Neue, Helvetica, Arial, sans-serif; 
                margin-right: 20px; 
                font-weight: bold; 
                font-size: 0.8em; 
            }

            .separator {
                color: #707070;
                padding: 0 5px;
            }

            .line {
                width: 80%;
                height: 1px;
                background-color: #CCCCCC;
                clear: both;

            margin: 0 auto;
        }
    </style>
    </head>
    <body>
    '''

    message_html = '''
    <div class="chat-row">
        <div class="%s">
          <span class="author">%s</span>
          <span class="separator">·</span>
          <span class="time">%s</span>
          <div class="text">%s</div>
        </div>
    </div>
    '''
    img_html = '<div class="image"><img src="./%s"></div>'
    
    # main loop to fetch and save messages
    while MORE_RECORDS:
        # fetch the JSON data from the API
        vlog("Fetching URL: %s" % (url))
        r = rated_requests(url, user_token)

        # TODO - check response code for other errors and report out
        if not r.status_code == requests.codes.ok:
            r.raise_for_status()   

        # check JSON for objects and react
        if 'items' not in r.json():
            raise Usage("Could not find messages in API return data... Check your token and try again.")

        # write the current JSON dump to file
        json_file_name = os.path.join(EXPORT_DIR, person['name'], person['name'] + '_' + str(LEVEL)+ '.json')
        vlog("  + writing JSON to disk: %s" % (json_file_name))
        with io.open(json_file_name, 'w', encoding='utf-8') as f:
            f.write(json.dumps(r.json(), sort_keys=True, indent=4, ensure_ascii=False))

        html_file_name = os.path.join(EXPORT_DIR, person['name'], person['name'] + '_' + str(LEVEL)+'.html')
        vlog("  + writing JSON to disk: %s" % (json_file_name))
        html_file = io.open(html_file_name, 'w', encoding='utf-8')
        html_file.write(unicode(start_html % html_file_name))
        html_file.write(unicode(message_css))

        # write html, scan for any file links (aws), fetch them and save to disk
        vlog("  + looking for file uploads in current message batch...")
        vlog(str(person))
        for item in r.json()['items']:
            date_time = dateutil.parser.parse(item['date'])
            time = date_time.strftime('%b-%d %I:%M %p')
            author = item['from']['mention_name']
            if person['details']['id']==item['from']['id']:
                css = "message"
            else:
                css = "message message-self"

            html_file.write(message_html % (css, author, time, item['message']))
            if 'file' in item:
                vlog("  + fetching file: %s" % (item['file']['url']))
                r2 = rated_requests(item['file']['url'])

                # extract the unique part of the URI to use as a file name
                disassembled = urlparse(item['file']['url'])
                path = urllib.unquote(disassembled.path).decode('utf8') 
                filename, file_ext = splitext(basename(path))
                fpath = os.path.join(EXPORT_DIR, person['name'], (filename + file_ext))

                # ensure full dir for the path exists
                temp_d = os.path.dirname(fpath)
                if not os.path.exists(temp_d):
                    os.makedirs(temp_d)

                # now fetch the file and write it to disk
                vlog("  --+ writing to disk: %s" % (fpath))
                with open(fpath, 'w+b') as fd:
                    for chunk in r2.iter_content(1024):
                        fd.write(chunk)
                html_file.write(unicode(img_html % (filename + file_ext)))
        html_file.write(unicode(end_html))
        # check for more records to process
        if 'next' in r.json()['links']:
            url = r.json()['links']['next']
            LEVEL += 1
        else:
            MORE_RECORDS = False
    #end loop

class Usage(Exception):
    def __init__(self, msg):
        self.msg = msg


def main(argv=None):
    # initialize variables
    global VERBOSE
    ACTION = "PROCESS"
    USER_TOKEN = None
    USER_LIST = {}

    if argv is None:
        argv = sys.argv
    try:
        try:
            opts, args = getopt.getopt(argv[1:], "hlu:v", ["help", "list", "user_token="])
        except getopt.error, msg:
            raise Usage(msg)

        # option processing
        for option, value in opts:
            if option in ("-h", "--help"):
                print help_message
                sys.exit(0)
            if option in ("-l", "--list"):
                ACTION = "DISPLAY"
            if option == "-v":
                VERBOSE = True
            if option in ("-u", "--user_token"):
                USER_TOKEN = value

        # ensure that the token passed is a valid token length (real check happens later)
        if not USER_TOKEN or not len(USER_TOKEN) == 40:
            raise Usage("You must specify a valid HipChat user token!")

        # Get the list of users
        USER_LIST = get_user_list(USER_TOKEN)

        # If the action is listing only, display and exit
        if ACTION == "DISPLAY":
            display_userlist(USER_LIST)
            sys.exit(0)

        # Iterate through user list and export all 1-to-1 messages to disk
        for user_id, person in USER_LIST.items():
            log("\nExporting 1-to-1 messages for %s (ID: %s)..." % (person['name'], user_id))
            message_export(USER_TOKEN, user_id, person)

    except Usage, err:
        print >> sys.stderr, sys.argv[0].split("/")[-1] + ": " + str(err.msg)
        print >> sys.stderr, "\t for help use --help"
        return 2


if __name__ == "__main__":
    sys.exit(main())
