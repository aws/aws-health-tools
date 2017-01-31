// Sample Lambda Function to send notifications to a SNS topic when an AWS Health event happens
var AWS = require('aws-sdk');
var sns = new AWS.SNS();

// define configuration
const snsTopic ='arn:aws:sns:us-east-1:083010608567:Test_Topic'; //use ARN

//main function which gets AWS Health data from Cloudwatch event
exports.handler = (event, context, callback) => {
    //extract details from Cloudwatch event
    healthMessage = event.detail.eventDescription[0].latestDescription + ' For more details, please see https://phd.aws.amazon.com/phd/home?region=us-east-1#/dashboard/open-issues';
    eventName = event.detail.eventTypeCode
    //prepare message for SNS to publish
    var snsPublishParams = {
        Message: healthMessage, 
        Subject: eventName,
        TopicArn: snsTopic
    };
    sns.publish(snsPublishParams, function(err, data) {
    if (err) {
        const snsPublishErrorMessage = `Error publishing AWS Health event to SNS`;
        console.log(snsPublishErrorMessage, err);
        callback(snsPublishErrorMessage);
        } 
    else {
        const snsPublishSuccessMessage = `Successfully got details from AWS Health event, ${eventName} and published to SNS topic.`;
        console.log(snsPublishSuccessMessage, data);
        callback(null, snsPublishSuccessMessage); //return success
        }
    });
};

