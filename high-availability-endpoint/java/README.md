## Using the high availability endpoint java demo

To build and run this demo:

1. Download / clone the repo [AWS Health high availability endpoint demo](https://github.com/aws/aws-health-tools/high-availability-endpoint) from GitHub

2. [Install Gradle](https://docs.gradle.org/current/userguide/installation.html)

3. Navigate to the java demo project directory in a command line window:

```
cd java
```

4. Compile the demo by entering the following command:

```
gradle build
```

5. Set the AWS credentials:

[Configure AWS credentials](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html). e.g. using profiles or environment variables

```
export AWS_ACCESS_KEY_ID="AKIAIOSFODNN7EXAMPLE"
export AWS_SECRET_ACCESS_KEY="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
export AWS_SESSION_TOKEN="your-aws-token"
```

6. Enter the following command to run the demo:

```
gradle run
```

The output will look something like:

```
> Task :run
[main] INFO aws.health.high.availability.endpoint.demo.HighAvailabilityV2Workflow - EventDetails(Event=Event(Arn=arn:aws:health:global::event/CONFIG/AWS_CONFIG_OPERATIONAL_NOTIFICATION/AWS_CONFIG_OPERATIONAL_NOTIFICATION_88a43e8a-e419-4ca7-9baa-56bcde4dba3, Service=CONFIG, EventTypeCode=AWS_CONFIG_OPERATIONAL_NOTIFICATION, EventTypeCategory=accountNotification, Region=global, StartTime=2020-09-11T02:55:49.899Z, LastUpdatedTime=2020-09-11T03:46:31.764Z, StatusCode=open, EventScopeCode=ACCOUNT_SPECIFIC), EventDescription=EventDescription(LatestDescription=As part of our ongoing efforts to optimize costs associated with recording changes related to certain ephemeral workloads, AWS Config is scheduled to release an update to relationships modeled within ConfigurationItems (CI) for 7 EC2 resource types on August 1, 2021. Examples of ephemeral workloads include changes to Amazon Elastic Compute Cloud (Amazon EC2) Spot Instances, Amazon Elastic MapReduce jobs, and Amazon EC2 Autoscaling. This update will optimize CI models for EC2 Instance, SecurityGroup, Network Interface, Subnet, VPC, VPN Gateway, and Customer Gateway resource types to record direct relationships and deprecate indirect relationships.

A direct relationship is defined as a one-way relationship (A->B) between a resource (A) and another resource (B), and is typically derived from the Describe API response of resource (A). An indirect relationship, on the other hand, is a relationship that AWS Config infers (B->A), in order to create a bidirectional relationship. For example, EC2 instance -> Security Group is a direct relationship, since security groups are returned as part of the describe API response for an EC2 instance. But Security Group -> EC2 instance is an indirect relationship, since EC2 instances are not returned when describing an EC2 Security group.

Until now, AWS Config has recorded both direct and indirect relationships. With the launch of Advanced queries in March 2019, indirect relationships can easily be answered by running Structured Query Language (SQL) queries such as:

SELECT
 resourceId,
 resourceType
WHERE
 resourceType ='AWS::EC2::Instance'
AND
 relationships.resourceId = 'sg-234213'

By deprecating indirect relationships, we can optimize the information contained within a Configuration Item while reducing AWS Config costs related to relationship changes. This is especially useful in case of ephemeral workloads where there is a high volume of configuration changes for EC2 resource types.

Which resource relationships are being removed?

Resource Type: Related Resource Type
1 AWS::EC2::CustomerGateway: AWS::VPN::Connection
2 AWS::EC2::Instance: AWS::EC2::EIP, AWS::EC2::RouteTable
3 AWS::EC2::NetworkInterface: AWS::EC2::EIP, AWS::EC2::RouteTable
4 AWS::EC2::SecurityGroup: AWS::EC2::Instance, AWS::EC2::NetworkInterface
5 AWS::EC2::Subnet: AWS::EC2::Instance, AWS::EC2::NetworkACL, AWS::EC2::NetworkInterface, AWS::EC2::RouteTable
6 AWS::EC2::VPC: AWS::EC2::Instance, AWS::EC2::InternetGateway, AWS::EC2::NetworkACL, AWS::EC2::NetworkInterface, AWS::EC2::RouteTable, AWS::EC2::Subnet, AWS::EC2::VPNGateway, AWS::EC2::SecurityGroup
7 AWS::EC2::VPNGateway: AWS::EC2::RouteTable, AWS::EC2::VPNConnection

Alternate mechanism to retrieve this relationship information:
The SelectResourceConfig API accepts a SQL SELECT command, performs the corresponding search, and returns resource configurations matching the properties. You can use this API to retrieve the same relationship information. For example, to retrieve the list of all EC2 Instances related to a particular VPC vpc-1234abc, you can use the following query:

SELECT
 resourceId,
 resourceType
WHERE
 resourceType ='AWS::EC2::Instance'
AND
 relationships.resourceId = 'vpc-1234abc'

If you have any questions regarding this deprecation plan, please contact AWS Support [1]. Additional sample queries to retrieve the relationship information for the resources listed above is provided in [2].

[1] https://aws.amazon.com/support
[2] https://docs.aws.amazon.com/config/latest/developerguide/examplerelationshipqueries.html), EventMetadata={})
[main] INFO aws.health.high.availability.endpoint.demo.HighAvailabilityV2Workflow - EventDetails(Event=Event(Arn=arn:aws:health:us-west-2::event/STORAGEGATEWAY/AWS_STORAGEGATEWAY_OPERATIONAL_ISSUE/AWS_STORAGEGATEWAY_OPERATIONAL_ISSUE_WQPFF_7809546408, Service=STORAGEGATEWAY, EventTypeCode=AWS_STORAGEGATEWAY_OPERATIONAL_ISSUE, EventTypeCategory=issue, Region=us-west-2, StartTime=2020-09-13T19:46:48.335Z, LastUpdatedTime=2020-09-14T01:30:16.216Z, StatusCode=open, EventScopeCode=PUBLIC), EventDescription=EventDescription(LatestDescription=Storage Gateway VMs Offline

[12:46 PM PDT] Beginning at 7:39 AM PDT, we are experiencing an issue where Storage Gateway VMs appear to be offline and are not able to perform out of cache reads or upload to our service. The gateways will continue to accept writes but will not be able to proceed to upload them to our service until this issue is resolved. We have identified the root cause and are working towards resolution.

[02:59 PM PDT] We continue to work towards resolution on the issue impacting Storage Gateway. The Gateways will continue to accept writes but will not be able to proceed to upload them to our service until this issue is resolved. Based upon the information available at this time, full resolution is estimated to take 2 hours. We are working through the recovery process now and will continue to keep you updated if this timeline changes.

[05:29 PM PDT] We are beginning to see recovery in some AWS Regions for the issue impacting Storage Gateway. We continue to work towards resolution for all impacted Regions. We will update the message for each AWS Region as recovery occurs.

[06:30 PM PDT] Beginning at 7:39 AM PDT we experienced an issue impacting Storage Gateway in the US-WEST-2 Region. During the event Gateways were unable to perform out of cache reads and appeared offline in the SGW console. Gateways continued to accept writes but were unable to upload them to the AWS service. The issue has been resolved and the service is operating normally. ), EventMetadata={})
```

## References

* AWS Java SDK V2 health client [javadoc](https://sdk.amazonaws.com/java/api/latest/software/amazon/awssdk/services/health/HealthClient.html) and [source code](https://repo1.maven.org/maven2/software/amazon/awssdk/health/2.14.2/)
* The library used in this demo for DNS lookups - [dnsjava](https://github.com/dnsjava/dnsjava)

## License

AWS Health Tools are licensed under the Apache 2.0 License