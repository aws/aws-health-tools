// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
package aws.health.high.availability.endpoint.demo;

import software.amazon.awssdk.services.health.HealthClient;
import software.amazon.awssdk.services.health.model.DateTimeRange;
import software.amazon.awssdk.services.health.model.DescribeEventDetailsRequest;
import software.amazon.awssdk.services.health.model.DescribeEventDetailsResponse;
import software.amazon.awssdk.services.health.model.DescribeEventsRequest;
import software.amazon.awssdk.services.health.model.DescribeEventsResponse;
import software.amazon.awssdk.services.health.model.Event;
import software.amazon.awssdk.services.health.model.EventFilter;
import software.amazon.awssdk.services.health.model.EventStatusCode;
import software.amazon.awssdk.services.health.paginators.DescribeEventsIterable;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Duration;
import java.time.Instant;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * Example workflow when using the AWS Health API high availability endpoint
 * and the AWS Java V2 SDK.
 */
public class HighAvailabilityV2Workflow {
    private static final Logger log = LoggerFactory.getLogger(HighAvailabilityV2Workflow.class);

    /**
     * Helper method to provide a shorter way of referring to the singleton
     * client method
     */
    private HealthClient getV2Client() throws RegionLookupException, ActiveRegionHasChangedException {
        return HighAvailabilityV2HealthClient.getHealthClient();
    }

    /**
     * Log the details of an event
     */
    private void eventDetails(Event event) throws RegionLookupException, ActiveRegionHasChangedException {
        // NOTE: It is more efficient to call describeEventDetails with a batch
        // of eventArns, but for simplicitly of this demo we call it with a
        // single eventArn
        DescribeEventDetailsRequest detailsRequest = DescribeEventDetailsRequest.builder()
            .eventArns(Collections.singleton(event.arn()))
            .build();

        DescribeEventDetailsResponse detailsResponse = getV2Client().describeEventDetails(detailsRequest);
        detailsResponse.successfulSet().stream().forEach(detail -> log.info(detail.toString()));
    }

    private void describeEvents() throws RegionLookupException, ActiveRegionHasChangedException {
        // Describe events using the same default filters as the Personal Health Dashboard (PHD). i.e
        //
        // Return all open or upcoming events which started in the last 7 days, ordered by event lastUpdatedTime

        List<EventStatusCode> eventStatusCodes = new ArrayList<>();
        eventStatusCodes.add(EventStatusCode.OPEN);
        eventStatusCodes.add(EventStatusCode.UPCOMING);

        DateTimeRange sevenDaysAgo = DateTimeRange.builder().from(Instant.now().minus(Duration.ofDays(7))).build();

        DescribeEventsRequest describeEventsRequest = DescribeEventsRequest.builder()
            .filter(EventFilter.builder().eventStatusCodes(eventStatusCodes).startTimes(Collections.singleton(sevenDaysAgo)).build())
            .build();

        int numberOfMatchingEvents = 0;
        DescribeEventsIterable describeEventsResponses = getV2Client().describeEventsPaginator(describeEventsRequest);
        for (DescribeEventsResponse eventsResponse : describeEventsResponses) {
            for (Event event: eventsResponse.events()) {
                eventDetails(event);
                numberOfMatchingEvents++;
            }
        }

        if (numberOfMatchingEvents == 0) {
            log.info("There are no AWS Health events that match the given filters");
        }
    }

    public void doWorkflow() throws RegionLookupException {
        // An example workflow using the AWS Health API's high availability
        // endpoint and the AWS Java SDK V2

        // If the active endpoint changes we recommend you restart any
        // workflows.
        //
        // In this sample code we throw an exception if the active
        // endpoint changes in the middle of a workflow and restart the
        // workflow using the new active endpoint.
        boolean restartWorkflow = true;

        while (restartWorkflow) {
            try {
                // Describe events for the account
                describeEvents();
                restartWorkflow = false;
            } catch (ActiveRegionHasChangedException ex) {
                log.info("The AWS Health API active region has changed. Restarting the workflow using the new active region!" + ex);
            }
        }
    }
}