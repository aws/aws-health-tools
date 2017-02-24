// Sample Lambda Function to remove unattached ENIs in the region of the event when AWS Health AWS_ELASTICLOADBALANCING_ENI_LIMIT_REACHED events are generated. 
// This is useful for situations where you might have leftover ENIs that are not used and are preventing load balancer scaling
'use strict';
var AWS = require('aws-sdk');
const dryRun = ((process.env.DRY_RUN || 'true') == 'true');

//main function which gets AWS Health data from Cloudwatch event
exports.handler = (event, context, callback) => {
    //extract details from Cloudwatch event
    var eventName = event.detail.eventTypeCode;
    var region = event.region;
    const awsHealthSuccessMessage = `Successfully got details from AWS Health event ${eventName} and executed automated action in ${region}. Further details in CloudWatch Logs.`;

    // we only need to run this automation once per invocation since the issue 
    // of ENI exhaustion is regional and not dependent on the load balancers in the alert
    // Event will only trigger for one region so we don't have to loop that
    AWS.config.update({region: region});
    AWS.config.update({maxRetries: 3});
    var ec2 = new AWS.EC2();
    
    console.log ('Getting the list of available ENI in region %s', region);
    var params = {
        Filters: [{Name: 'status',Values: ['available']}]
    };
    
    ec2.describeNetworkInterfaces(params, function(err, data) {
        if (err) 
        {
            console.log( region, err, err.stack); // an error occurred
            callback('Error describing ENIs; check CloudWatch Logs for details');
        }
        else 
        {
            console.log('Found %s available ENI',data.NetworkInterfaces.length);
            // for each interface, remove it
            for ( var i=0; i < data.NetworkInterfaces.length; i+=1)
            {
                deleteNetworkInterface(data.NetworkInterfaces[i].NetworkInterfaceId,dryRun); 
            }
            
            callback(null, awsHealthSuccessMessage); //return success
        }
    });
};

//This function removes an ENI
function deleteNetworkInterface (networkInterfaceId, dryrun) {
    var ec2 = new AWS.EC2();
    
    console.log ('Running code to delete ENI %s with Dry Run set to %s', networkInterfaceId, dryrun);
    var deleteNetworkInterfaceParams = {
        NetworkInterfaceId: networkInterfaceId,
        DryRun: dryrun
    };
    ec2.deleteNetworkInterface(deleteNetworkInterfaceParams, function(err, data) {
        if (err) 
        {
            switch (err.code)
            {
                case 'DryRunOperation':
                    console.log('Dry run attempt complete for %s', networkInterfaceId);
                    break;
                case 'RequestLimitExceeded':
                    console.log('Request limit exceeded while processing %s after %s retries', networkInterfaceId, this.retryCount);
                    break;
                default:
                    console.log(networkInterfaceId, err, err.stack);    
            }
        }
        else console.log('ENI deleted: %s', networkInterfaceId);  // successful response
    });
}