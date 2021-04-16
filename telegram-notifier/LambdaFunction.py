from __future__ import print_function

import boto3
import json
import logging
import os
import urllib
from urllib2 import Request, urlopen, URLError, HTTPError

"""
BOT_ID = Your Telegram BOT ID. Example: bot123456789:XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
CHAT_ID = Is your channel ID or your BOT chat window id
"""

BOT_ID = "bot123456789:XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
CHAT_ID = "01234567891234"
API_ENDPOINT = "https://api.telegram.org/%s/sendMessage" % BOT_ID

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    message = str(event['detail']['eventDescription'][0]['latestDescription'] + "\n\n<https://phd.aws.amazon.com/phd/home?region=us-east-1#/event-log?eventID=" + event['detail']['eventArn'] + " | Click here> for details.")

    msg = {
        "chat_id":CHAT_ID,
        "text": message
    }

    logger.info(str(msg))

    req = Request(API_ENDPOINT, urllib.urlencode(msg))
    try:
        response = urlopen(req)
        response.read()
        logger.info("Message posted to %s", CHAT_ID)
    except HTTPError as e:
        logger.error("Request failed: %d %s", e.code, e.reason)
    except URLError as e:
        logger.error("Server connection failed: %s", e.reason)
