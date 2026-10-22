"""Deploy the bounded, read-only AnyBank sandbox backend. Default: inspect only."""
import argparse
import io
import json
import secrets
import subprocess
import time
import zipfile
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[1]
FUNCTION = 'anybank-readonly-api'
TABLE = 'anybank-readonly-state'
ROLE = 'lambdaDynamoRole'
POLICIES = [
    'arn:aws:iam::aws:policy/AmazonDynamoDBReadOnlyAccess',
    'arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole',
]


def read_env(path):
    values = {}
    for raw in path.read_text(encoding='utf-8-sig').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep:
            raise ValueError('Invalid environment file entry')
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def optional(call, missing, **kwargs):
    try:
        return call(**kwargs)
    except ClientError as error:
        if error.response['Error']['Code'] in missing:
            return None
        raise


def package():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in ['core.cjs', 'readonly.cjs']:
            archive.write(ROOT / 'backend' / name, name)
    return buffer.getvalue()


def validate_existing_role(role, boundary):
    if role.get('PermissionsBoundary', {}).get('PermissionsBoundaryArn') != boundary:
        raise ValueError('Existing role does not have the expected workshop boundary; refusing to change it')
    statements = role['AssumeRolePolicyDocument'].get('Statement', [])
    if not any(s.get('Effect') == 'Allow' and 'lambda.amazonaws.com' in
               ([s.get('Principal', {}).get('Service')] if isinstance(s.get('Principal', {}).get('Service'), str)
                else s.get('Principal', {}).get('Service', [])) for s in statements):
        raise ValueError('Existing role does not trust Lambda; refusing to change its trust')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, default=ROOT.parent / 'config' / 'sandbox.env')
    parser.add_argument('--apply', action='store_true', help='Create or update resources; otherwise inspect only')
    args = parser.parse_args()
    cfg = read_env(args.env_file)
    required = ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN', 'AWS_DEFAULT_REGION']
    for name in required:
        if not cfg.get(name):
            raise ValueError(f'Missing {name}')
    session = boto3.Session(aws_access_key_id=cfg['AWS_ACCESS_KEY_ID'],
                            aws_secret_access_key=cfg['AWS_SECRET_ACCESS_KEY'],
                            aws_session_token=cfg['AWS_SESSION_TOKEN'], region_name=cfg['AWS_DEFAULT_REGION'])
    identity = session.client('sts').get_caller_identity()
    account = identity['Account']
    if session.region_name != 'us-east-1':
        raise ValueError('This workshop deployment is restricted to us-east-1')
    print(f"Account: {account}; region: {session.region_name}; identity: {identity['Arn']}", flush=True)
    boundary = f'arn:aws:iam::{account}:policy/WorkshopLambdaBoundary'
    role_arn = f'arn:aws:iam::{account}:role/{ROLE}'
    iam, db, lam = session.client('iam'), session.client('dynamodb'), session.client('lambda')
    iam.get_policy(PolicyArn=boundary)  # Mandatory prerequisite; never create or alter the boundary.
    role_result = optional(iam.get_role, ['NoSuchEntity'], RoleName=ROLE)
    if role_result:
        validate_existing_role(role_result['Role'], boundary)
    table_result = optional(db.describe_table, ['ResourceNotFoundException'], TableName=TABLE)
    if table_result and table_result['Table']['KeySchema'] != [{'AttributeName': 'pk', 'KeyType': 'HASH'}]:
        raise ValueError('Existing table schema differs; refusing to modify it')
    function = optional(lam.get_function_configuration, ['ResourceNotFoundException'], FunctionName=FUNCTION)
    if function and (function['Role'] != role_arn or function['Handler'] != 'readonly.handler'):
        raise ValueError('Existing function configuration differs; refusing to replace it')
    for label, exists in [('Role', role_result), ('Table', table_result), ('Function', function)]:
        print(f'{label}: {"exists" if exists else "will be created"}', flush=True)
    if not args.apply:
        print('Inspection only. No AWS resources changed. Add --apply to deploy.', flush=True)
        return
    # Prepare fictional data before performing any AWS mutation.
    state = subprocess.check_output(['node', '-e', "process.stdout.write(JSON.stringify(require('./backend/core.cjs').seed()))"], cwd=ROOT, text=True)
    code = package()
    if not role_result:
        trust = json.loads((ROOT / 'lambda-trust.json').read_text(encoding='utf-8-sig'))
        iam.create_role(RoleName=ROLE, AssumeRolePolicyDocument=json.dumps(trust), PermissionsBoundary=boundary)
        print('Created bounded Lambda role', flush=True)
    attached = {p['PolicyArn'] for page in iam.get_paginator('list_attached_role_policies').paginate(RoleName=ROLE) for p in page['AttachedPolicies']}
    for policy in POLICIES:
        if policy not in attached:
            iam.attach_role_policy(RoleName=ROLE, PolicyArn=policy)
    if not table_result:
        db.create_table(TableName=TABLE, BillingMode='PAY_PER_REQUEST',
                        AttributeDefinitions=[{'AttributeName': 'pk', 'AttributeType': 'S'}],
                        KeySchema=[{'AttributeName': 'pk', 'KeyType': 'HASH'}])
    db.get_waiter('table_exists').wait(TableName=TABLE, WaiterConfig={'Delay': 2, 'MaxAttempts': 60})
    try:
        db.put_item(TableName=TABLE, Item={'pk': {'S': 'STATE'}, 'payload': {'S': state}}, ConditionExpression='attribute_not_exists(pk)')
        print('Initialized fictional data', flush=True)
    except ClientError as error:
        if error.response['Error']['Code'] != 'ConditionalCheckFailedException':
            raise
        stored = db.get_item(TableName=TABLE, Key={'pk': {'S': 'STATE'}}, ConsistentRead=True).get('Item', {})
        if not stored.get('payload', {}).get('S'):
            raise ValueError('Existing state has an unexpected format; left unchanged')
        print('Preserved existing data', flush=True)
    key = function.get('Environment', {}).get('Variables', {}).get('API_KEY') if function else None
    key = key or secrets.token_urlsafe(32)
    environment = {'Variables': {'TABLE_NAME': TABLE, 'API_KEY': key}}
    if function:
        lam.get_waiter('function_updated_v2').wait(FunctionName=FUNCTION)
        lam.update_function_code(FunctionName=FUNCTION, ZipFile=code)
        lam.get_waiter('function_updated_v2').wait(FunctionName=FUNCTION)
        lam.update_function_configuration(FunctionName=FUNCTION, Runtime='nodejs22.x', Handler='readonly.handler',
                                           Role=role_arn, Environment=environment, Timeout=15, MemorySize=256)
        lam.get_waiter('function_updated_v2').wait(FunctionName=FUNCTION)
    else:
        for attempt in range(10):
            try:
                lam.create_function(FunctionName=FUNCTION, Runtime='nodejs22.x', Role=role_arn,
                                    Handler='readonly.handler', Code={'ZipFile': code}, Environment=environment,
                                    Timeout=15, MemorySize=256)
                break
            except ClientError as error:
                if error.response['Error']['Code'] != 'InvalidParameterValueException' or 'cannot be assumed' not in str(error) or attempt == 9:
                    raise
                time.sleep(3)
        lam.get_waiter('function_active_v2').wait(FunctionName=FUNCTION)
    url = optional(lam.get_function_url_config, ['ResourceNotFoundException'], FunctionName=FUNCTION)
    if url and url['AuthType'] != 'NONE':
        raise ValueError('Existing Function URL requires different authentication; left unchanged')
    if not url:
        url = lam.create_function_url_config(FunctionName=FUNCTION, AuthType='NONE')
    permissions = [
        {'StatementId': 'AnyBankFunctionUrl', 'Action': 'lambda:InvokeFunctionUrl', 'FunctionUrlAuthType': 'NONE'},
        {'StatementId': 'AnyBankInvokeViaUrl', 'Action': 'lambda:InvokeFunction', 'InvokedViaFunctionUrl': True},
    ]
    existing_policy = optional(lam.get_policy, ['ResourceNotFoundException'], FunctionName=FUNCTION)
    statements = json.loads(existing_policy['Policy']).get('Statement', []) if existing_policy else []
    for permission in permissions:
        existing = next((s for s in statements if s['Sid'] == permission['StatementId']), None)
        if existing:
            expected_condition = {'StringEquals': {'lambda:FunctionUrlAuthType': 'NONE'}} if 'FunctionUrlAuthType' in permission else {'Bool': {'lambda:InvokedViaFunctionUrl': 'true'}}
            principal = existing.get('Principal')
            if existing.get('Effect') != 'Allow' or existing.get('Action') != permission['Action'] or principal not in ('*', {'AWS': '*'}) or existing.get('Condition') != expected_condition:
                raise ValueError('Existing URL permission differs; refusing to replace it')
        else:
            lam.add_permission(FunctionName=FUNCTION, Principal='*', **permission)
    base_url = url['FunctionUrl'].rstrip('/')
    (ROOT / 'readonly.env').write_text(f'API_URL_Base={base_url}\nAPI_Key={key}\n')
    print(f'Read-only endpoint: {base_url}', flush=True)
    print('Secret values saved to ignored retail-banking-cx/readonly.env. Run scripts/verify-readonly.py next.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except ClientError as error:
        print(f"AWS error: {error.response['Error']['Code']}: {error.response['Error']['Message']}", flush=True)
        raise SystemExit(1)
