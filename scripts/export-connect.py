"""Export Connect definitions without changing AWS resources or loading .env as code."""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, default=root / 'config/sandbox.env')
    parser.add_argument('--practice', required=True, help='Existing top-level practice folder, for example retail-banking-cx')
    parser.add_argument('--output', type=Path, help='Optional snapshot directory inside the selected practice')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*', args.practice):
        parser.error('--practice must be a lowercase folder name with optional hyphens')
    practice = (root / args.practice).resolve()
    if practice.parent != root.resolve() or not practice.is_dir() or args.practice in ('config', 'scripts', 'docs'):
        parser.error('--practice must identify an existing top-level practice folder')
    destination = (args.output or practice / 'connect-exports').resolve()
    if not destination.is_relative_to(practice):
        parser.error('--output must stay inside the selected practice')
    config = {}
    for line in args.env_file.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep:
            raise ValueError('Invalid environment file entry')
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in '\"\'':
            value = value[1:-1]
        config[key.strip()] = value
    required = ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN',
                'AWS_DEFAULT_REGION', 'CONNECT_INSTANCE_ID')
    for key in required:
        if not config.get(key):
            raise ValueError(f'Missing {key}')
    session = boto3.Session(
        aws_access_key_id=config['AWS_ACCESS_KEY_ID'],
        aws_secret_access_key=config['AWS_SECRET_ACCESS_KEY'],
        aws_session_token=config['AWS_SESSION_TOKEN'],
        region_name=config['AWS_DEFAULT_REGION'])
    identity = session.client('sts').get_caller_identity()
    connect = session.client('connect')
    instance_id = config['CONNECT_INSTANCE_ID']
    instance = connect.describe_instance(InstanceId=instance_id)['Instance']
    print(f"Connected: account={identity['Account']}, region={session.region_name}, "
          f"instance={instance.get('InstanceAlias', instance_id)}", flush=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = destination / stamp
    output.mkdir(parents=True, exist_ok=False)
    manifest = {'exportedAt': stamp, 'practice': args.practice, 'region': session.region_name,
                'accountId': identity['Account'], 'instanceId': instance_id,
                'counts': {}, 'errors': []}

    def save(path, data):
        target = output / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2, default=str) + '\n', encoding='utf-8')

    def collect(operation, result_key, **kwargs):
        items = []
        while True:
            response = getattr(connect, operation)(InstanceId=instance_id, **kwargs)
            items.extend(response.get(result_key, []))
            if not response.get('NextToken'):
                return items
            kwargs['NextToken'] = response['NextToken']

    def error(label, exc):
        detail = exc.response['Error']
        manifest['errors'].append({'resource': label, 'code': detail['Code'],
                                   'message': detail['Message']})
        print(f"Incomplete: {label}: {detail['Code']}", flush=True)

    save('instance.json', instance)
    resources = [
        ('flows', 'list_contact_flows', 'ContactFlowSummaryList', 'describe_contact_flow', 'ContactFlowId', 'ContactFlow'),
        ('flow-modules', 'list_contact_flow_modules', 'ContactFlowModulesSummaryList', 'describe_contact_flow_module', 'ContactFlowModuleId', 'ContactFlowModule'),
        ('hours-of-operation', 'list_hours_of_operations', 'HoursOfOperationSummaryList', 'describe_hours_of_operation', 'HoursOfOperationId', 'HoursOfOperation'),
        ('queues', 'list_queues', 'QueueSummaryList', 'describe_queue', 'QueueId', 'Queue'),
        ('routing-profiles', 'list_routing_profiles', 'RoutingProfileSummaryList', 'describe_routing_profile', 'RoutingProfileId', 'RoutingProfile'),
        ('quick-connects', 'list_quick_connects', 'QuickConnectSummaryList', 'describe_quick_connect', 'QuickConnectId', 'QuickConnect'),
    ]
    for folder, listing, result_key, describe, id_key, detail_key in resources:
        try:
            options = {'QueueTypes': ['STANDARD']} if folder == 'queues' else {}
            items = collect(listing, result_key, **options)
            save(f'{folder}/index.json', items)
            count = 0
            for item in items:
                try:
                    detail = getattr(connect, describe)(InstanceId=instance_id, **{id_key: item['Id']})[detail_key]
                    if folder in ('flows', 'flow-modules') and isinstance(detail.get('Content'), str):
                        detail['Content'] = json.loads(detail['Content'])
                    if folder == 'routing-profiles':
                        detail['QueueConfigs'] = collect('list_routing_profile_queues', 'RoutingProfileQueueConfigSummaryList', RoutingProfileId=item['Id'])
                    if folder == 'queues':
                        detail['QuickConnects'] = collect('list_queue_quick_connects', 'QuickConnectSummaryList', QueueId=item['Id'])
                    save(f"{folder}/{item['Id']}.json", detail)
                    count += 1
                except ClientError as exc:
                    error(f"{folder}/{item['Id']}", exc)
            manifest['counts'][folder] = count
            print(f'{folder}: {count}/{len(items)} exported', flush=True)
        except ClientError as exc:
            error(folder, exc)
    for label, operation, key in [
        ('prompts', 'list_prompts', 'PromptSummaryList'),
        ('lambda-functions', 'list_lambda_functions', 'LambdaFunctions'),
        ('lex-bots', 'list_lex_bots', 'LexBots'),
        ('integrations', 'list_integration_associations', 'IntegrationAssociationSummaryList'),
        ('instance-attributes', 'list_instance_attributes', 'Attributes')]:
        try:
            items = collect(operation, key)
            save(f'{label}.json', items)
            manifest['counts'][label] = len(items)
        except ClientError as exc:
            error(label, exc)
    save('manifest.json', manifest)
    print(f'Export saved: {output}', flush=True)
    if manifest['errors']:
        raise SystemExit('Export completed with gaps; inspect manifest.json.')


if __name__ == '__main__':
    main()
