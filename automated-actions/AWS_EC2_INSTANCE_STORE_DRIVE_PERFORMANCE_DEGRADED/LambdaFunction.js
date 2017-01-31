// Sample Lambda Function to stop EC2 instances when AWS Health AWS_EC2_INSTANCE_STORE_DRIVE_PERFORMANCE_DEGRADED events are generated. This is useful for situations where there is data redundancy and automated launch of instnaces (e.g. via Autoscaling).
var AWS = require('aws-sdk');

// define configuration
const tagKey ='stage';
const tagValue ='prod';

//main function which gets AWS Health data from Cloudwatch event
exports.handler = (event, context, callback) => {
    //extract details from Cloudwatch event
    eventName = event.detail.eventTypeCode;
    affectedEntities = event.detail.affectedEntities;
    region = event.region;
    const awsHealthSuccessMessage = `Successfully got details from AWS Health event, ${eventName} and executed automated action.`;
    
    // setting up a loop that calls the function for the automated action for each of the resources flagged by AWS Health
    for ( var i=0; i < affectedEntities.length; i+=1 )
    {
        instanceId = affectedEntities[i].entityValue;
        if (affectedEntities[i].tags[[tagKey]] == tagValue){
            stopInstances (instanceId, region);
        }
        else console.log ('The following instance does not match the configured tag: ', instanceId);
    }
    callback(null, awsHealthSuccessMessage); //return success
};

//This function stops an EC2 Instance
function stopInstances (instanceId, region) {
    AWS.config.update({region: region});
    var ec2 = new AWS.EC2();
    console.log ('attempting to stop the following instance: ', instanceId);
    var stopInstancesParams = {
        InstanceIds: [instanceId],
        DryRun: true
    };
    ec2.stopInstances(stopInstancesParams, function(err, data) {
        if (err) console.log(instanceId, region, err, err.stack); // an error occurred
        else console.log("Instance stopped: ", instanceId, region);           // successful response
    });
}
