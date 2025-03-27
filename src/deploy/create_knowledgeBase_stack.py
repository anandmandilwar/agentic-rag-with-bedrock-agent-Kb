import warnings
import json
import os
import boto3
from botocore.exceptions import ClientError
from utility import create_bedrock_execution_role, create_oss_policy_attach_bedrock_execution_role, create_policies_in_oss, interactive_sleep
import random
from retrying import retry
credentials = boto3.Session().get_credentials()
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth, RequestError
from dotenv import load_dotenv

load_dotenv()


suffix = random.randrange(200, 900)

#sts_client = boto3.client('sts')
#boto3_session = boto3.session.Session()
region_name = "us-east-1"
bedrock_agent_client = boto3.client('bedrock-agent')
service = 'aoss'
aoss_client = boto3.client('opensearchserverless')
s3_client = boto3.client('s3')
#s3_suffix = f"{region_name}-{account_id}"
#bucket_name = f'bedrock-kb-6915-{s3_suffix}'

def check_if_bucket_exists(bucket_name):
    try:
        s3_client.head_bucket(Bucket=bucket_name)
        print(f'Bucket {bucket_name} Exists')
        return True
    except ClientError as e:
        print(f'Creating bucket {bucket_name}')
        if region_name == "us-east-1":
            s3bucket = s3_client.create_bucket(
                Bucket=bucket_name
            )
        else:
            s3bucket = s3_client.create_bucket(
            Bucket=bucket_name,
            CreateBucketConfiguration={ 'LocationConstraint': region_name }
            )

# Function to create vector store
# amazonq-ignore-next-line
def create_oss_collection(vector_store_name, bucket_name,bedrock_kb_execution_role,bedrock_kb_execution_role_arn):

    # create bedrock execution role
    #bedrock_kb_execution_role = create_bedrock_execution_role(bucket_name)
    #bedrock_kb_execution_role_arn = bedrock_kb_execution_role['Role']['Arn']

    # create security, network and data access policies within OSS
    encryption_policy, network_policy, access_policy = create_policies_in_oss(vector_store_name=vector_store_name,
                       aoss_client=aoss_client,
                       bedrock_kb_execution_role_arn=bedrock_kb_execution_role_arn)
    collection = aoss_client.create_collection(name=vector_store_name,type='VECTORSEARCH')
    print("Collecton - {}".format(collection))

    # Get the OpenSearch serverless collection URL
    collection_id = collection['createCollectionDetail']['id']
    host = collection_id + '.' + region_name + '.aoss.amazonaws.com'
    print("Host - {}".format(host))

    # Wait for collection to be ready
    response = aoss_client.batch_get_collection(names=[vector_store_name])
    while response['collectionDetails'][0]['status'] == 'CREATING':
        print("Waiting for collection to be ready...")
        interactive_sleep(5)
        response = aoss_client.batch_get_collection(names=[vector_store_name])
        print('\nCollection successfully created:')
        print("\nCollection Details - {}".format(response["collectionDetails"]))
        print("\nCollection Status - {}".format(response["collectionDetails"][0]["status"]))
    collection_arn = collection["createCollectionDetail"]['arn']
    print("Collection ARN - {}".format(collection_arn))
    return host, collection_arn,collection_id

def attach_oss_policy(collection_id,bedrock_kb_execution_role,account_ID,region_name):
    # create opensearch serverless access policy and attach it to Bedrock execution role
    try:
        create_oss_policy_attach_bedrock_execution_role(collection_id=collection_id,
                                                       bedrock_kb_execution_role=bedrock_kb_execution_role,
                                                       account_number=account_ID,region_name=region_name)
        # It can take upto a minn for data access rules to be effective
        interactive_sleep(60)

        #return host, collection_arn
    except ClientError as e:
        print("Policy already exists")
        print(e)
        return False
    
def create_vector_index(host,index_name):
    # Create Vector index
    awsauth = auth = AWSV4SignerAuth(credentials, region_name, service)
    body_json = {
    "settings": {
        "index.knn": "true",
        #"number_of_shards": 1,
        #"knn.algo_param.ef_search": 512,
        #"number_of_replicas": 0,
    },
    "mappings": {
        "properties": {
            "vector_field": {
                "type": "knn_vector",
                "dimension": 1536,
                "method": {
                    "name": "hnsw",
                    "engine": "faiss",
                    "space_type": "l2",
                    "parameters": {"ef_construction": 5, "m": 2}
                },
            },
            "text": {
                "type": "text"
            },
            "text-metadata": {
                "type": "text"         }
        }
    }
    }
    # Build the Opensearch client
    opensearch_client = OpenSearch(
        hosts=[{'host': host, 'port': 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=300
    )

    # Create Index
    try:
        response = opensearch_client.indices.create(index_name, body=body_json)
        print('\nCreating index:')
        print(response)

        # Index creation can take up to a minute
        interactive_sleep(60)
    except RequestError as e:
        print("Index already exists")
        print(e)
        print(f'Error while trying to create the index, with error {e.error}\nyou may unmark the delete above to delete, and recreate the index')

    #return index_name

# Function to Create Knowledge Base
@retry(wait_random_min=1000, wait_random_max=2000,stop_max_attempt_number=7)
def create_bedrock_knowledge_base(region_name, collection_arn,knowledge_base_name,index_name,bedrock_kb_execution_role_arn):
    

    opensearchServerlessConfiguration = {
            "collectionArn": collection_arn,
            "vectorIndexName": index_name,
            "fieldMapping": {
                "vectorField": "vector_field",
                "textField": "text",
                "metadataField": "text-metadata"
            }
        }
    

    # The embedding model used by Bedrock to embed ingested documents, and realtime prompts
    embeddingModelArn = f"arn:aws:bedrock:{region_name}::foundation-model/amazon.titan-embed-text-v1"
    knowledge_base_name = f"bedrock-sample-knowledge-base-{suffix}"
    description = "Amazon shareholder letter knowledge base."
    roleArn = bedrock_kb_execution_role_arn

    # Create a KnowledgeBase
    try:
        create_kb_response = bedrock_agent_client.create_knowledge_base(
            name=knowledge_base_name,
            description=description,
            roleArn=roleArn,
            knowledgeBaseConfiguration={
                "type": "VECTOR",
                "vectorKnowledgeBaseConfiguration": {
                    "embeddingModelArn": embeddingModelArn
                    #"embeddingModelConfiguration" : {
                    #    "dimensions": 1536
                    #}
                }
            },
            storageConfiguration={
                "type": "OPENSEARCH_SERVERLESS",
                "opensearchServerlessConfiguration": opensearchServerlessConfiguration
            }
        )
        print("Knowledge base created successfully")
        return create_kb_response["knowledgeBase"]
    # print(create_kb_response)
    except ClientError as e:
        print(f"Error occurred while creating KB: {e}")

# Function to upload file from local to S3 Bucket
def uploadDirectory(local_path,bucket_name):
    prefix_key = "data/"
    for filename in os.listdir(local_path):
         #print("Uploading:", filename)
         s3_client.upload_file(local_path + filename, bucket_name, prefix_key + filename)

def create_kb_data_source(data_source_name,kb_id,bucket_name): # Create a DataSource in KnowledgeBase():
    description = "Amazon shareholder letter knowledge base Data source."
    # Ingest strategy - How to ingest data from the data source
    chunkingStrategyConfiguration = {
        "chunkingStrategy": "FIXED_SIZE",
        "fixedSizeChunkingConfiguration": {
            "maxTokens": 512,
            "overlapPercentage": 20
        }
    }

    # The data source to ingest documents from, into the OpenSearch serverless knowledge base index
    s3Configuration = {
        "bucketArn": f"arn:aws:s3:::{bucket_name}",
        "inclusionPrefixes":["data"]
    }    
    create_ds_response = bedrock_agent_client.create_data_source(
        name = data_source_name,
        description = description,
        knowledgeBaseId = kb_id,
        dataSourceConfiguration = {
            "type": "S3",
            "s3Configuration":s3Configuration
        },
        vectorIngestionConfiguration = {
            "chunkingConfiguration": chunkingStrategyConfiguration
        }
    )
    ds = create_ds_response["dataSource"] # Get the DataSource
    ds_id = ds["dataSourceId"] # Get the DataSource ID
    return ds_id

def start_ingestion_job(kb_id,dataSource_ID):
    interactive_sleep(30)
    start_job_response = bedrock_agent_client.start_ingestion_job(
        knowledgeBaseId = kb_id,
        dataSourceId = dataSource_ID
    )
    job = start_job_response["ingestionJob"]
    #print("Job started successfully with Job ID - {}".format(job["ingestionJobId"]))
    # Get job
    while(job['status']!='COMPLETE' ):
        get_job_response = bedrock_agent_client.get_ingestion_job(
        knowledgeBaseId = kb_id,
            dataSourceId = dataSource_ID,
            ingestionJobId = job["ingestionJobId"]
        )
        job = get_job_response["ingestionJob"]
        
        interactive_sleep(30)
    print("Job Completed successfully with Job ID - {}".format(job))


def create_kb_stack(account_ID,region_name,bucket_name):

    # Check if the bucket exists
    print("Checking if bucket exists...")
    check_if_bucket_exists(bucket_name)
    print(f'Bucket {bucket_name} Exists')
    
    data_root = "data/"
    suffix = random.randrange(200, 900)
    vector_store_name = f'bedrock-sample-rag-{suffix}'
    index_name = f"bedrock-sample-rag-index-{suffix}"
    
    print("Creating required policies for KB role...")
    bedrock_kb_execution_role = create_bedrock_execution_role(bucket_name,account_ID,region_name)
    bedrock_kb_execution_role_arn = bedrock_kb_execution_role['Role']['Arn']
    
    print("Creating Collection...")
    # Call function to create Collection
    host, collection_arn,collection_id = create_oss_collection(vector_store_name, bucket_name,bedrock_kb_execution_role,bedrock_kb_execution_role_arn)
    
    print("Creating required policies for OSS...")
    # create opensearch serverless access policy and attach it to Bedrock execution role
    attach_oss_policy(collection_id,bedrock_kb_execution_role,account_ID,region_name)
    
    print("Host and Collection ARN - {}, {}".format(host, collection_arn))
    
    print("Creating Vector Index...")
    # Call function to create Vector Index
    create_vector_index(host,index_name)

    print("Uploading data to S3 for Knowledge base Data Source...")
    # Upload the data to S3
    uploadDirectory(data_root, bucket_name)


    print("Creating Knowledge Base...")
    # create Knowledge Base
    knowledge_base_name = f'bedrock-sample-rag-kb-{suffix}'
    #print("Creating KB phase with collection ARn - {}".format(collection_arn))
    kb = create_bedrock_knowledge_base(region_name, collection_arn,knowledge_base_name,index_name,bedrock_kb_execution_role_arn)
    kb_id = kb['knowledgeBaseId']
    kb_arn = kb['knowledgeBaseArn']
    

    print("Creating Data Source...")
    # Create datasource
    data_source_name = f'bedrock-sample-rag-kb-ds-{suffix}'
    dataSource_ID = create_kb_data_source(data_source_name,kb_id,bucket_name)

    print("Starting ingestion job...")
    # Call function start_ingestion_job to Start ingestion job
    start_ingestion_job(kb_id,dataSource_ID)
    
    print("Knowledge Based ID and ARN are {}, {} respectively".format(kb_id, kb_arn))
    return kb_arn, kb_id