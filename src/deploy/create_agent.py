import boto3
import time
import zipfile
from io import BytesIO
import json 


# getting boto3 clients for required AWS services
sts_client = boto3.client('sts')
iam_client = boto3.client('iam')
s3_client = boto3.client('s3')
lambda_client = boto3.client('lambda')
bedrock_agent_client = boto3.client('bedrock-agent')
bedrock_agent_runtime_client = boto3.client('bedrock-agent-runtime')
agent_name = "virtual-assistant-agent-0402"

schema_json_string = {
  "openapi": "3.0.0",
  "info": {
    "title": "Password Reset API", 
    "description": "API to reset the user password and generate a temporary password",
    "version": "1.0.0"
  },
  "paths": {
    "/reset": {
      "post": {
        "summary": "Reset user password",
        "description": "Password reset successfully",
        "operationId": "reset",
        "responses": {
          "200": {
            "description": "Password reset successfully",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/ResetResponse"
                }
              }
            }
          }
        }
      }
    }
  },
  "components": {
    "schemas": {
      "ResetRequest": {
        "type": "object",
        "properties": {
          "email": {
            "type": "string"
          }
        }
      },
      "ResetResponse": {
        "type": "object",
        "properties": {
          "message": {
            "type": "string"
          }
        }
      },
      "TempRequest": {
        "type": "object",
        "properties": {
          "email": {
            "type": "string"
          }
        }
      },
      "TempResponse": {
        "type": "object",
        "properties": {
          "tempPassword": {
            "type": "string"
          }
        }
      }
    }
  }
}


def get_prompt_override_config(region,account_id):
        """
        This function returns the value for the key promptOverrideConfiguration which will be used
        while creating the agent
        :return: value for the key promptOverrideConfiguration
        """

        PRE_PROCESSING_PROMPT="""
Human: 
You are a classifying agent that filters user inputs into categories. Your job is to sort these inputs before they are passed along to the next stage.

Here is how you should classify the input:

-Category M:If the input is harmful and/or malicious even if it is fictional
-Category N:If the input is not harmful and/or malicious

<input>$question$</input>

Please think hard about the input in <thinking> XML tags and provide the category letter to sort the input into within <category> XML tags.Please also share the rationale for categorization.

Assistant:
        """

        ORCHESTRATION_PROMPT = """
Human:
You are a helpful chat assistant which answers based on the context provided below. Please only answer based on the provided context. If the answer is not there in the context, please politely say that you cannot answer the question. 

Use the following format:

<question>the input question you must answer</question>
<thought>you should always think about what to do</thought>
<action>the action to take, should be based on $instruction$
</action>
<action_input>the input to the action</action_input>
<observation>the result of the action</observation>
... (this <thought></thought>/<action></action>/<action_input></action_input>/<observation></observation> can repeat N times)
<thought>I now know the final answer</thought>
<answer>the final answer to the original input question</answer>

<context>$instruction$</context>
<question>$question$</question>

Assistant:
"""

        POST_PROCESSING_PROMPT="""
Human: 
You are an agent tasked with providing more context to an answer that a function calling agent outputs. The function calling agent takes in a user’s question and calls the appropriate functions (a function call is equivalent to an API call) that it has been provided with in order to take actions in the real-world and gather more information to help answer the user’s question.

At times, the function calling agent produces responses that may seem confusing to the user because the user lacks context of the actions the function calling agent has taken. Here’s an example:
<example>
    The user tells the function calling agent: “Acknowledge all policy engine violations under me. My alias is jsmith, start date is 09/09/2023 and end date is 10/10/2023.”

    After calling a few API’s and gathering information, the function calling agent responds, “What is the expected date of resolution for policy violation POL-001?”

    This is problematic because the user did not see that the function calling agent called API’s due to it being hidden in the UI of our application. Thus, we need to provide the user with more context in this response. This is where you augment the response and provide more information.

    Here’s an example of how you would transform the function calling agent response into our ideal response to the user. This is the ideal final response that is produced from this specific scenario: “Based on the provided data, there are 2 policy violations that need to be acknowledged - POL-001 with high risk level created on 2023-06-01, and POL-002 with medium risk level created on 2023-06-02. What is the expected date of resolution date to acknowledge the policy violation POL-001?”
</example>

It’s important to note that the ideal answer does not expose any underlying implementation details that we are trying to conceal from the user like the actual names of the functions.

Do not ever include any API or function names or references to these names in any form within the final response you create. An example of a violation of this policy would look like this: “To update the order, I called the order management APIs to change the shoe color to black and the shoe size to 10.” The final response in this example should instead look like this: “I checked our order management system and changed the shoe color to black and the shoe size to 10.”

Now you will try creating a final response. Here’s the original user input <user_input>$question$</user_input>.

Here is the latest raw response from the function calling agent that you should translate to bengali: <latest_response>$latest_response$</latest_response>.

And here is the history of the actions the function calling agent has taken so far in this conversation: <history>$responses$</history>.

Please output your transformed response within <final_response></final_response> XML tags. 

Assistant:
        """

        config = {
            "overrideLambda": f"arn:aws:lambda:{region}:{account_id}:function:preprocess-lambda",
            "promptConfigurations": [
                {
                    "basePromptTemplate": PRE_PROCESSING_PROMPT,
                    "inferenceConfiguration": {
                        "maximumLength": 2048,
                        "stopSequences": ["Human:"],
                        "temperature": 0,
                        "topK": 1,
                        "topP": 1
                    },
                    "parserMode": "OVERRIDDEN",
                    "promptCreationMode": "OVERRIDDEN",
                    "promptState": "ENABLED",
                    "promptType": "PRE_PROCESSING"
                },
                {
                    "basePromptTemplate": ORCHESTRATION_PROMPT,
                    "inferenceConfiguration": {
                        "maximumLength": 2048,
                        "stopSequences": ["Human:"],
                        "temperature": 0,
                        "topK": 1,
                        "topP": 1
                    },
                    "parserMode": "OVERRIDDEN",
                    "promptCreationMode": "OVERRIDDEN",
                    "promptState": "ENABLED",
                    "promptType": "ORCHESTRATION"
                },
                {
                    "basePromptTemplate": POST_PROCESSING_PROMPT,
                    "inferenceConfiguration": {
                        "maximumLength": 2048,
                        "stopSequences": ["Human:"],
                        "temperature": 0,
                        "topK": 1,
                        "topP": 1
                    },
                    "parserMode": "OVERRIDDEN",
                    "promptCreationMode": "OVERRIDDEN",
                    "promptState": "ENABLED",
                    "promptType": "POST_PROCESSING"
                }
            ]
        }

      
        return config


def create_agent(region, account_id, kb_arn, kb_id):

    #create all the required policies and roles
    va_agent_role_arn = create_agent_role(region, account_id, kb_arn)
    #va_agent_role_arn = 'arn:aws:iam::722665529886:role/AmazonBedrockExecutionRoleForAgents_va'
    #print(va_agent_role_arn)

    # Create Agent
    #agent_instruction = """You are an expert customer service agent helping faculty and students to resolve their queries like accessing the grades, eligibility, login issues, powerschool access issues. You can also guide users with navigation and other assistance on their portal. If the user request for a password reset, ask for email address, name and ID which are required information before fulfilling the <user-request>, once you have all the required information, you can reset the password and provide temporary password to the user"""
    agent_instruction = """
    You are an expert financial analyst with deep understanding of reading, digesting and analyzing the Quaterly Investment Perspective (QIP) documents.
    You provide help to Client advisors to resolve their queries like answering the queris based on QIP documents accessing. 
    You can also guide users with navigation and other assistance on their portal. 
    If the user request for a password reset, ask for email address, name and ID which are required information before fulfilling the <user-request>, 
    once you have all the required information, you can reset the password and provide temporary password to the user"""

    va_agent_obj = bedrock_agent_client.create_agent(
        agentName=agent_name,
        agentResourceRoleArn=va_agent_role_arn,
        description="Virtual assistant agent with ability to answer queries based on QIP Documents.",
        idleSessionTTLInSeconds=1800,
        foundationModel= "anthropic.claude-v2",    #"anthropic.claude-3-haiku-20240307-v1:0",
        instruction=agent_instruction,
        promptOverrideConfiguration=get_prompt_override_config(region,account_id)
    )
    print("Agent created successfully")
    #print(va_agent_obj)
    va_agent_id = va_agent_obj['agent']['agentId']
    create_action_group(region, account_id, va_agent_id, kb_id)

    #prepare agent
    bedrock_agent_client.prepare_agent(
        agentId=va_agent_id
    )
    # nosemgrep
    time.sleep(25)
    #create alias once agent is prepared
    create_alias(va_agent_id)

    print("Agent prepared and new alias created")
    return va_agent_id

def create_alias(va_agent_id):
    #create alias
    alias_name = "latest"
    alias_description = "Alias for latest version of the agent"
    alias_arn = bedrock_agent_client.create_agent_alias(
        agentId=va_agent_id,
        agentAliasName=alias_name,
        description=alias_description
    )
    #print(alias_arn)
    return alias_arn
    




def create_action_group(region, account_id, va_agent_id, kb_id):
    suffix = f"{region}-{account_id}"
    lambda_role_name = f'{agent_name}-lambda-role-{suffix}'
    lambda_code_path = "lambda_function.py"
    lambda_name = f'{agent_name}-{suffix}'
    # Commented by Anand - Circumvent the issue while reading it from S3 Bucket
    #bucket_name = f'{agent_name}-{suffix}'
    #schema_key = f'{agent_name}-schema.json'

    try:
        print("Creating Agent action group")
        # Pause to make sure agent is created & in available state
        # nosemgrep
        time.sleep(15)
        assume_role_policy_document = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": "bedrock:InvokeModel",
                    "Principal": {
                        "Service": "lambda.amazonaws.com"
                    },
                    "Action": "sts:AssumeRole"
                }
            ]
        }

        assume_role_policy_document_json = json.dumps(assume_role_policy_document)

        lambda_iam_role = iam_client.create_role(
            RoleName=lambda_role_name,
            AssumeRolePolicyDocument=assume_role_policy_document_json
        )

        # Pause to make sure role is created
        # nosemgrep
        time.sleep(10)
    except:
        lambda_iam_role = iam_client.get_role(RoleName=lambda_role_name)

    iam_client.attach_role_policy(
        RoleName=lambda_role_name,
        PolicyArn='arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'
    )
    # package lambda function for the agent action group
    # Package up the lambda function code
    s = BytesIO()
    z = zipfile.ZipFile(s, 'w')
    z.write(lambda_code_path)
    z.close()
    zip_content = s.getvalue()

    # Create Lambda Function
    lambda_function = lambda_client.create_function(
        FunctionName=lambda_name,
        Runtime='python3.12',
        Timeout=180,
        Role=lambda_iam_role['Role']['Arn'],
        Code={'ZipFile': zip_content},
        Handler='lambda_function.lambda_handler'
    )

    agent_action_group_response = bedrock_agent_client.create_agent_action_group(
        agentId=va_agent_id,
        agentVersion='DRAFT',
        actionGroupExecutor={
            'lambda': lambda_function['FunctionArn']
        },
        actionGroupName='PasswordResetActionGroup',
        apiSchema={
            'payload' : json.dumps(schema_json_string)
            # Commented below by Anand - Circumvent the S3 Read issue
            #'s3': {
            #    's3BucketName': bucket_name,
            #    's3ObjectKey': schema_key
            #}
        },
        description='Actions for password reset'
    )

    # Add required permissions to Lambda
    lm_response = lambda_client.add_permission(
        FunctionName=lambda_name,
        StatementId='allow_bedrock',
        Action='lambda:InvokeFunction',
        Principal='bedrock.amazonaws.com',
        SourceArn=f"arn:aws:bedrock:{region}:{account_id}:agent/{va_agent_id}",
    )

    # Add KB to agent
    agent_kb_description = bedrock_agent_client.associate_agent_knowledge_base(
        agentId=va_agent_id,
        agentVersion='DRAFT',
        description=f'Answer queries from prompts. Double check each source you reference from the Quaterly Investment Perspective (QIP) docuemnt to provide a good response. Ask if anything else is needed.',
        knowledgeBaseId=kb_id 
    )


def create_agent_role(region, account_id,knowledge_base_arn ):

    suffix = f"{region}-{account_id}"
    agent_name = "virtual-assistant-agent-0402"
    bucket_name = f'{agent_name}-{suffix}'
    bucket_name = f'{agent_name}-{suffix}'
    schema_key = f'{agent_name}-schema.json'
    schema_arn = f'arn:aws:s3:::{bucket_name}/{schema_key}'
    
    va_agent_bedrock_allow_policy_name = f"va-bedrock-allow-01-{suffix}"
    va_agent_s3_allow_policy_name = f"va-s3-allow-01-{suffix}"
    va_agent_kb_allow_policy_name = f"va-kb-allow-01-{suffix}"
    
    agent_role_name = f'AmazonBedrockExecutionRoleForAgents01_va'
   
    va_agent_bedrock_allow_policy_statement = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AmazonBedrockAgentBedrockFoundationModelPolicy",
                "Effect": "Allow",
                "Action": [
                    "bedrock:InvokeModel",
                ],
                "Resource": [
                    "arn:aws:bedrock:us-east-1::foundation-model/*"
                ]
            }
        ]
    }

    bedrock_policy_json = json.dumps(va_agent_bedrock_allow_policy_statement)

    va_agent_bedrock_policy = iam_client.create_policy(
        PolicyName=va_agent_bedrock_allow_policy_name,
        PolicyDocument=bedrock_policy_json
    )

    bedrock_agent_s3_allow_policy_statement = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AllowAgentAccessOpenAPISchema",
                "Effect": "Allow",
                "Action": ["s3:GetObject"],
                "Resource": [
                    schema_arn
                ]
            }
        ]
    }


    bedrock_agent_s3_json = json.dumps(bedrock_agent_s3_allow_policy_statement)
    va_agent_s3_schema_policy = iam_client.create_policy(
        PolicyName=va_agent_s3_allow_policy_name,
        Description=f"Policy to allow invoke Lambda that was provisioned for it.",
        PolicyDocument=bedrock_agent_s3_json
    )

    va_agent_kb_retrival_policy_statement = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "bedrock:Retrieve"
                ],
                "Resource": [
                    knowledge_base_arn
                ]
            }
        ]
    }
    va_bedrock_agent_kb_json = json.dumps(va_agent_kb_retrival_policy_statement)

    va_agent_kb_schema_policy = iam_client.create_policy(
        PolicyName=va_agent_kb_allow_policy_name,
        Description=f"Policy to allow agent to retrieve documents from knowledge base.",
        PolicyDocument=va_bedrock_agent_kb_json
    )

    # Create IAM Role for the agent and attach IAM policies
    assume_role_policy_document = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {
                "Service": "bedrock.amazonaws.com"
            },
            "Action": "sts:AssumeRole"
        }]
    }

    assume_role_policy_document_json = json.dumps(assume_role_policy_document)
    va_agent_role = iam_client.create_role(
        RoleName=agent_role_name,
        AssumeRolePolicyDocument=assume_role_policy_document_json
    )
    # nosemgrep
    time.sleep(15)

    iam_client.attach_role_policy(
        RoleName=agent_role_name,
        PolicyArn=va_agent_bedrock_policy['Policy']['Arn']
    )

    iam_client.attach_role_policy(
        RoleName=agent_role_name,
        PolicyArn=va_agent_s3_schema_policy['Policy']['Arn']
    )

    iam_client.attach_role_policy(
        RoleName=agent_role_name,
        PolicyArn=va_agent_kb_schema_policy['Policy']['Arn']
    )

    

    return va_agent_role['Role']['Arn']