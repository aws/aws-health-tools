import json
import datetime
import urllib.request
import dateutil.parser
import math
import os 

WELCOME_MESSAGE = ("Welcome to Production Environment!  You can ask me about your production environment status!")
EXIT_SKILL_MESSAGE = "Thank you! Enjoy the rest of your summit!"
HELP_MESSAGE = ("I know stuff about your production environment! Ask away!")
STATE_START = "Start"
STATE = STATE_START

date_handler = lambda obj: obj.strftime('%Y-%m-%d %H:%M:%S')

def getLatestPhdEvent():
    es = "http://"+os.environ['ESELB']
    index = 'phd-full-events'
    query = {
        "size": 1,
        "sort": [
            {
                "PhdEventTime": {
                    "order": "desc"
                }
            }
        ]
    }
    
    # Elasticsearch Request/Response
    payload = json.dumps(query).encode('utf-8')         # Encode query for HTTP request
    request = urllib.request.Request(es + '/' + index + '/_search', payload, {'Content-Type': 'application/json'}, method='GET')    # Build HTTP request
    response = urllib.request.urlopen(request).read()   # Send Request
    response = json.loads(response.decode('utf-8'))     # Decode response and convert to JSON
    return response['hits']['hits'][0]['_source']       # Return query payload    

# --------------- entry point -----------------

def lambda_handler(event, context):
    print(event)
    
    """ App entry point  """
    if event['request']['type'] == "LaunchRequest":
        return on_launch()
    elif event['request']['type'] == "IntentRequest": 
        return on_intent(event['request'], event['session'])
    elif event['request']['type'] == "SessionEndedRequest":
        return on_session_ended(event['request'])


# --------------- response handlers -----------------

def on_intent(request, session):
    """ Called on receipt of an Intent  """

    intent = request['intent']
    intent_name = request['intent']['name']

    #print("on_intent " +intent_name)
    get_state(session)

    if 'dialogState' in request:
        #delegate to Alexa until dialog sequence is complete
        if request['dialogState'] == "STARTED" or request['dialogState'] == "IN_PROGRESS":
            print (request['dialogState'])
            return dialog_response("", False)

    if intent_name == "GetNewEventIntent":
        return get_event()
    elif intent_name == "AMAZON.HelpIntent":
        return do_help()
    elif intent_name == "AMAZON.StopIntent":
        return do_stop()
    elif intent_name == "AMAZON.CancelIntent":
        return do_stop()
    else:
        print("invalid intent reply with help")
        return do_help()


def do_stop():
    attributes = {"state":globals()['STATE']}
    return response(attributes, response_plain_text(EXIT_SKILL_MESSAGE, True))

def do_help():
    global STATE
    STATE = STATE_START
    attributes = {"state":globals()['STATE']}
    return response(attributes, response_plain_text(HELP_MESSAGE, True))

def on_launch():
    return get_welcome_message()

def on_session_ended(request):
    if request['reason']:
        end_reason = request['reason']
        print("on_session_ended reason: " + end_reason)
        
def get_state(session):
    """ get and set the current state  """

    global STATE

    if 'attributes' in session:
        if 'state' in session['attributes']:
            STATE = session['attributes']['state']
        else:
            STATE = STATE_START
    else:
        STATE = HELP_MESSAGE


# --------------- response string formatters -----------------
def get_welcome_message():
    attributes = {"state":globals()['STATE']}
    return response(attributes, response_plain_text(WELCOME_MESSAGE, False))

def getDateTimeFromISO8601String(s):
    d = dateutil.parser.parse(s)
    return d

def get_event():
    attributes = {"state":globals()['STATE']}

    payload = getLatestPhdEvent()
    print(payload)
    
    ## Get Time ##
    x = payload['PhdEventTime']
    timeiso = getDateTimeFromISO8601String(x)
    
    ## Convert to AU/Melbourne ##
    y = dateutil.parser.parse(x)
    meltimeiso = y + datetime.timedelta(hours=int(os.environ['timezonedelta']))
    eventtimestr = json.dumps(meltimeiso, default = date_handler)
   
    eventtime = datetime.datetime.strptime(eventtimestr.replace("\"", ""), "%Y-%m-%d  %H:%M:%S")
    systemname =  payload['ResourceStack']['StackName']
    eventid =  payload['PhdEventId']
    recoverytime = payload['RestoredResources']['RestoredVolumes'][0]['CreateTime']
    recoverystatus = payload['NOTIFMESSAGE']['Message']
    
    # Compose Event time
    eventdate = str(eventtime.year) + "-" + str(eventtime.month) + "-" + str(eventtime.day)
    eventtimestr = str(eventtime.hour) + ":" + str(eventtime.minute)
    dtime = datetime.datetime.strptime(eventtimestr, "%H:%M")
    eventtime = dtime.strftime("%I:%M %p")
    
    # Find Recovery Time
    reventlist = payload['ResourceStack']['StackEvents']
    for revent in reventlist:
        if revent['ResourceType'] == "AWS::CloudFormation::Stack":
            if revent['ResourceStatus'] == "UPDATE_COMPLETE":
                rendtime = revent['Timestamp']
    
    endtime = getDateTimeFromISO8601String(rendtime)
    diff = endtime - timeiso
    diffseconds = diff.total_seconds()
    diffhours = diffseconds // 3600
    diffminutes = (diffseconds % 3600) // 60
    diffseconds = diffseconds % 60
    recoveryhours =  str(math.ceil(diffhours))
    recoveryminutes =  str(math.ceil(diffminutes))
    recoveryseconds =  str(math.ceil(diffseconds))

    LATEST_EVENT = ( "On "+ eventdate + " at " + eventtime + "! System " + systemname + " was down! " + "System is now recovered ! " + " Total Recovery time is " + recoveryhours + " hours " + recoveryminutes + " minutes and " + recoveryseconds + " seconds " +  "! Please check kibana for recovery details!")
    return response(attributes, response_plain_text(LATEST_EVENT, True))

def response(attributes, speech_response):
    """ create a simple json response """

    return {
        'version': '1.0',
        'sessionAttributes': attributes,
        'response': speech_response
    }
    
def response_plain_text(output, endsession):
    """ create a simple json plain text response  """

    return {
        'outputSpeech': {
            'type': 'PlainText',
            'text': output
        },
        'shouldEndSession': endsession
    }
