// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
package aws.health.high.availability.endpoint.demo;

import software.amazon.awssdk.services.health.HealthClient;
import software.amazon.awssdk.services.health.HealthClientBuilder;
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * This is an example of using the Health API endpoint DNS lookup strategy
 * with the AWS Java SDK V2 Health client.
 */
public final class HighAvailabilityV2HealthClient {
    private static String activeRegion;

    private static HealthClient healthClient;

    private HighAvailabilityV2HealthClient() {}

    public static synchronized HealthClient getHealthClient() throws RegionLookupException, ActiveRegionHasChangedException {
        String currentActiveRegion = RegionLookup.getCurrentActiveRegion();
        if (activeRegion == null) {
            // This is the first time we've done the DNS lookup
            activeRegion = currentActiveRegion;
        } else {
            // If the active region has changed since the last time we did the
            // DNS lookup we throw an exception to let the calling code know
            // abount the change
            if (!currentActiveRegion.equals(activeRegion)) {
                String oldActiveRegion = activeRegion;
                activeRegion = currentActiveRegion;

                if (healthClient != null) {
                    // Close the existing client so that the next call to this
                    // method will create a new client using the new active
                    // region
                    healthClient.close();
                    healthClient = null;
                }

                throw new ActiveRegionHasChangedException("Active region has changed from [" + oldActiveRegion + "] to [" + currentActiveRegion + "]");
            }
        }

        if (healthClient == null) {
            // Create the Health client using the region extraced from the global
            // endpoint CNAME
            healthClient = HealthClient.builder()
                .region(Region.of(activeRegion))
                .credentialsProvider(
                    // See https://docs.aws.amazon.com/sdk-for-java/v2/developer-guide/setup-credentials.html
                    DefaultCredentialsProvider.builder().build()
                )
                .build();
        }

        return healthClient;
    } 

}