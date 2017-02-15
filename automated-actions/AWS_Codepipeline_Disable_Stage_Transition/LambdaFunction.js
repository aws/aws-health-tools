// Sample Lambda Function to disable stage transition to pause deployments when an AWS Health issue event is generated.
var AWS = require('aws-sdk');
var codepipeline = new AWS.CodePipeline();

// define configuration
const pipelineName = process.env.pipelineName; //Pipeline Name
const stageName = process.env.stageName; //Stage Name (e.g. Beta)

//main function which gets AWS Health data from Cloudwatch event
exports.handler = (event, context, callback) => {
    //extract details from Cloudwatch event
    eventName = event.detail.eventTypeCode;
    //disable transitions into the next stage of the pipeline
    var params = {
        pipelineName: pipelineName, 
        reason: "AWS Health issue detected - please see AWS Personal Health Dashboard for more details",
        stageName: stageName, 
        transitionType: "Inbound"
    };
    codepipeline.disableStageTransition(params, function(err, data) {
    if (err) {
        const errorMessage = `Error in disabling CodePipeline stage transition for pipeline, ${pipelineName} in response to AWS Health event: ${eventName}.`;
        console.log(errorMessage, err);
        callback(errorMessage);
        }
    else {
        const successMessage = `Successfully got details from AWS Health event, ${eventName}, and disabled stage transition to ${stageName} for pipeline, ${pipelineName}.`;
        console.log(successMessage, data);
        callback(null, successMessage); //return success
        }
    });
};

