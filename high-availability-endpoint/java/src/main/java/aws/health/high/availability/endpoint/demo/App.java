// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
package aws.health.high.availability.endpoint.demo;

/**
 * Sample workflow for using the AWS Health API high availability endpoint
 */
public class App {
    public static void main(String[] args) throws RegionLookupException {

        // Example using the HealthClient from the AWS Java SDK V2
        HighAvailabilityV2Workflow v2Workflow = new HighAvailabilityV2Workflow();
        v2Workflow.doWorkflow();
    }
}
