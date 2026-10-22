"""Create and publish three isolated Connect practice flows. No existing users are reassigned."""
import argparse
import copy
import importlib.util
import io
import json
import uuid
import zipfile
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('backend_deploy', ROOT / 'scripts/deploy-readonly.py')
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


def collect(client, operation, key, **kwargs):
    items = []
    while True:
        result = getattr(client, operation)(**kwargs)
        items.extend(result.get(key, []))
        if not result.get('NextToken'):
            return items
        kwargs['NextToken'] = result['NextToken']


def uid(name):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'anybank-practice/' + name))


def build_flow(name, operation, queue_arn, lambda_arn, waiting_arn):
    nodes = []
    metadata = {}
    def add(label, kind, parameters, next_label=None, errors=True):
        transitions = {}
        if next_label:
            transitions['NextAction'] = uid(next_label)
        if errors:
            transitions['Errors'] = [{'NextAction': uid('error'), 'ErrorType': 'NoMatchingError'}]
        node = {'Identifier': uid(label), 'Type': kind, 'Parameters': parameters, 'Transitions': transitions}
        nodes.append(node)
        metadata[node['Identifier']] = {'position': {'x': len(nodes) * 270, 'y': 200 if label not in ('error', 'end') else 550}, 'isFriendlyName': True, 'friendlyName': label}
        return node
    add('logging', 'UpdateFlowLoggingBehavior', {'FlowLoggingBehavior': 'Enabled'}, 'welcome', errors=False)
    add('welcome', 'MessageParticipant', {'Text': 'Welcome to the AnyBank learning demo. We will use fictional customer CUST-12345.'}, 'lookup')
    add('lookup', 'InvokeLambdaFunction', {'LambdaFunctionARN': lambda_arn, 'InvocationTimeLimitSeconds': '8', 'InvocationType': 'SYNCHRONOUS', 'LambdaInvocationAttributes': {'customerId': 'CUST-12345', 'operation': operation}, 'ResponseValidation': {'ResponseType': 'STRING_MAP'}}, 'result')
    add('result', 'MessageParticipant', {'Text': '$.External.Message'}, 'handoff')
    metadata[uid('result')]['parameters'] = {'Text': {'useDynamic': True}}
    add('handoff', 'MessageParticipant', {'Text': 'The automated lookup is complete. Next, you will enter the ' + ('general service' if operation == 'accounts' else 'cards support') + ' queue to wait for a human agent.'}, 'queue-flow')
    add('queue-flow', 'UpdateContactEventHooks', {'EventHooks': {'CustomerQueue': waiting_arn}}, 'queue')
    add('queue', 'UpdateContactTargetQueue', {'QueueId': queue_arn}, 'transfer')
    transfer = add('transfer', 'TransferContactToQueue', {}, 'end')
    transfer['Transitions']['Errors'].insert(0, {'NextAction': uid('error'), 'ErrorType': 'QueueAtCapacity'})
    add('error', 'MessageParticipant', {'Text': 'The demo could not complete this step. Please check the flow logs and the queue configuration.'}, 'end')
    add('end', 'DisconnectParticipant', {}, errors=False)
    return {'Version': '2019-10-30', 'StartAction': uid('logging'), 'Metadata': {'name': name, 'description': 'AnyBank visible learning exercise', 'type': 'contactFlow', 'entryPointPosition': {'x': 0, 'y': 200}, 'ActionMetadata': metadata}, 'Actions': nodes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    cfg = backend.read_env(ROOT.parent / 'config/sandbox.env')
    session = boto3.Session(aws_access_key_id=cfg['AWS_ACCESS_KEY_ID'], aws_secret_access_key=cfg['AWS_SECRET_ACCESS_KEY'], aws_session_token=cfg['AWS_SESSION_TOKEN'], region_name=cfg['AWS_DEFAULT_REGION'])
    c, lam = session.client('connect'), session.client('lambda')
    instance_id = cfg['CONNECT_INSTANCE_ID']
    instance = c.describe_instance(InstanceId=instance_id)['Instance']
    account = session.client('sts').get_caller_identity()['Account']
    print(f"Instance: {instance['InstanceAlias']} ({instance_id}); account: {account}", flush=True)
    flows = collect(c, 'list_contact_flows', 'ContactFlowSummaryList', InstanceId=instance_id)
    source = next(f for f in flows if f['Name'] == 'MainFlow')
    source_content = json.loads(c.describe_contact_flow(InstanceId=instance_id, ContactFlowId=source['Id'])['ContactFlow']['Content'])
    if not any(a['Type'] == 'ConnectParticipantWithAgenticCX' for a in source_content['Actions']):
        raise ValueError('MainFlow has no ACXD application to reuse')
    waiting = next(f for f in flows if f['Name'] == 'Default customer queue')
    print('Plan: two queues, one 24/7 schedule, one routing profile, one read-only Lambda adapter, three published flows.', flush=True)
    if not args.apply:
        print('Inspection only. Add --apply to publish. Existing users and MainFlow stay unchanged.', flush=True)
        return
    hours = collect(c, 'list_hours_of_operations', 'HoursOfOperationSummaryList', InstanceId=instance_id)
    schedule = next((h for h in hours if h['Name'] == 'AnyBank-Demo-24x7'), None)
    if not schedule:
        schedule = c.create_hours_of_operation(InstanceId=instance_id, Name='AnyBank-Demo-24x7', Description='Always open for AnyBank chat exercises', TimeZone='America/Bogota', Config=[{'Day': day, 'StartTime': {'Hours': 0, 'Minutes': 0}, 'EndTime': {'Hours': 23, 'Minutes': 59}} for day in ['MONDAY','TUESDAY','WEDNESDAY','THURSDAY','FRIDAY','SATURDAY','SUNDAY']])
        schedule['Id'] = schedule['HoursOfOperationId']
        print('Created schedule AnyBank-Demo-24x7', flush=True)
    queues = collect(c, 'list_queues', 'QueueSummaryList', InstanceId=instance_id, QueueTypes=['STANDARD'])
    queue_map = {}
    for name in ['AnyBank-General-Service', 'AnyBank-Cards-Support']:
        queue = next((q for q in queues if q['Name'] == name), None)
        if not queue:
            result = c.create_queue(InstanceId=instance_id, Name=name, Description='AnyBank training queue', HoursOfOperationId=schedule['Id'])
            queue = {'Id': result['QueueId'], 'Arn': result['QueueArn'], 'Name': name}
            print('Created queue ' + name, flush=True)
        queue_map[name] = queue
    profiles = collect(c, 'list_routing_profiles', 'RoutingProfileSummaryList', InstanceId=instance_id)
    profile = next((p for p in profiles if p['Name'] == 'AnyBank-Demo-Agents'), None)
    if not profile:
        result = c.create_routing_profile(InstanceId=instance_id, Name='AnyBank-Demo-Agents', Description='Accept AnyBank general and cards demo contacts', DefaultOutboundQueueId=queue_map['AnyBank-General-Service']['Id'], MediaConcurrencies=[{'Channel':'VOICE','Concurrency':1},{'Channel':'CHAT','Concurrency':2}], QueueConfigs=[{'QueueReference': {'QueueId': q['Id'], 'Channel': channel}, 'Priority': 1, 'Delay': 0} for q in queue_map.values() for channel in ['VOICE','CHAT']])
        profile = {'Id': result['RoutingProfileId'], 'Arn': result['RoutingProfileArn'], 'Name': 'AnyBank-Demo-Agents'}
        print('Created routing profile AnyBank-Demo-Agents; no users reassigned', flush=True)
    function_name = 'anybank-connect-demo'
    function_arn = f'arn:aws:lambda:{session.region_name}:{account}:function:{function_name}'
    code = io.BytesIO()
    with zipfile.ZipFile(code, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.write(ROOT / 'backend/connect-demo.cjs', 'connect-demo.cjs')
    environment = {'Variables': {'TABLE_NAME': 'anybank-readonly-state', 'CONNECT_INSTANCE_ARN': instance['Arn']}}
    existing = backend.optional(lam.get_function_configuration, ['ResourceNotFoundException'], FunctionName=function_name)
    if not existing:
        lam.create_function(FunctionName=function_name, Runtime='nodejs22.x', Role=f'arn:aws:iam::{account}:role/lambdaDynamoRole', Handler='connect-demo.handler', Code={'ZipFile':code.getvalue()}, Timeout=8, MemorySize=256, Environment=environment)
        lam.get_waiter('function_active_v2').wait(FunctionName=function_name)
    else:
        if existing['Handler'] != 'connect-demo.handler':
            raise ValueError('Existing demo function has an unexpected handler')
        lam.update_function_code(FunctionName=function_name, ZipFile=code.getvalue())
        lam.get_waiter('function_updated_v2').wait(FunctionName=function_name)
        lam.update_function_configuration(FunctionName=function_name, Environment=environment)
        lam.get_waiter('function_updated_v2').wait(FunctionName=function_name)
    try:
        lam.add_permission(FunctionName=function_name, StatementId='AnyBankConnectInvoke', Action='lambda:InvokeFunction', Principal='connect.amazonaws.com', SourceArn=instance['Arn'], SourceAccount=account)
    except ClientError as error:
        if error.response['Error']['Code'] != 'ResourceConflictException':
            raise
    associated = collect(c, 'list_lambda_functions', 'LambdaFunctions', InstanceId=instance_id)
    if function_arn not in associated:
        c.associate_lambda_function(InstanceId=instance_id, FunctionArn=function_arn)
    print('Associated read-only Lambda adapter with Connect', flush=True)
    for operation in ['accounts','cards']:
        event = {'Details': {'ContactData': {'InstanceARN':instance['Arn']}, 'Parameters': {'customerId':'CUST-12345','operation':operation}}}
        result = lam.invoke(FunctionName=function_name, Payload=json.dumps(event).encode())
        payload = json.loads(result['Payload'].read())
        if result.get('FunctionError') or not payload.get('Message'):
            raise ValueError('Demo Lambda lookup failed: ' + json.dumps(payload))
        print('Verified lookup: ' + payload['Message'], flush=True)
    definitions = {}
    for name, operation, queue_name in [('AnyBank-01-Balance','accounts','AnyBank-General-Service'),('AnyBank-02-Cards','cards','AnyBank-Cards-Support')]:
        definitions[name] = build_flow(name, operation, queue_map[queue_name]['Arn'], function_arn, waiting['Arn'])
    ai = copy.deepcopy(source_content)
    ai.setdefault('Metadata', {})['name'] = 'AnyBank-03-AI'
    for action in ai['Actions']:
        if action['Type'] == 'UpdateContactTargetQueue':
            action['Parameters'] = {'QueueId': queue_map['AnyBank-General-Service']['Arn']}
        if action['Type'] == 'ConnectParticipantWithAgenticCX':
            action['Parameters']['AgentConfiguration'].setdefault('ContextVariables', {}).pop('customerId', None)
            aid = action['Identifier']
            ai['Metadata'].setdefault('ActionMetadata', {}).setdefault(aid, {}).setdefault('parameters', {}).setdefault('AgentConfiguration', {}).setdefault('ContextVariables', {}).pop('customerId', None)
    definitions['AnyBank-03-AI'] = ai
    manifest = {'instanceId': instance_id, 'queues':queue_map, 'routingProfile':profile, 'lambdaArn':function_arn, 'flows':{}}
    build = ROOT / '.build'; build.mkdir(exist_ok=True)
    for name, content in definitions.items():
        (build / (name+'.json')).write_text(json.dumps(content,indent=2))
        old = next((f for f in flows if f['Name'] == name), None)
        if old:
            c.update_contact_flow_content(InstanceId=instance_id, ContactFlowId=old['Id'], Content=json.dumps(content))
            flow_id = old['Id']
        else:
            result = c.create_contact_flow(InstanceId=instance_id, Name=name, Type='CONTACT_FLOW', Description='AnyBank learning practice; isolated from MainFlow', Content=json.dumps(content), Status='PUBLISHED')
            flow_id = result['ContactFlowId']
        published = c.describe_contact_flow(InstanceId=instance_id, ContactFlowId=flow_id)['ContactFlow']
        manifest['flows'][name] = {'Id':flow_id,'Arn':published['Arn'],'Status':published.get('Status')}
        print('Published ' + name + ': ' + flow_id + ' (' + str(published.get('Status')) + ')', flush=True)
        (build/'connect-practice.json').write_text(json.dumps(manifest,indent=2))
    print('Done. Select the demo routing profile manually on your test agent, then test each published flow using Test chat.', flush=True)


if __name__ == '__main__':
    main()
