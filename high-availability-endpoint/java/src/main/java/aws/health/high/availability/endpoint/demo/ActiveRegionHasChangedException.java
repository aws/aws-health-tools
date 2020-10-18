// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
package aws.health.high.availability.endpoint.demo;

public final class ActiveRegionHasChangedException extends Exception {
    public ActiveRegionHasChangedException(String message) {
        super(message);
    }

    public ActiveRegionHasChangedException(String message, Throwable cause) {
        super(message, cause);
    }
}