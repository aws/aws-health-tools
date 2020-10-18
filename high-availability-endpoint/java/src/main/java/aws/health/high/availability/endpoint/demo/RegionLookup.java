// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
package aws.health.high.availability.endpoint.demo;

import org.xbill.DNS.Lookup;
import org.xbill.DNS.CNAMERecord;
import org.xbill.DNS.TextParseException;
import org.xbill.DNS.Type;
import org.xbill.DNS.Record;

public final class RegionLookup {
    public static final String GLOBAL_HEALTH_ENDPOINT = "global.health.amazonaws.com"; 

    public static String getCurrentActiveRegion() throws RegionLookupException {
        // Init lookup object
        Lookup dnsLookup = null;
        try {
            dnsLookup = new Lookup(GLOBAL_HEALTH_ENDPOINT, Type.CNAME);
        } catch (TextParseException e) {
            throw new RegionLookupException("Failed to parse DNS name [" + GLOBAL_HEALTH_ENDPOINT + "]", e);
        } 
        dnsLookup.setCache(null); // Never use caching, always do a full a DNS lookup

        // Do the DNS lookup
        Record[] records = dnsLookup.run();
        if (records == null || records.length == 0) {
            throw new RegionLookupException("Failed to resolve the DNS name [" + GLOBAL_HEALTH_ENDPOINT + "]");
        }
        CNAMERecord cnameRecord = (CNAMERecord)records[0];
        String regionalDNSName = cnameRecord.getTarget().toString(true);

        // The CNAME will look something like: "health.us-east-1.amazonaws.com"
        // Extract the region name (e.g. us-east-1) to use for SigV4 signing
        String[] cnameParts = regionalDNSName.split("\\.");
        String regionName = cnameParts[1].toLowerCase(); // The region is always the second item in the array

        return regionName;
    }
}
