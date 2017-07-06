## AWS Health AWS_EC2_INSTANCE_STORE_DRIVE_PERFORMANCE_DEGRADED

### Description
EC2 has detected a performance degradation of one or more physical storage drives that backs the instance store volumes of your Amazon EC2 instance. Because of this degradation, some instance store volumes could be unresponsive or exhibit poor performance.

### Setup and Usage
You can automatically stop or terminate EC2 instances that have degraded instance-store performance using Amazon Cloudwatch events and AWS Lambda.

#### CloudFormation
Choose **Launch Stack** to launch the CloudFormation template in the US East (N. Virginia) Region in your account:

[![Launch AWS Health Automated Action](../../images/cloudformation-launch-stack.png)](https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/new?stackName=EC2InstancStopuponInstanceStoreDegradation&templateURL=https://s3.amazonaws.com/aws-health-tools-assets/cloudformation-templates/aa-instance-store-degraded.json)

The CloudFormation template requires the following parameters:

*Action to take* - Whether to Stop or Terminate affected instances

*Tag Key* - Instances must have a matching tag key and value, this is the key to match

*Tag Value* - the tag value to match

*Dry Run* - Set to true for testing. setting this to true will run the requested EC2 API in DryRun mode, not actually stopping/terminating instances

#### Manual setup

1. Create an IAM role for the Lambda function to use. Attach the [IAM policy](IAMPolicy) to the role in the IAM console.
Documentation on how to create an IAM policy is available here: http://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_create.html
Documentation on how to create an IAM role for Lambda is available here: http://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_create_for-service.html#roles-creatingrole-service-console

2. Create a Lambda JavaScript function by using the [sample](LambdaFunction.js) provided and choose the IAM role created in step 1. The sample Lambda function will stop EC2 instances when AWS Health AWS_EC2_INSTANCE_STORE_DRIVE_PERFORMANCE_DEGRADED events are generated. This is useful for situations where there is data redundancy and fault tolerance (for example, when using Auto Scaling).  Be sure to set the appropriate tags and region in the configuration section of the Lambda function.
More information about Lambda is available here: http://docs.aws.amazon.com/lambda/latest/dg/getting-started.html

3. Create a CloudWatch Events rule to trigger the Lambda function created in step 2 matching the AWS_EC2_INSTANCE_STORE_DRIVE_PERFORMANCE_DEGRADED event.
Documentation on how to create an AWS Health CloudWatch Events rule is available here: http://docs.aws.amazon.com/health/latest/ug/cloudwatch-events-health.html

More information about AWS Health is available here: http://docs.aws.amazon.com/health/latest/ug/what-is-aws-health.html

Note that this is a just an example of how to set up automation with AWS Health, Amazon CloudWatch Events, and AWS Lambda. We recommend testing the example and tailoring it to your environment before using it in your production environment.

### License
AWS Health Tools are licensed under the Apache 2.0 License.
