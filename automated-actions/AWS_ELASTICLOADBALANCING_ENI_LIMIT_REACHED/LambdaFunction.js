// Sample Lambda Function to remove unattached ENIs in the region of the event when AWS Health AWS_ELASTICLOADBALANCING_ENI_LIMIT_REACHED events are generated. 
// This is useful for situations where you might have leftover ENIs that are not used and are preventing load balancer scaling
'use strict';
var AWS = require('aws-sdk');

//main function which gets AWS Health data from Cloudwatch event
exports.handler = (event, context, callback) => {
    //extract details from Cloudwatch event
    var eventName = event.detail.eventTypeCode;
    var region = event.region;
    const awsHealthSuccessMessage = `Successfully got details from AWS Health event, ${eventName} and executed automated action.`;

	// the event could have multiple load balancers listed but this does not matter here
	// ultimately we only need to run this automation once per invocation since the issue 
	// of ENI exhaustion is regional and not dependent on the load balancers in the alert
	// Event will only trigger for one region so we don't have to loop that
	AWS.config.update({region: region});
    var ec2 = new AWS.EC2();
	
	console.log ('Getting the list of available ENI in region %s', region);
	var params = {
		Filters: [{	Name: 'status',	Values: ['available']}]
	};
	
	var networkInterfaces = null;
	ec2.describeNetworkInterfaces(params, function(err, data) {
		if (err) console.log( region, err, err.stack); // an error occurred
		else 
		{
			console.log("Found %s available ENI",data.NetworkInterfaces.length); // successful response
			// for each interface, remove it
			for ( var i=0; i < data.NetworkInterfaces.length; i+=1) deleteNetworkInterface(data.NetworkInterfaces[i], region);
		}
	});

    callback(null, awsHealthSuccessMessage); //return success
};

//This function removes an available (unattached) ENI
//Take an instance description as argument so we can verify attachment status
function deleteNetworkInterface (networkInterface, region) {
    AWS.config.update({region: region});
    var ec2 = new AWS.EC2();
	
	if (networkInterface.Status == "available") {
		console.log ('Attempting to delete the following ENI: %s', networkInterface.NetworkInterfaceId);
		var deleteNetworkInterfaceParams = {
			NetworkInterfaceId: networkInterface.NetworkInterfaceId,
			DryRun: false
		};
		ec2.deleteNetworkInterface(deleteNetworkInterfaceParams, function(err, data) {
			if (err) console.log(networkInterface.NetworkInterfaceId, region, err, err.stack); // an error occurred
			else console.log("ENI deleted: %s", networkInterface.NetworkInterfaceId);           // successful response
		});
	}
	else console.log ('The following ENI is not in an available (unattached) state: %s', networkInterface.NetworkInterfaceId);
}