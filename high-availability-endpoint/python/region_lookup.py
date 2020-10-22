# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import dns.resolver

class RegionLookupError(Exception):
    """Rasied when there was a problem when looking up the active region"""
    pass

def active_region():
    qname = 'global.health.amazonaws.com'
    try:
        answers = dns.resolver.resolve(qname, 'CNAME')
    except Exception as e:
        raise RegionLookupError('Failed to resolve {}'.format(qname), e)
    if len(answers) != 1:
        raise RegionLookupError('Failed to get a single answer when resolving {}'.format(qname))
    name = str(answers[0].target) # e.g. health.us-east-1.amazonaws.com.
    region_name = name.split('.')[1] # Region name is the 1st in split('.') -> ['health', 'us-east-1', 'amazonaws', 'com', '']
    return region_name