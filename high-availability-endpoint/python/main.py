#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from  health_client import HealthClient, ActiveRegionHasChangedError
import datetime
import logging
logging.basicConfig(level=logging.INFO)

def event_details(event):
    # NOTE: It is more efficient to call describe_event_details with a batch
    # of eventArns, but for simplicitly of this demo we call it with a
    # single eventArn
    event_details_response = HealthClient.client().describe_event_details(eventArns=[event['arn']])
    for event_details in event_details_response['successfulSet']:
        logging.info('Details: %s, description: %s', event_details['event'], event_details['eventDescription'])

def describe_events():
    events_paginator = HealthClient.client().get_paginator('describe_events')

    # Describe events using the same default filters as the Personal Health
    # Dashboard (PHD). i.e
    #
    # Return all open or upcoming events which started in the last 7 days,
    # ordered by event lastUpdatedTime

    events_pages = events_paginator.paginate(filter={
        'startTimes': [
            {
                'from': datetime.datetime.now() - datetime.timedelta(days=7)
            }
        ],
        'eventStatusCodes': ['open', 'upcoming']
    })

    number_of_matching_events = 0
    for events_page in events_pages:
        for event in events_page['events']:
            number_of_matching_events += 1
            event_details(event)

    if number_of_matching_events == 0:
        logging.info('There are no AWS Health events that match the given filters')


# If the active endpoint changes we recommend you restart any workflows.
#
# In this sample code we throw an exception if the active endpoint changes in
# the middle of a workflow and restart the workflow using the new active
# endpoint.
restart_workflow = True

while restart_workflow:
    try:
        describe_events()
        restart_workflow = False
    except ActiveRegionHasChangedError as are:
        logging.info("The AWS Health API active region has changed. Restarting the workflow using the new active region!, %s", are)