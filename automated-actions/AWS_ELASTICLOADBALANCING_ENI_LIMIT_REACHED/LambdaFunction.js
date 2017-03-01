// Sample Lambda Function to remove unattached ENIs in the region of the event when AWS Health AWS_ELASTICLOADBALANCING_ENI_LIMIT_REACHED events are generated. 
// This is useful for situations where you might have leftover ENIs that are not used and are preventing load balancer scaling
'use strict';
var AWS = require('aws-sdk');
const dryRun = ((process.env.DRY_RUN || 'true') == 'true');
const maxEniToProcess = process.env.MAX_ENI || 100;
var ec2 = null; // scoping object so both functions can see it

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
	ec2 = new AWS.EC2(); // creating the object now that we know event region
	
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
            var numberToProcess = data.NetworkInterfaces.length;
            if ((maxEniToProcess > 0) && (data.NetworkInterfaces.length > maxEniToProcess)) numberToProcess = maxEniToProcess;
            console.log('Found %s available ENI; processing %s',data.NetworkInterfaces.length,numberToProcess);
            // for each interface, remove it
            for ( var i=0; i < numberToProcess; i+=1)
            {
                deleteNetworkInterface(data.NetworkInterfaces[i].NetworkInterfaceId,dryRun); 
            }
            
            callback(null, awsHealthSuccessMessage); //return success
        }
    });
};

//This function removes an ENI
function deleteNetworkInterface (networkInterfaceId, dryrun) {
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
                    console.log('Dry run attempt complete for %s after %s retries', networkInterfaceId, this.retryCount);
                    break;
                case 'RequestLimitExceeded':
                    console.log('Request limit exceeded while processing %s after %s retries', networkInterfaceId, this.retryCount);
                    break;
                default:
                    console.log(networkInterfaceId, err, err.stack);    
            }
        }
        else console.log('ENI %s deleted after %s retries', networkInterfaceId, this.retryCount);  // successful response
    });
}