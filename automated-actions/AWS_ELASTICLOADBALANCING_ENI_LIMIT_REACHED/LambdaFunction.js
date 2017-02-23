// Sample Lambda Function to remove unattached ENIs in the region of the event when AWS Health AWS_ELASTICLOADBALANCING_ENI_LIMIT_REACHED events are generated. 
// This is useful for situations where you might have leftover ENIs that are not used and are preventing load balancer scaling
'use strict';
var AWS = require('aws-sdk');
const dryRun = process.env.DRY_RUN || 'true';

//main function which gets AWS Health data from Cloudwatch event
exports.handler = (event, context, callback) => {
    //extract details from Cloudwatch event
    var eventName = event.detail.eventTypeCode;
    var region = event.region;
    const awsHealthSuccessMessage = `Successfully got details from AWS Health event ${eventName} and executed automated action in ${region}.`;

    // we only need to run this automation once per invocation since the issue 
    // of ENI exhaustion is regional and not dependent on the load balancers in the alert
    // Event will only trigger for one region so we don't have to loop that
    AWS.config.update({region: region});
    var ec2 = new AWS.EC2();
    
    console.log ('Getting the list of available ENI in region %s', region);
    var params = {
        Filters: [{Name: 'status',Values: ['available']}]
    };
    
    ec2.describeNetworkInterfaces(params, function(err, data) {
        if (err) console.log( region, err, err.stack); // an error occurred
        else 
        {
            console.log('Found %s available ENI',data.NetworkInterfaces.length); // successful response
            // for each interface, remove it
            for ( var i=0; i < data.NetworkInterfaces.length; i+=1)
            {
                var netId = data.NetworkInterfaces[i].NetworkInterfaceId;
                if (dryRun == 'true')
                {
                    console.log('Dry run is true - not deleting %s', netId);            
                } else {
                    console.log('No dry run - deleting %s', netId);
                    deleteNetworkInterface(netId); 
                }
            }
        }
    });

    callback(null, awsHealthSuccessMessage); //return success
};

//This function removes an ENI
function deleteNetworkInterface (networkInterfaceId) {
    var ec2 = new AWS.EC2();
    
    console.log ('Attempting to delete the following ENI: %s', networkInterfaceId);
    var deleteNetworkInterfaceParams = {
        NetworkInterfaceId: networkInterfaceId,
        DryRun: false
    };
    ec2.deleteNetworkInterface(deleteNetworkInterfaceParams, function(err, data) {
        if (err) console.log(networkInterfaceId, err, err.stack); // an error occurred
        else console.log('ENI deleted: %s', networkInterfaceId);  // successful response
    });
}