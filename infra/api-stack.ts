import {
  ApiGateway,
  ApiMethodType,
  ApiStageType,
  ApiStageVariable,
  Feature,
  ParameterSource,
  Stack,
  Utility
} from '@ncino/aws-cdk';
import { StackProps } from 'aws-cdk-lib';
import { JsonSchemaType } from 'aws-cdk-lib/aws-apigateway';
import { Function } from 'aws-cdk-lib/aws-lambda';

export interface ApiStackProps extends StackProps {
  readonly registerProfile: Function;
  readonly lookupProfile: Function;
  readonly deleteProfile: Function;
}

export class ApiStack extends Stack {
  private feature: Feature;

  private static readonly STAGE_VARIABLES = ['RegisterProfile', 'LookupProfile', 'DeleteProfile'];

  private createStageVariables(lambdaNames: string[]): ApiStageVariable[] {
    const variables: ApiStageVariable[] = [];
    lambdaNames.forEach((lambdaName: string) => {
      variables.push(
        {
          key: lambdaName,
          value: `${this.getFullName(lambdaName)}-${ApiStageType.BLUE}`,
          stage: ApiStageType.BLUE
        },
        {
          key: lambdaName,
          value: `${this.getFullName(lambdaName)}-${ApiStageType.GREEN}`,
          stage: ApiStageType.GREEN
        }
      );
    });
    return variables;
  }

  constructor(scope: Feature, id: string, props: ApiStackProps) {
    super(scope, id, props);
    this.feature = scope;

    const gateway: ApiGateway = new ApiGateway(
      this,
      Utility.createResourceName('intelligent-feature-registry', this.feature.node.tryGetContext('suffix')),
      {
        name: Utility.createResourceName('intelligent-feature-registry', this.feature.node.tryGetContext('suffix')),
        description: 'API for the Intelligent Feature Registry',
        retainDeployments: true,
        targetStageType: this.getContext('deploymentStage') || ApiStageType.BLUE,
        stageVariables: this.createStageVariables(ApiStack.STAGE_VARIABLES),
        apiExecutionRole: this.feature.baseStack.apiExecutionRole,
        disableDocumentation: true
      }
    );
    this.feature.registerResource('intelligent-feature-registry', gateway);
    this.createApi(gateway, props);
    this.feature.addApiGatewayAccess('IntelligentGatewayAPI', gateway.arnForExecuteApi());
  }

  private createApi(gateway: ApiGateway, props: ApiStackProps): void {
    const profilesResource = gateway.addResource(gateway.root, 'profiles');
    gateway.enableCors(profilesResource);

    gateway.addMethod(
      ApiMethodType.POST,
      profilesResource,
      'RegisterProfile',
      props.registerProfile,
      [
        {
          name: 'team',
          mappingName: 'team',
          required: true,
          type: JsonSchemaType.STRING,
          source: ParameterSource.BODY
        },
        {
          name: 'featureName',
          mappingName: 'featureName',
          required: true,
          type: JsonSchemaType.STRING,
          source: ParameterSource.BODY
        },
        {
          name: 'modelId',
          mappingName: 'modelId',
          required: true,
          type: JsonSchemaType.STRING,
          source: ParameterSource.BODY
        },
        {
          name: 'tags',
          mappingName: 'tags',
          required: false,
          type: JsonSchemaType.OBJECT,
          source: ParameterSource.BODY
        }
      ],
      { stageVariable: 'RegisterProfile', enableCustomStatusCodes: true }
    );

    gateway.addMethod(
      ApiMethodType.GET,
      profilesResource,
      'LookupProfile',
      props.lookupProfile,
      [
        {
          name: 'team',
          mappingName: 'team',
          required: true,
          type: JsonSchemaType.STRING,
          source: ParameterSource.QUERY_STRING
        },
        {
          name: 'featureName',
          mappingName: 'featureName',
          required: true,
          type: JsonSchemaType.STRING,
          source: ParameterSource.QUERY_STRING
        },
        {
          name: 'modelId',
          mappingName: 'modelId',
          required: true,
          type: JsonSchemaType.STRING,
          source: ParameterSource.QUERY_STRING
        }
      ],
      { stageVariable: 'LookupProfile', enableCustomStatusCodes: true }
    );

    gateway.addMethod(
      ApiMethodType.DELETE,
      profilesResource,
      'DeleteProfile',
      props.deleteProfile,
      [
        {
          name: 'team',
          mappingName: 'team',
          required: true,
          type: JsonSchemaType.STRING,
          source: ParameterSource.QUERY_STRING
        },
        {
          name: 'featureName',
          mappingName: 'featureName',
          required: true,
          type: JsonSchemaType.STRING,
          source: ParameterSource.QUERY_STRING
        },
        {
          name: 'modelId',
          mappingName: 'modelId',
          required: true,
          type: JsonSchemaType.STRING,
          source: ParameterSource.QUERY_STRING
        }
      ],
      { stageVariable: 'DeleteProfile', enableCustomStatusCodes: true }
    );
  }
}
