# Health-Event-Iterator-LambdaFn

# Increments a count variable by 1 until it reaches a maximum value (maxCount)
# then sets the value to 0. Simple iterator.
# Input: maxCount - int, maximum count, defaults to 15
#        count - int, current count, defaults to 0
# Output: current count
#

import json # essential to read json
import os # required to read in the os variables
import boto3 # AWS CLI, required to poll AWS Health

# Static vars
COUNT=0 # default counter starting value
MAXCOUNT=15 # default maximum count number before reset

# Main lambda function 
def lambda_handler(event, context): 
  # read in the count, if missing default to COUNT
  try:
    count= event['count']
  except Exception as e:
    eMessage="WARN: Missing count defaulting to %i" % COUNT
    print(eMessage)
    count=COUNT

  # read in the maxCount, if missing default to 15 
  try:
    maxCount= event['maxCount']
  except Exception as e:
    eMessage="WARN: Missing maxCount defaulting to %i" % MAXCOUNT
    print(eMessage)
    maxCount=MAXCOUNT

  count=count+1 # increment the counter
  if (count==maxCount): count=0 # set the count back to 0 when maxCount is reached
  return count # return the count as the output
