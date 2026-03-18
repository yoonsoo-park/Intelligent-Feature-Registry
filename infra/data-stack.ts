import { Feature, Stack } from '@ncino/aws-cdk';
import { RemovalPolicy, StackProps } from 'aws-cdk-lib';
import { AttributeType, BillingMode, StreamViewType, Table } from 'aws-cdk-lib/aws-dynamodb';

export class DataStack extends Stack {
  private feature: Feature;
  public databaseTable: Table;
  public databaseTableGsi1Name: string;

  constructor(scope: Feature, id: string, props?: StackProps) {
    super(scope, id, props);
    this.feature = scope;
    const removalPolicy = this.getContext('temporary') ? RemovalPolicy.DESTROY : RemovalPolicy.RETAIN;
    this.databaseTable = this.createDatabaseTable(removalPolicy);
    this.grantBedrockAccess();
  }

  private grantBedrockAccess() {
    this.feature.addServiceAccess('*', [
      'bedrock:CreateInferenceProfile',
      'bedrock:GetInferenceProfile',
      'bedrock:DeleteInferenceProfile',
      'bedrock:ListInferenceProfiles',
      'bedrock:TagResource'
    ]);
  }

  private createDatabaseTable(removalPolicy: RemovalPolicy): Table {
    const tableName: string = this.getFullName('Database');
    const table = new Table(this, tableName, {
      tableName,
      partitionKey: {
        name: 'pk',
        type: AttributeType.STRING
      },
      sortKey: {
        name: 'sk',
        type: AttributeType.STRING
      },
      billingMode: BillingMode.PAY_PER_REQUEST,
      removalPolicy,
      stream: StreamViewType.NEW_AND_OLD_IMAGES,
      timeToLiveAttribute: 'expires_at'
    });
    this.feature.addServiceAccess(table.tableArn, [
      'dynamodb:BatchGetItem',
      'dynamodb:GetItem',
      'dynamodb:Query',
      'dynamodb:PutItem',
      'dynamodb:UpdateItem',
      'dynamodb:DeleteItem'
    ]);

    const indexName = 'gsi1';
    table.addGlobalSecondaryIndex({
      indexName,
      partitionKey: {
        name: 'gsi1pk',
        type: AttributeType.STRING
      },
      sortKey: {
        name: 'gsi1sk',
        type: AttributeType.STRING
      }
    });
    this.databaseTableGsi1Name = indexName;
    this.feature.addServiceAccess(`${table.tableArn}/index/${indexName}`, ['dynamodb:Query']);

    this.feature.addServiceAccess(`${table.tableArn}/stream/*`, [
      'dynamodb:DescribeStream',
      'dynamodb:GetRecords',
      'dynamodb:GetShardIterator',
      'dynamodb:ListStreams'
    ]);

    return table;
  }
}
