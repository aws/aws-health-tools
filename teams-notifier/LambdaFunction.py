#Sample Lambda Function to post notifications to a Teams room when an AWS Health event happens
import json
import logging
import os

from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

TEAMSWEBHOOK = ""

# Setting up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# main function
def lambda_handler(event, context):
    """Post a message to the Teams Room when a new AWS Health event is generated"""
    message =  str(event['detail']['eventDescription'][0]['latestDescription']  + " https://phd.aws.amazon.com/phd/home?region=us-east-1#/event-log?eventID=" + event['detail']['eventArn'])
    json.dumps(message)
    
    teams_message = {
        "@context": "https://schema.org/extensions",
        "@type": "MessageCard",
        "title": "AWS - Personal Health Updates",
        "text": message
    }
    
    logger.info(str(teams_message))
    req = Request(TEAMSWEBHOOK, json.dumps(teams_message).encode('utf-8'))

    try:
        response = urlopen(req)
        response.read()
        logger.info("Message posted")
        return {"status": "200 OK"}
    except HTTPError as e:
        logger.error("Request failed : %d %s", e.code, e.reason)
    except URLError as e:
        logger.error("Server connection failed: %s", e.reason)
