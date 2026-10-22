"""Read-only ACXD workspace snapshot. Secret values and credentials are never exported."""
import argparse
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


class ApiError(Exception):
    def __init__(self, status):
        self.status = status
        super().__init__(f'ACXD HTTP {status}')


def read_env(path):
    values = {}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        key, separator, value = line.strip().partition('=')
        if not separator or key.startswith('#'):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


class Client:
    def __init__(self, region, workspace, api_key):
        if not re.fullmatch(r'[a-z]{2}-[a-z]+-\d', region):
            raise ValueError('Invalid AWS region')
        self.base = f'https://api.acxd.connect.{region}.amazonaws.com'
        self.headers = {'x-api-key': api_key, 'x-workspace-id': workspace, 'Accept': 'application/json'}

    def get(self, path, query=None):
        url = self.base + '/sdk/' + path
        if query:
            url += '?' + urllib.parse.urlencode(query)
        for attempt in range(4):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=self.headers), timeout=30) as response:
                    return json.load(response)
            except urllib.error.HTTPError as error:
                if error.code in (429, 500, 502, 503) and attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                raise ApiError(error.code) from None

    def items(self, path):
        items, token, seen = [], None, set()
        while True:
            page = self.get(path, {'nextToken': token} if token else None)
            items.extend(page['items'])
            token = page.get('nextToken')
            if not token:
                return items
            if token in seen:
                raise ValueError('Repeated pagination token')
            seen.add(token)


def sanitize(value, known_secrets):
    """Keep symbolic secret references; strip secret fields and literal auth headers."""
    if isinstance(value, list):
        return [sanitize(item, known_secrets) for item in value]
    if isinstance(value, dict):
        result = {}
        header = str(value.get('key', value.get('name', ''))).lower()
        for key, item in value.items():
            sensitive = key.lower() in {'secretvalue', 'apikey', 'api_key', 'password', 'authorization', 'cookie', 'acxd_api_key', 'accesstoken', 'refreshtoken'}
            header_value = key == 'value' and header in {'x-api-key', 'authorization', 'cookie'}
            symbolic = isinstance(item, str) and re.fullmatch(r'\{[^{}]+\}', item)
            result[key] = '[REDACTED]' if (sensitive or header_value) and not symbolic else sanitize(item, known_secrets)
        return result
    if isinstance(value, str):
        for secret in known_secrets:
            if len(secret) >= 8:
                value = value.replace(secret, '[REDACTED]')
    return value


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--practice', required=True)
    parser.add_argument('--workspace-id', help='Workspace UUID from the ACXD browser URL')
    parser.add_argument('--env-file', type=Path, default=root / 'config/sandbox.env')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*', args.practice):
        parser.error('Invalid practice folder name')
    practice = (root / args.practice).resolve()
    if practice.parent != root.resolve() or not practice.is_dir() or args.practice in {'config', 'scripts', 'docs'}:
        parser.error('Select an existing top-level practice folder')
    cfg = read_env(args.env_file)
    workspace = args.workspace_id or cfg.get('ACXD_WORKSPACE_ID')
    if not workspace or not re.fullmatch(r'[0-9a-fA-F-]{36}', workspace):
        parser.error('Set --workspace-id or ACXD_WORKSPACE_ID to the workspace UUID')
    if not cfg.get('ACXD_API_KEY'):
        parser.error('Missing ACXD_API_KEY in local environment file')
    client = Client(cfg['AWS_DEFAULT_REGION'], workspace, cfg['ACXD_API_KEY'])
    # Validate access before creating the output folder.
    applications = client.items('applications')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = practice / 'acxd-exports' / stamp
    output.mkdir(parents=True, exist_ok=False)
    secrets = [v for k, v in cfg.items() if any(word in k for word in ['KEY', 'TOKEN', 'PASSWORD']) and v]
    local_backend = practice / 'readonly.env'
    if local_backend.exists():
        secrets.extend(v for k, v in read_env(local_backend).items() if 'Key' in k and v)
    manifest = {'exportedAt': stamp, 'workspaceId': workspace, 'region': cfg['AWS_DEFAULT_REGION'], 'practice': args.practice, 'secretValuesIncluded': False, 'counts': {}, 'errors': [], 'limitations': ['Source definitions and build/deployment metadata; not a tested automatic restore.', 'Secret values, conversations, documents binaries, users, permissions, and analytics history are excluded.', 'New workspace/server-assigned IDs and Connect application aliases must be remapped on restore.']}

    def save(relative, data):
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(sanitize(data, secrets), indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

    def error(path, exc):
        status = getattr(exc, 'status', None)
        manifest['errors'].append({'resource': path, 'status': status, 'type': type(exc).__name__})
        print(f'Incomplete: {path}: {status or type(exc).__name__}', flush=True)

    resources = [('applications', 'applicationId'), ('flows', 'flowId'), ('data-requests', 'dataRequestId'), ('slot-types', 'slotTypeId'), ('guardrails', 'guardrailId'), ('knowledge-bases', 'knowledgeBaseId'), ('modalities', 'modalityId'), ('live-sync-scripts', 'liveSyncScriptId'), ('context-variables', None), ('secrets', None)]
    for path, id_field in resources:
        completed = 0
        try:
            items = applications if path == 'applications' else client.items(path)
            save(path + '/index.json', items)
            for item in items:
                try:
                    if id_field:
                        identifier = str(item[id_field])
                        encoded = urllib.parse.quote(identifier, safe='')
                        # Server IDs never become filesystem paths directly.
                        filename = urllib.parse.quote(identifier, safe='')
                        save(f'{path}/{filename}.json', client.get(path + '/' + encoded))
                        if path == 'applications':
                            for child in ['builds', 'deployments']:
                                save(f'{path}/{filename}/{child}.json', client.items(f'{path}/{encoded}/{child}'))
                        if path == 'knowledge-bases':
                            articles = client.items(f'{path}/{encoded}/articles')
                            save(f'{path}/{filename}/articles.json', articles)
                            for article in articles:
                                article_id = urllib.parse.quote(article['articleId'], safe='')
                                save(f'{path}/{filename}/articles/{article_id}.json', client.get(f'{path}/{encoded}/articles/{article_id}'))
                            save(f'{path}/{filename}/documents.json', client.items(f'{path}/{encoded}/documents'))
                    completed += 1
                except (ApiError, KeyError, ValueError, OSError) as exc:
                    error(path, exc)
            manifest['counts'][path] = completed
            print(f'{path}: {completed}/{len(items)} saved', flush=True)
        except (ApiError, KeyError, ValueError) as exc:
            error(path, exc)
        save('manifest.json', manifest)
    print(f'ACXD snapshot saved: {output}', flush=True)
    if manifest['errors']:
        raise SystemExit('Snapshot is partial. See manifest.json.')


if __name__ == '__main__':
    try:
        main()
    except ApiError as exc:
        raise SystemExit(str(exc))
