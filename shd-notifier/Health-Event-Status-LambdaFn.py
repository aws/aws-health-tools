# Health-Event-Status-LambdaFn

# Given an events ARN return if it is open or closed
# Input: Event ARN
# Output: Event Status (open, closed, upcoming)

import json # essential to read json
import os # required to read in the os variables
import boto3 # AWS CLI, required to poll AWS Health

# Static vars
maxEvents=10 # Max is 100, but we expect just 1

# Main lambda function 
def lambda_handler(event, context): 
  # read in the eventArn input
  eventArn= event['eventArn']
  # Load the AWS Health API
  health= boto3.client('health', region_name='us-east-1')
  # Pull the event matching the Arn passed in, catch any errors
  try:
    events_dict= health.describe_events(
      filter={'eventArns': [eventArn]},
      maxResults=maxEvents
      )
  except Exception as e:
    print(e)
    message= 'ERROR: getting events status'
    print(message)
    raise Exception(message)
  # pull out just the events
  our_events=events_dict['events']
  # now lets validate we received what we expected, 1 result
  if (len(our_events)==0):
      # Error state, no match
      message= 'ERROR: ARN not detected'
      print(message)  
      raise Exception(message) 
  elif (len(our_events)>1):
      # Error state, too many matches
      message="ERROR: Multiple ARNs detected"
      print(message)
      raise Exception(message)
  else:
    # return the status code for our one event
    statusCode= our_events[0]['statusCode']
    return statusCode
