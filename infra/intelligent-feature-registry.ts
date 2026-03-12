import { Feature, ApiStageType } from '@ncino/aws-cdk';
import { Utility } from '@ncino/aws-cdk';
import { DataStack } from './data-stack';
import { LambdaStack } from './lambda-stack';
import { ApiStack } from './api-stack';

const deployAccount = process.env.CDK_DEPLOY_ACCOUNT || process.env.CDK_DEFAULT_ACCOUNT;
const deployRegion = process.env.CDK_DEPLOY_REGION || process.env.CDK_DEFAULT_REGION;

console.log('🛠 Feature');
const feature = new Feature({
  name: 'intelligent-feature-registry',
  description: 'Intelligent Feature Registry for Bedrock inference profile provisioning',
  standardFeature: false
});

if (Utility.isDevopsAccount()) {
  feature.createDeploymentPipeline({
    repositoryName: 'intelligentFeatureRegistry',
    isS3Source: true,
    branch: 'release',
    deployBuildSpecPath: 'config/deploy-buildspec.yml',
    devBuildSpecPath: 'config/dev-buildspec.yml',
    skipDevDeployment: true
  });
} else {
  const stageName = feature.getContext('deploymentStage', ApiStageType.BLUE);

  console.log('🛠 Data Stack');
  const dataStack = new DataStack(feature, feature.getFullName('DataStack'), {
    description: 'Contains data resources for intelligent-feature-registry.',
    env: {
      account: deployAccount,
      region: deployRegion
    }
  });
  feature.setStack('dataStack', dataStack);

  console.log('🛠 Lambda Stack');
  const lambdaStack = new LambdaStack(feature, `${feature.getFullName('LambdaStack')}-${stageName}`, {
    description: 'Contains lambda functions for intelligent-feature-registry.',
    env: {
      account: deployAccount,
      region: deployRegion
    },
    stageName,
    databaseTable: dataStack.databaseTable,
    databaseTableName: dataStack.databaseTable.tableName,
    databaseTableGsi1Name: dataStack.databaseTableGsi1Name
  });
  lambdaStack.addDependency(dataStack);
  feature.setStack('lambdaStack', lambdaStack);

  console.log('🛠 Api Stack');
  const apiStack = new ApiStack(feature, feature.getFullName('ApiStack'), {
    description: 'Contains APIs for intelligent-feature-registry.',
    env: {
      account: deployAccount,
      region: deployRegion
    },
    registerProfile: lambdaStack.registerProfile,
    lookupProfile: lambdaStack.lookupProfile,
    deleteProfile: lambdaStack.deleteProfile
  });
  apiStack.addDependency(lambdaStack);
  feature.setStack('apiStack', apiStack);
}
feature.synth();
