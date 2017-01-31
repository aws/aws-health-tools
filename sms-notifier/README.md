## AWS Health SMS Notifier

### Description

This tool can be used to send custom text or SMS notifications via Amazon SNS when an AWS Health event happens by using AWS Lambda and Amazon CloudWatch Events. 

### Setup and Usage

1. Create an IAM role for the Lambda function to use. Attach the [IAM policy](IAMPolicy) to the role in the IAM console.
Documentation on how to create an IAM policy is available here: http://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_create.html
Documentation on how to create an IAM role for Lambda is available here: http://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_create_for-service.html#roles-creatingrole-service-console

2. Create a Lambda JavaScript function by using the [sample](LambdaFunction.js) provided and choose the IAM role created in step 1. Update the phone number in the configuration section. More information about Lambda is available here: http://docs.aws.amazon.com/lambda/latest/dg/getting-started.html

3. Create a CloudWatch Events rule to trigger the Lambda function created in step 2 for AWS Health events.
Documentation on how to create an AWS Health CloudWatch Events rule is available here: http://docs.aws.amazon.com/health/latest/ug/cloudwatch-events-health.html

More information about AWS Health is available here: http://docs.aws.amazon.com/health/latest/ug/what-is-aws-health.html

Note that this is a just an example of how to set up automation with AWS Health, Amazon CloudWatch Events, and AWS Lambda. We recommend testing this example and tailoring it to your environment before using it in your production environment.

### License
AWS Health Tools are licensed under the Apache 2.0 License.


