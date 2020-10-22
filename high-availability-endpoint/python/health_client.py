# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
from region_lookup import active_region
import boto3

class ActiveRegionHasChangedError(Exception):
    """Rasied when the active region has changed"""
    pass

class HealthClient:
    __active_region = None
    __client = None

    @staticmethod
    def client():
        if not HealthClient.__active_region:
            HealthClient.__active_region = active_region()
        else:
            current_active_region = active_region()
            if current_active_region != HealthClient.__active_region:
                old_active_region = HealthClient.__active_region
                HealthClient.__active_region = current_active_region

                if HealthClient.__client:
                    HealthClient.__client = None

                raise ActiveRegionHasChangedError('Active region has changed from [' + old_active_region + '] to [' + current_active_region + ']')

        if not HealthClient.__client:
            HealthClient.__client = boto3.client('health', region_name=HealthClient.__active_region)

        return HealthClient.__client