## AWS Health AWS_EC2_INSTANCE_STORE_DRIVE_PERFORMANCE_DEGRADED

### Description
EC2 has detected a performance degradation of one or more physical storage drives that backs the instance store volumes of your Amazon EC2 instance. Because of this degradation, some instance store volumes could be unresponsive or exhibit poor performance.

### Setup and Usage
You can automatically stop or terminate EC2 instances that have degraded instance-store performance using Amazon Cloudwatch events and AWS Lambda using the following instructions:

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

