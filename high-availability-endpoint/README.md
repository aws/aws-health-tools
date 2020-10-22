high-availability-endpoint
--------------------------

This repository contains sample code for using the AWS Health API's high availability endpoint to determine which region to connect to in order to get the latest Health information.

## Background

AWS Health is a RESTful web service that uses HTTPS as a transport and JSON as a message serialization format. Your application code can make requests directly to the AWS Health API. When using the REST API directly, you must write the necessary code to sign and authenticate your requests. For more information, see the [AWS Health API Reference](https://docs.aws.amazon.com/health/latest/APIReference/).

**NOTE**: You must have a Business or Enterprise support plan from [AWS Support](http://aws.amazon.com/premiumsupport/) to use the AWS Health API. If you call the AWS Health API from an AWS account that doesn't have a Business or Enterprise support plan, you receive a ```SubscriptionRequiredException``` error. 

You can simplify application development by using the AWS SDKs that wrap the AWS Health REST API calls. You provide your credentials, and then these libraries take care of authentication and request signing. 
AWS Health also provides a Personal Health Dashboard in the AWS Management Console that you can use to view and search for events and affected entities.

## Endpoints

The AWS Health API follows a [multi-Region application architecture](http://aws.amazon.com/solutions/implementations/multi-region-application-architecture/) and has two regional endpoints in an active-passive configuration. To support active-passive DNS failover, AWS Health provides a single, global endpoint. You can determine the active endpoint and corresponding signing Region by performing a DNS lookup on the global endpoint. This lets you know which endpoint to use in your code so that you can get the latest information from AWS Health. 

When you make a request to the global endpoint, you must specify your AWS access credentials to the regional endpoint that you target and configure the signing for your Region. Otherwise, your authentication might fail. For more information, see [Signing AWS Health API requests](https://docs.aws.amazon.com/health/latest/ug/health-api.html#signing). 

The following table represents the default configuration.

| Description | Signing Region | Endpoint | Protocol |
| ----------- | -------------- | -------- | -------- |
| Active | 	us-east-1 |	health.us.east-1.amazonaws.com | HTTPS |
| Passive | us-east-2 | health.us-east-2.amazonaws.com | HTTPS |
| Global | us-east-1 This is the signing Region of the current active endpoint. | global.health.amazonaws.com | HTTPS |

For China regions see [this configuration](https://docs.amazonaws.cn/en_us/health/latest/ug/health-api.html#endpoints).

The method to determine if an endpoint is the _active endpoint_ is to do a DNS lookup on the _global endpoint CNAME_ and extract the region from the resolved name.

For example, the following command completes a DNS lookup on the global.health.amazonaws.com endpoint. The command then returns the us-east-1 Region endpoint:

```
$ dig global.health.amazonaws.com | grep CNAME
global.health.amazonaws.com. 10	IN	CNAME	health.us-east-1.amazonaws.com
```

The active endpoint region is us-east-1.

Both the active and passive endpoints will return AWS Health data. However, the latest AWS Health data will only be available from the active endpoint. Data from the passive endpoint will be eventually consistent. We recommend that you **restart any workflows when the active endpoint changes**.

## Demos

For examples on using the high availability endpoint with the AWS SDKs see:

* [Java demo](java/)
* [Python demo](python/)

## License

AWS Health Tools are licensed under the Apache 2.0 License