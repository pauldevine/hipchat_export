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
  --very_verbose      Run very verbosely
  -h, --help          Show this help file
  -l, --list          List the active users that will be queried
  -j                  Output json file of messages
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
VERY_VERBOSE = False
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
    if VERBOSE or VERY_VERBOSE:
        log(msg)

def vvlog(msg):
    if VERY_VERBOSE:
        log(msg)

@RateLimited(.50)  # .5 per second at most
def rated_requests(url, user_token=None):
    vvlog('requesting: ' + str(url))
    if user_token:
        # Set HTTP header to use user token for auth
        headers = {'Authorization': 'Bearer ' + user_token }
        res = requests.get(url, headers=headers)
    else:
        res = requests.get(url)

    if 'X-RateLimit-Remaining' in res.headers:    
        api_limit = res.headers['X-RateLimit-Remaining']
        vlog('api limit:' + str(api_limit) + ' status: ' + str(res.status_code) + ' url:' + url)
    else:
        api_limit = 'Unlimited'
    
    if res.status_code == 429:
        log('rate limit reached, sleeping for 30 seconds')
        sleep(30)
        res = rated_requests(url, user_token)
    return res

def get_current_user(user_token):
    url = 'http://api.hipchat.com/v2/oauth/token/' + user_token
    r = rated_requests(url, user_token)
    owner = r.json()['owner']
    vlog('current user name: ' + owner['name'] + 
        ' id: ' + str(owner['id']) + ' mention_name: ' + owner['mention_name'] )
    return owner

def get_user_list(user_token):

    # Return value will be a dictionary
    user_list = {}

    # Fetch the user list from the API
    url = "http://api.hipchat.com/v2/user"
    more_people = True
    while more_people:
        r = rated_requests(url, user_token)
        vlog('user count: ' + str(len(r.json()['items'])))
        vvlog('message: ' + str(r.json()))
        # Iterate through the users and make a dict to return
        for person in r.json()['items']:
            person_req = rated_requests(person['links']['self'], user_token)
            person_details = person_req.json()
            new_person = {'name': person['name'], 
                          'email': person_details['email'], 
                          'person':person, 
                          'details': person_details}
            user_list[str(person['id'])] = new_person
            #if len(user_list) > 2:
            #    break
        # check for more records to process
        if 'next' in r.json()['links']:
            url = r.json()['links']['next']
        else:
            more_people = False
           
        
    # Return the dict
    return user_list

def display_userlist(user_list):
    print "\nThe following users are active and will be queried for 1-to-1 messages:\n"
    for id, person in user_list.items():
        log(person['name'] + ' <' + person['email'] + '>, id: ' + str(id))

def message_export(user_token, owner, user_id, person, create_json):

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
    link_html = '<div class="link"><a href="./%s">%s</a></div>'

    log('processing: ' + person['name'] + ' <' + person['email'] + '>, id: ' + str(user_id))

    # flag to track iteration through pages
    page = 0

    # Set initial URL with correct user_id, current time
    utc_time = datetime.utcnow().isoformat()
    url = "http://api.hipchat.com/v2/user/%s/history?date=%s&reverse=false&max-results=1000" % (user_id, utc_time)
    
    # fetch the JSON data from the API
    vlog("Fetching URL: %s" % (url))
    r = rated_requests(url, user_token)

    # only enter loop if we have records to process
    if len(r.json()['items']) > 0:
        more_records = True
    else:
        more_records = False

    if more_records:
        export_dir = os.path.join(os.getcwd(), owner['name'])

        # create dirs for current user
        user_dir =  os.path.join(export_dir, person['name'])
        if not os.path.isdir(user_dir):
            os.makedirs(user_dir)

    # main loop to fetch and save messages
    while more_records:
        # TODO - check response code for other errors and report out
        if not r.status_code == requests.codes.ok:
            r.raise_for_status()   

        # check JSON for objects and react
        if 'items' not in r.json():
            raise Usage("Could not find messages in API return data... Check your token and try again.")

        # write the current JSON dump to file
        if create_json:
            json_file_name = os.path.join(user_dir, person['name'] + '_' + str(page)+ '.json')
            vlog("  + writing JSON to disk: %s" % (json_file_name))
            with io.open(json_file_name, 'w', encoding='utf-8') as f:
                f.write(json.dumps(r.json(), sort_keys=True, indent=4, ensure_ascii=False))
                f.close()

        # write the initial HTML to setup for messages later
        html_file_name = os.path.join(user_dir, person['name'] + '_' + str(page)+'.html')
        vlog("  + writing HTML to disk: %s" % (html_file_name))
        html_file = io.open(html_file_name, 'w', encoding='utf-8')
        html_file.write(unicode(start_html % html_file_name))
        html_file.write(unicode(message_css))

        # write html, scan for any file links (aws), fetch them and save to disk
        vlog("  + looking for file uploads in current message batch of %s messages" % str(len(r.json()['items'])))
        vvlog(str(person))
        for item in r.json()['items']:
            date_time = dateutil.parser.parse(item['date'])
            time = date_time.strftime('%b-%d-%Y %I:%M %p')
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
                fpath = os.path.join(user_dir, (filename + file_ext))

                # ensure full dir for the path exists
                temp_d = os.path.dirname(fpath)
                if not os.path.exists(temp_d):
                    os.makedirs(temp_d)

                # now fetch the file and write it to disk
                vlog("  --+ writing to disk: %s" % (fpath))
                with open(fpath, 'w+b') as fd:
                    for chunk in r2.iter_content(1024):
                        fd.write(chunk)
                    fd.close()
               
                embed = (filename + file_ext)
                if file_ext in [".png", ".gif", ".jpg"]:
                    html_file.write(unicode(img_html % embed))
                else:
                    html_file.write(unicode(link_html % (embed, embed)))
        
        html_file.write(unicode(end_html))
        html_file.close()
        
        # check for more records to process

        if len(r.json()['items']) == 1000:
            utc_time = r.json()['items'][-1]['date']
            url = "http://api.hipchat.com/v2/user/%s/history?date=%s&reverse=false&max-results=1000" % (user_id, utc_time)
            vlog("Fetching additional page messages URL: %s" % (url))
            r = rated_requests(url, user_token)
            page += 1
        else:
            more_records = False

class Usage(Exception):
    def __init__(self, msg):
        self.msg = msg


def main(argv=None):
    # initialize variables
    global VERBOSE
    global VERY_VERBOSE
    ACTION = "PROCESS"
    USER_TOKEN = None
    USER_LIST = {}
    CREATE_JSON = False

    if argv is None:
        argv = sys.argv
    try:
        try:
            opts, args = getopt.getopt(argv[1:], "hlu:vjd", ["help", "list", "debug", "user_token="])
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
            if option in ("-d", "--debug"):
                VERY_VERBOSE = True
            if option == "-j":
                CREATE_JSON = True
            if option in ("-u", "--user_token"):
                USER_TOKEN = value

        # ensure that the token passed is a valid token length (real check happens later)
        if not USER_TOKEN or not len(USER_TOKEN) == 40:
            raise Usage("You must specify a valid HipChat user token!")

        #get the owner who we're exporting
        OWNER = get_current_user(USER_TOKEN)
        log("\nExporting 1-to-1 messages for user: %s (ID: %s) Mention Name: %s" % 
            (OWNER['name'], str(OWNER['id']), OWNER['mention_name']))

        # Get the list of users
        USER_LIST = get_user_list(USER_TOKEN)

        # If the action is listing only, display and exit
        if ACTION == "DISPLAY":
            display_userlist(USER_LIST)
            sys.exit(0)

        # Iterate through user list and export all 1-to-1 messages to disk
        count = len(USER_LIST.items())
        num=1
        for user_id, person in USER_LIST.items():
            log("\nExporting 1-to-1 messages for %s (ID: %s) %i of %i" % (person['name'], user_id, num, count))
            message_export(USER_TOKEN, OWNER, user_id, person, CREATE_JSON)
            num += 1
        log("\nDone with %s (ID: %s)" % (OWNER['name'], str(OWNER['mention_name'])))

    except Usage, err:
        print >> sys.stderr, sys.argv[0].split("/")[-1] + ": " + str(err.msg)
        print >> sys.stderr, "\t for help use --help"
        return 2


if __name__ == "__main__":
    sys.exit(main())
