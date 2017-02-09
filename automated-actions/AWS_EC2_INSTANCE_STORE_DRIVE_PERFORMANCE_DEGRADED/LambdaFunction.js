// Sample Lambda Function to stop EC2 instances when AWS Health AWS_EC2_INSTANCE_STORE_DRIVE_PERFORMANCE_DEGRADED events are generated. This is useful for situations where there is data redundancy and automated launch of instnaces (e.g. via Autoscaling).
var AWS = require('aws-sdk');

// define configuration
const tagKey = process.env.TAG_KEY;
const tagValue = process.env.TAG_VALUE;
const action = process.env.EC2_ACTION;
const dryRun = process.env.DRY_RUN;

function getMatchingInstances(affectedEntities){
    //initialize an empty array
    var instances = [];
    // loop through entities
    for ( var i=0; i < affectedEntities.length; i+=1 )
    {
        var instanceId = affectedEntities[i].entityValue;
        // check that the instance has tags
        if (typeof (affectedEntities[i].tags) != 'undefined') {
            // check that tags match
            if (affectedEntities[i].tags[[tagKey]] == tagValue){
                // add instanceid to the array
                instances.push(instanceId);
            }
            else console.log ('The following instance does not match the configured tag: ', instanceId);
        }
        else console.log ('The following instance does not match the configured tag: ', instanceId);
    }
    return instances
}

function setupClient(region){
    // set the region for the sdk
    AWS.config.update({region: region});
    //create the ec2 client
    return new AWS.EC2();
}

function getParams(instances, dryRun){
    // setup parameters
    var instancesParams = {
        InstanceIds: instances,
        DryRun: false
    };
    // enable DryRun if set in environment variables
    if (dryRun == 'true')  {
        instancesParams.DryRun = true;
        console.log()
    }
    return instancesParams
}

//main function which gets AWS Health data from Cloudwatch event
exports.handler = (event, context, callback) => {
    console.log(event);
    console.log(JSON.stringify(event));
    // function to handle ec2 API response
    function handleResponse(err, data) {
        if (err) {                                                          // an error occurred
            if (err.code == 'DryRunOperation') {
                console.log(instances, region, err.message);
                callback(null, awsHealthSuccessMessage);
            } else {
                console.log(instances, region, err, err.stack);
                throw err;
            }

        } else {
            console.log(`Instance ${action}: `, instances, region);
            //return success
            callback(null, awsHealthSuccessMessage);
        }                                                                   // successful response
    }

    //extract details from Cloudwatch event
    var eventName = event.detail.eventTypeCode;
    var affectedEntities = event.detail.affectedEntities;
    var region = event.region;

    const awsHealthSuccessMessage = `Successfully got details from AWS Health event, ${eventName} and executed automated action.`;

    // get affected instances that match the required tags
    instances = getMatchingInstances(affectedEntities);

    if (instances.length > 0) {                           //there are some instances to take action on

        //create an ec2 api client in the event's region
        var ec2 = setupClient(region);

        // setup parameters
        var instancesParams = getParams(instances, dryRun);

        console.log (`attempting to ${action} the following instances: `, instances);
        // Call either the Terminate or the Stop API
        if (action == 'Terminate') ec2.terminateInstances(instancesParams, handleResponse);
        else ec2.stopInstances(instancesParams, handleResponse);

    } else {
        console.log('No instances in the event match the required tags, exiting without any action');
        callback(null, awsHealthSuccessMessage);
    }

};
