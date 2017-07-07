## AWS Health SMS Notifier

### Description

This tool can be used to send custom text or SMS notifications via Amazon SNS when an AWS Health event happens by using AWS Lambda and Amazon CloudWatch Events.

### Setup and Usage

Choose **Launch Stack** to launch the template in the US East (N. Virginia) Region in your account:

[![Launch AWS Health SMS Notifier](../images/cloudformation-launch-stack.png)](https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/new?stackName=SmsNotifier&templateURL=https://s3.amazonaws.com/aws-health-tools-assets/cloudformation-templates/sms-notifier.yml)

The CloudFormation template requires the following parameters:

- AWS Health Tool configuration
  - **Phone number**: The phone number to send notifications to.

More information about AWS Health is available here: http://docs.aws.amazon.com/health/latest/ug/what-is-aws-health.html

Note that this is a just an example of how to set up automation with AWS Health, Amazon CloudWatch Events, and AWS Lambda. We recommend testing this example and tailoring it to your environment before using it in your production environment.

### License
AWS Health Tools are licensed under the Apache 2.0 License.
