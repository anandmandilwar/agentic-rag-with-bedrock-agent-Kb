from dotenv import load_dotenv
import boto3
import logging
import random
import time
import zipfile
from io import BytesIO
import json
import uuid
import pprint
import os
load_dotenv()
#from requests_aws4auth import AWS4Auth
#from create_kb import create_knowledgebase
from create_knowledgeBase_stack import create_kb_stack
from create_agent import create_agent



# getting boto3 clients for required AWS services
sts_client = boto3.client('sts')
iam_client = boto3.client('iam')
s3_client = boto3.client('s3')
lambda_client = boto3.client('lambda')
bedrock_agent_client = boto3.client('bedrock-agent')
bedrock_agent_runtime_client = boto3.client('bedrock-agent-runtime')

# Get config from environment variables
region =  os.environ.get("REGION_NAME") #"us-east-1"
account_id = os.environ.get("AWS_ACCOUNT_ID") # "123456789"

s3_suffix = f"{region}-{account_id}"
bucket_name = f'bedrock-kb-6915-{s3_suffix}'

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    return logger

 #call logging
logger = setup_logging()

def main():
    
    # Create Knowledge base
    print("Creating Knowledge base...")
    #kb_arn = create_knowledgebase(region, account_id)
    kb_arn, kb_id = create_kb_stack(account_id,region,bucket_name)
    print("Knowledge base created with KB_Id - {} and KB_Arn - {}!".format(kb_id, kb_arn))
    print("====================")    
    print("Creating Agent...")
    va_agent_id = create_agent(region, account_id, kb_arn, kb_id)
    print("Agent created with Agent_Id - {}!".format(va_agent_id))
    print("====================")
    print("Setup Complete!")

if __name__ == "__main__":
    main()
