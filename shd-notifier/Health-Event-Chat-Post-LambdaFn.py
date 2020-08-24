# Health-Event-Chat-Post-LambdaFn
# Lambda Function to post open issues from an AWS event to a
# Amazon Chime or Slack room setup by the ENDPOINTARRAY environment variable

# Input: eventArn -  Event ARN to post to the Amazon Chime room
#        lastUpdatedTime - String with when the event was last updated
#                          If not set defaults to blank
#        Environment variables for DEBUG, MESSAGEPREFIX,ENDPOINTARRAY,CHATCLIENT
#        ENDPOINTARRAY is required
# Output: returns a string of the time the event was last updated.

# Imports
import json  # essential to read json
import os  # required to read in the os variable for the Webhook
import logging  # handy to keep track of things
import boto3  # AWS CLI, required to poll AWS Health


from urllib.request import Request, urlopen # for chime API
from urllib.error import URLError, HTTPError


# Static vars
MAXCHIMEPOST = 4096  # Maximum number of characters a chime post will accept
CHIMEPOSTTRIM = 3800  # Truncated message size, must be < (4096-message encoding)
STATUSLINK = 'http://status.aws.amazon.com'  # Status URL for messages truncated
# Read in the OS environment variables, default any missing vars
# read in the debugging flag, if 1 enable debug log level and some messages, defaults to 0
DEBUG = int(os.getenv('DEBUG', 0))  # set DEBUG environment variable to 1 to enable testing
# read in the BAIL_NOCHANGE flag. defaults to 0
BAIL = int(os.getenv('BAIL_NOCHANGE', 0))  # set to 1 to enable bailing on no update
# Setting up logging, default to INFO level
logger = logging.getLogger()
if (DEBUG):
    logger.setLevel(logging.DEBUG)
    logger.debug("DEBUGGING ON")  # send debug status
else:
    logger.setLevel(logging.INFO)
# read in the chime message tag to add to the post
MESSAGEPREFIX = str(os.getenv('MESSAGEPREFIX', '[AUTO Post] '))
logger.debug("MESSAGEPREFIX= %s" % MESSAGEPREFIX)
# read in the chat client type, default to chime
CHATCLIENT = str(os.getenv('CHATCLIENT', 'chime'))
logger.debug("CHATCLIENT= %s" % CHATCLIENT)


# Trims a message to fit inside the Chime character limit
# Input: message to shorten
# Expects CHIMEPOSTTRIM and STATUSLINK static vars
# Output: shortened message, with a decription of the trim
def chimeTrimMessage(message):
    if (DEBUG): logger.debug(("Message Original Length: %i") % (len(message)))
    message = message[:CHIMEPOSTTRIM] + "\n\n[MESSAGE TRUNCATED] For the full message refer to " + STATUSLINK
    if (DEBUG): logger.debug(("Message Truncated Length: %i") % (len(message)))
    return message


# Post the message to an sns topic
# Inputs: topic - arn of the topic to publish to
#         message - message string
def snsMessage(topic, subject, message):
    client = boto3.client("sns")
    return client.publish(TopicArn=topic, Message=message, Subject=subject)


# Post the message to the chat webhook
# Inputs: message - supported message string
#         webhook - webhook URL to post the message to
#         type - 'chime'||'slack' as a string, defaults to chime
# Output 1 on success
def chatMessage(message, subject, webhook, type):
    # detect if we are using slack, otherwise default to chime
    if (type == 'slack'):
        chat_message = {'text': message}
    elif type == 'sns':
        return snsMessage(webhook, subject, message)
    else:
        chat_message = {'Content': message}

    # log the chat message
    logger.info(str(chat_message))
    # post the message, catch and log any errors
    header = {'Content-type': 'application/json'}
    req = Request(webhook, json.dumps(chat_message).encode('utf8'), header)
    try:
        response = urlopen(req)
        response.read()
        if (type == 'slack'):
            logger.info("Message posted: %s", chat_message['text'])
        else:
            logger.info("Message posted: %s", chat_message['Content'])
    except HTTPError as e:
        logger.error(e)
        eMessage = "WEBHOOK HTTP Request failed : %d %s" % (e.code, e.reason)
        logger.error(eMessage)
        raise Exception(eMessage)
    except URLError as e:
        logger.error(e)
        eMessage = "WEBHOOK Server connection failed: %s" % (e.reason)
        logger.error(eMessage)
        raise Exception(eMessage)
    # successful post
    return 1


# Given an event return its latest description string
# Input: eventArn - string with the events AWS ARN
# Output: one detail object
def eventDetailedDesc(eventArn):
    # Load the AWS Health API
    health = boto3.client('health', region_name='us-east-1')

    # get the event details
    try:
        details = health.describe_event_details(
            eventArns=[eventArn]
        )
    except Exception as e:
        logger.error(e)
        eMessage = 'ERROR: Unable to retrieve events details'
        logger.error(eMessage)
        raise Exception(eMessage)
    # we expect one success result, otherwise raise an exception
    if (len(details['successfulSet']) is not 1):
        eMessage = "Unable to retrieve details for event ARN: %s" % eventArn
        logger.error(eMessage)
        raise Exception(eMessage)
    # since we know we only have one, return the 1 detail
    return details['successfulSet'][0]


#
# Main lambda function
#
def lambda_handler(event, context):
    # read in the webhook to post too, since it is required error out if it is missing
    try:
        ENDPOINTARRAY = str(os.environ['ENDPOINTARRAY'])
        ENDPOINTARRAY = json.loads(ENDPOINTARRAY)
    except Exception as e:
        logger.error(e)
        eMessage = 'ERROR: Missing ENDPOINTARRAY Environment Variable for the Lambda Function!'
        logger.error(eMessage)
        raise Exception(eMessage)

    # read in the eventArn, error out if it is missing
    try:
        eventArn = event['eventArn']
    except Exception as e:
        logger.error(e)
        eMessage = 'ERROR: Invalid input, Event ARN Invalid!'
        logger.error(eMessage)
        raise Exception(eMessage)

    # read in the events name from the ARN
    # Health ARN Pattern: arn:aws:health:[^:]*:[^:]*:event/[\w-]+
    eventIDPos = eventArn.rfind('/')
    if (eventIDPos > 1): eventIDPos = eventIDPos + 1
    eventName = eventArn[eventIDPos:]
    logger.info("Event name: %s" % (eventName))

    # read in the lastUpdatedTime, if missing default to blank
    try:
        lastUpdatedTime = event['lastUpdatedTime']
    except Exception as e:
        eMessage = "WARN: Missing lastUpdatedTime defaulting to blank."
        logger.debug(eMessage)
        lastUpdatedTime = ''
    logger.debug("lastUpdatedTime: %s" % (lastUpdatedTime))

    # get the latest detailed description of the event
    detail = eventDetailedDesc(eventArn)
    # we want the events latest description
    latestDesc = detail['eventDescription']['latestDescription']
    # get this details last updated time
    curLastUpdatedTime = str(detail['event']['lastUpdatedTime'])
    logger.debug("curLastUpdatedTime: %s" % (curLastUpdatedTime))
    if (curLastUpdatedTime == lastUpdatedTime):
        if BAIL == 1:
            return curLastUpdatedTime
        latestDesc = "Event unchanged since the last update."

    # create the latest description posting
    message = ''
    eventNameStr = "[%s] " % eventName
    if (DEBUG):
        message = '[TESTING] PLEASE IGNORE DEBUGGING:\n'
    message = message + MESSAGEPREFIX
    if CHATCLIENT == 'sns':
        message = message + '\n\n'
    message = message + eventNameStr + latestDesc
    # trim messages larger than the maximum post size (4KB)
    if (len(message) > MAXCHIMEPOST):
        message = chimeTrimMessage(message)
    # post the message to the array of webhooks
    for webhook in ENDPOINTARRAY:
        chatMessage(message, eventNameStr, webhook, CHATCLIENT)
    # return the current updated time as the last updated time
    return curLastUpdatedTime

