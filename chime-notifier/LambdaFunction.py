# Sample Lambda Function to post notifications to a Chime room when an AWS Health event happens
from __future__ import print_function
import json
import logging
import os
from urllib2 import Request, urlopen, URLError, HTTPError
# Setting up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)
# main function
def lambda_handler(event, context):
    """Post a message to the Chime Room when a new AWS Health event is generated"""
    message =  str(event['detail']['eventDescription'][0]['latestDescription']  + " https://phd.aws.amazon.com/phd/home?region=us-east-1#/event-log?eventID=" + event['detail']['eventArn'])
    json.dumps(message)
    chime_message = {'Content': message}
    logger.info(str(chime_message))
    webhookurl = str(os.environ['CHIMEWEBHOOK'])
    req = Request(webhookurl, json.dumps(chime_message))
    try:
        response = urlopen(req)
        response.read()
        logger.info("Message posted: %s", chime_message['Content'])
    except HTTPError as e:
        logger.error("Request failed : %d %s", e.code, e.reason)
    except URLError as e:
        logger.error("Server connection failed: %s", e.reason)

