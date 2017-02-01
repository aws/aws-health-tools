// Sample Lambda Function to send notifications via text when an  AWS Health event happens
var AWS = require('aws-sdk');
var sns = new AWS.SNS();

//main function which gets AWS Health data from Cloudwatch event
exports.handler = (event, context, callback) => {
    //get phone number from Env Variable
    var phoneNumber = process.env.PHONE_NUMBER;
    //extract details from Cloudwatch event
    eventName = event.detail.eventTypeCode
    healthMessage = 'The following AWS Health event type has occured: ' + eventName + ' For more details, please see https://phd.aws.amazon.com/phd/home?region=us-east-1#/dashboard/open-issues';
    //prepare message for SNS to publish
    var snsPublishParams = {
        Message: healthMessage,
        PhoneNumber: phoneNumber,
    };
    sns.publish(snsPublishParams, function(err, data) {
    if (err) {
        const snsPublishErrorMessage = `Error publishing AWS Health event to SNS`;
        console.log(snsPublishErrorMessage, err);
        callback(snsPublishErrorMessage);
        }
    else {
        const snsPublishSuccessMessage = `Successfully got details from AWS Health event, ${eventName} and sent SMS via SNS.`;
        console.log(snsPublishSuccessMessage, data);
        callback(null, snsPublishSuccessMessage); //return success
        }
    });
};
