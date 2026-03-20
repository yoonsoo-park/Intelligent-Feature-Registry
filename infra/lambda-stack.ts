import { ApiStageType, Feature, LogGroup, StageableStack, StageableStackProps } from '@ncino/aws-cdk';
import { FilterCriteria, Function, Runtime, StartingPosition } from 'aws-cdk-lib/aws-lambda';
import { PythonFunction, PythonLayerVersion } from '@aws-cdk/aws-lambda-python-alpha';
import { BundlingOptions } from '@aws-cdk/aws-lambda-python-alpha';
import { DynamoEventSource } from 'aws-cdk-lib/aws-lambda-event-sources';
import { DockerVolume, Duration } from 'aws-cdk-lib';
import { ITable } from 'aws-cdk-lib/aws-dynamodb';
import { Effect, PolicyStatement } from 'aws-cdk-lib/aws-iam';
import path = require('path');
import fs = require('fs');
import os = require('os');

export interface LambdaStackProps extends StageableStackProps {
  databaseTable: ITable;
  databaseTableName: string;
  databaseTableGsi1Name: string;
}

export class LambdaStack extends StageableStack {
  private feature: Feature;
  private sharedLayer: PythonLayerVersion;
  private externalLayer: PythonLayerVersion;

  public registerProfile: Function;
  public lookupProfile: Function;
  public provisionProfile: Function;
  public deleteProfile: Function;
  public listModels: Function;

  constructor(feature: Feature, id: string, props: LambdaStackProps) {
    super(feature, id, props);
    this.feature = feature;

    this.sharedLayer = this.createLayer('Shared', 'shared');
    this.externalLayer = this.createLayer('External', 'external');

    this.registerProfile = this.createFunction('RegisterProfile', 'api/register_profile', {
      databaseTableName: props.databaseTableName,
      databaseTableGsi1Name: props.databaseTableGsi1Name,
      MAX_PROFILES_PER_TEAM: '10',
      MAX_TEAMS: '2'
    });

    this.lookupProfile = this.createFunction('LookupProfile', 'api/lookup_profile', {
      databaseTableName: props.databaseTableName,
      databaseTableGsi1Name: props.databaseTableGsi1Name
    });

    this.provisionProfile = this.createFunction(
      'ProvisionProfile',
      'jobs/provision_profile',
      {
        databaseTableName: props.databaseTableName,
        databaseTableGsi1Name: props.databaseTableGsi1Name,
        awsAccountId: this.targetAccount.getTargetAccountId()
      },
      Duration.minutes(5)
    );

    this.deleteProfile = this.createFunction('DeleteProfile', 'api/delete_profile', {
      databaseTableName: props.databaseTableName,
      databaseTableGsi1Name: props.databaseTableGsi1Name
    });

    this.listModels = this.createFunction('ListModels', 'api/list_models', {
      ALLOWED_PROVIDERS: 'anthropic,amazon'
    });

    this.provisionProfile.addEventSource(
      new DynamoEventSource(props.databaseTable, {
        startingPosition: StartingPosition.TRIM_HORIZON,
        filters: [
          FilterCriteria.filter({
            eventName: ['INSERT', 'MODIFY'],
            dynamodb: {
              NewImage: {
                type: { S: ['PROFILE'] },
                status: { S: ['PROVISIONING'] }
              }
            }
          })
        ],
        enabled: true,
        retryAttempts: 2,
        batchSize: 1
      })
    );

    this.feature.baseStack.lambdaExecutionRole.addToPrincipalPolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: [
          'dynamodb:GetItem',
          'dynamodb:PutItem',
          'dynamodb:UpdateItem',
          'dynamodb:DeleteItem',
          'dynamodb:Query'
        ],
        resources: [props.databaseTable.tableArn, `${props.databaseTable.tableArn}/index/*`]
      })
    );
    this.feature.baseStack.lambdaExecutionRole.addToPrincipalPolicy(
      new PolicyStatement({
        effect: Effect.ALLOW,
        actions: [
          'bedrock:CreateInferenceProfile',
          'bedrock:GetInferenceProfile',
          'bedrock:DeleteInferenceProfile',
          'bedrock:ListFoundationModels',
          'bedrock:ListInferenceProfiles',
          'bedrock:TagResource'
        ],
        resources: ['*']
      })
    );
  }

  private getBundlingOptions(): BundlingOptions {
    // Mount host CA cert bundle into Docker for Zscaler/corporate proxy TLS
    const zscalerCert = path.join(os.homedir(), 'combined-ca-bundle.pem');
    const hostCertPath = fs.existsSync(zscalerCert) ? zscalerCert : '/etc/ssl/cert.pem';
    const hasCert = fs.existsSync(hostCertPath);
    const containerCertPath = '/etc/ssl/certs/ca-certificates.crt';
    const volumes: DockerVolume[] = hasCert ? [{ hostPath: hostCertPath, containerPath: containerCertPath }] : [];
    return {
      environment: {
        UV_NATIVE_TLS: 'true',
        ...(hasCert && {
          SSL_CERT_FILE: containerCertPath,
          PIP_CERT: containerCertPath,
          REQUESTS_CA_BUNDLE: containerCertPath
        })
      },
      volumes
    };
  }

  private createLayer(name: string, assetName: string): PythonLayerVersion {
    const layerName = this.getFullName(name);
    return new PythonLayerVersion(this, layerName, {
      layerVersionName: layerName,
      entry: path.join(__dirname, `../src/layers/${assetName}`),
      compatibleRuntimes: [Runtime.PYTHON_3_11],
      bundling: this.getBundlingOptions()
    });
  }

  private createFunction(
    name: string,
    assetName: string,
    env?: { [key: string]: string },
    timeout: Duration = Duration.seconds(29)
  ): PythonFunction {
    const functionName = this.getFullName(name);
    const environment = {
      region: this.targetAccount.getTargetRegion(),
      deploymentStage: this.node.tryGetContext('deploymentStage')
        ? this.node.tryGetContext('deploymentStage')
        : ApiStageType.BLUE,
      service: this.node.tryGetContext('appName')?.toLowerCase() || 'intel-feature-registry',
      ...env
    };
    new LogGroup(this, `/aws/lambda/${functionName}`);
    const lambdaFunction = new PythonFunction(this, functionName, {
      functionName,
      entry: path.join(__dirname, `../src/functions/${assetName}`),
      index: 'handler.py',
      runtime: Runtime.PYTHON_3_11,
      role: this.feature.baseStack.lambdaExecutionRole,
      environment,
      memorySize: 2048,
      layers: [this.sharedLayer, this.externalLayer],
      timeout,
      bundling: this.getBundlingOptions()
    });
    this.feature.authorizeFunction(lambdaFunction);
    return lambdaFunction;
  }
}
