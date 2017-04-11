## AWS Health AWS_ELASTICLOADBALANCING_ENI_LIMIT_REACHED

### Description
An ELB has attempted to change load balancer nodes (for example, to scale) and this operation has been impacted by a lack of available ENIs in the associated region. ELB needs available ENIs to successfully do node operations. Clearing this up requires either freeing up ENIs (such as by deleting unattached ENIs), terminating instances or requesting a limit increase via http://docs.aws.amazon.com/general/latest/gr/aws_service_limits.html.

BE CAREFUL: This script, if so configured, will delete unattached ENIs from your environment. If you regularly leave ENIs unattached for a reason, use caution here.

### Setup and Usage

#### Cloudformation Setup
Choose **Launch Stack** to launch the template in the US East (N. Virginia) Region in your account:

[![Launch AWS Health Code Elastic Load Balancing ENI Limit Reached](../../images/cloudformation-launch-stack.png)](https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/new?stackName=AWSHealthElasticLoadBalancingENILimitReached&templateURL=https://s3.amazonaws.com/aws-health-tools-assets/cloudformation-templates/AWSHealthElasticLoadBalancingENILimitReached.json)

Setting the Dry Run parameter to true (the default) will keep the script from actually doing deletions. Set it to false to enable deletion.
Setting the Max ENI parameter (default 100) to a value higher than zero will limit the number of ENIs processed. Setting it to zero will cause the script to process all of the found unattached ENIs. Care should be used here as you can end up with the API calls being throttled by EC2. The script is configured for a limited number of retry attempts and in development testing 100 was found to be a good reliable value for Max ENIs.

#### Manual Setup
You can automatically delete unattached ENIs using Amazon Cloudwatch events and AWS Lambda using the following instructions:

1. Create an IAM role for the Lambda function to use. Attach the [IAM policy](IAMPolicy) to the role in the IAM console.
Documentation on how to create an IAM policy is available here: http://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_create.html
Documentation on how to create an IAM role for Lambda is available here: http://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_create_for-service.html#roles-creatingrole-service-console

2. Create a Lambda JavaScript function by using the [sample](LambdaFunction.js) provided and choose the IAM role created in step 1. The sample Lambda function will query for unattached ENIs when AWS Health AWS_ELASTICLOADBALANCING_ENI_LIMIT_REACHED events are generated and delete unattached ENIs. This is useful for situations where you might have created ENIs for testing purposes but forgotten to remove them.

More information about Lambda is available here: http://docs.aws.amazon.com/lambda/latest/dg/getting-started.html

3. Create a CloudWatch Events rule to trigger the Lambda function created in step 2 matching the AWS_ELASTICLOADBALANCING_ENI_LIMIT_REACHED event.
Documentation on how to create an AWS Health CloudWatch Events rule is available here: http://docs.aws.amazon.com/health/latest/ug/cloudwatch-events-health.html

More information about AWS Health is available here: http://docs.aws.amazon.com/health/latest/ug/what-is-aws-health.html

Note that this is a just an example of how to set up automation with AWS Health, Amazon CloudWatch Events, and AWS Lambda. We recommend testing the example and tailoring it to your environment before using it in your production environment. 

#### Testing structure
You can use the following for testing the function via the Lambda console.
Replace the region us-east-2 with the region containing your target ENIs.

```
{
  "region": "us-east-2",
  "detail": {"eventTypeCode": "AWS_ELASTICLOADBALANCING_ENI_LIMIT_REACHED"}
}
```

### License
AWS Health Tools are licensed under the Apache 2.0 License.

