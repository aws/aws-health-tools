# Health-Event-Poller-lambdaFn
# Lambda Function to poll for open health events and execute a Step Function
# (SFN) - state machine to deal with them

# Inputs: Optional environment variables
#           DEBUG - enables debugging, only will start one SFN
#           WAIT_TIME - minutes to wait before reposting event status to Chime
# Outputs: Executes a SFN, one for each open event detected.
#          Since the event name matches the SFN name, duplicate executions
#          of the same event will be rejected.
# Notes: Pagination is not supported, we handle a maximum of 100 open events
# 

import json # essential to read json
import os # required to read in the os variable for the Webhook
import logging # handy to keep track of things
import boto3 # AWS CLI, required to poll AWS Health
from botocore.exceptions import ClientError

# Static vars
eventStatusCodes='open' # open events only, for debug try closed
eventTypeCategories='issue' # SHD events are always issues
maxEvents=100 # That is the maximum events that can be pulled in one operation
# for now hard coded the name of the SFN ARN to run against
stateMachineArn=os.getenv('SFN_ARN','')
maxEventID=80 # maximum size of the name parameter passed to SFN
defWaitTime=15 # default the wait time to 15

# Read in the OS environment variables, default any missing vars
# read in the debugging flag, if 1 enable debug log level and some messages, defaults to 0
DEBUG = int(os.getenv('DEBUG',0)) # set DEBUG environment variable to 1 to enable testing
# Setting up logging, default to INFO level 
logger = logging.getLogger() 
if (DEBUG): 
  logger.setLevel(logging.DEBUG)
  logger.debug("DEBUGGING ON") # send debug status
else:
  logger.setLevel(logging.INFO)
  # read in the wait time, default to DEF_WAIT_TIME
WAIT_TIME= int(os.getenv('WAIT_TIME',defWaitTime))
logger.debug("WAIT_TIME= %i" % WAIT_TIME) 
try:
  REGION_FILTER= str(os.getenv('REGION_FILTER', '[]'))
  logger.debug("REGION_FILTER= %s" % REGION_FILTER)
  REGION_FILTER=json.loads(REGION_FILTER)
except Exception as e:
  logger.error(e)
  eMessage= 'ERROR: Invalid REGION_FILTER specified!'
  logger.error(eMessage)
  raise Exception(eMessage)

# Extracts the name field from the ARN
# Input: Issues ARN
# Output: The name of the ARN trimmed to the maxEventID size
def trimArnToName(arn):
  # Health ARN Pattern: arn:aws:health:[^:]*:[^:]*:event/[\w-]+
  # set the issues name from the ARN to match the SFN's name
  eventIDPos= arn.rfind('/')
  eventStr= arn[eventIDPos:]
  # Trim the SFN Name to the maxEventID size
  eventID= eventStr[1:maxEventID]
  logger.debug("SFN name: %s" % (eventID))
  return eventID

# Main lambda function 
def lambda_handler(event, context): 

  # Load the AWS Health API
  health= boto3.client('health', region_name='us-east-1')
  # Build the filter
  event_filter = {"eventStatusCodes": [eventStatusCodes],"eventTypeCategories": [ eventTypeCategories ]}
  if len(REGION_FILTER)>0:
    event_filter['regions']=REGION_FILTER
  # Poll the open events
  events_dict= health.describe_events(
    filter=event_filter,
    maxResults=maxEvents
    )
  open_issues=events_dict['events']
  if (len(open_issues)==0):
    print("No open issues detected.") # nothing to see here...
    logger.info("No open issues detected.")
  else:
    logger.info("Number of open issues: %s" % (len(open_issues)))
    # load the step state machine API
    stepClient = boto3.client('stepfunctions')
    # for every open issue, lets execute a state machine
    for issue in open_issues:
      # Skip events that are not PUBLIC events that appear on the SHD (i.e. Account specific events)
      if issue['eventScopeCode'] != 'PUBLIC':
        logger.info("Non-public issue not on SHD, skipping: %s" % (issue['arn']))
        continue
      logger.info("Starting Step Function for issue: %s" % (issue['arn']))
      # Execute state machine pass in the issues ARN and the WAIT_TIME
      input_str="{\"eventArn\":\"%s\",\"maxCount\": %i}" % (issue['arn'],WAIT_TIME)
      logger.debug("SFN Arn: %s" % (stateMachineArn))
      logger.debug("SFN input: %s" % (input_str))
      # extract the eventID field within the name size limit
      eventID=trimArnToName(issue['arn'])
      # ok lets fire up the state machine
      try:
        response = stepClient.start_execution(
          stateMachineArn=stateMachineArn,
          name=eventID,
          input= input_str
          )
      except ClientError as e:
        if e.response['Error']['Code'] == 'ExecutionAlreadyExists':
          # Duplicate Event ID's will be ignored since they were handled.
          logger.info("Event already executed named: %s" % (eventID))
          if (DEBUG): 
            logger.debug("DEBUG: Duplicate event detected for: %s" % (eventID))
            break # Only run one issue in debug, even already exists
          continue
        else:
          # we were unable to start the SFN, which is a severe error
          print(e)
          message= 'ERROR: Unable to start state machine'
          print(message)
          raise Exception(message)
      if (DEBUG): break # Only run one issue in debug

