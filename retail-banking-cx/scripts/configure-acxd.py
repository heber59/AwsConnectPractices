"""Configure the two AnyBank backend Secrets in ACXD from local readonly.env."""
import argparse
import importlib.util
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('acxd_export', ROOT.parent / 'scripts/export-acxd.py')
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace-id')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    cfg = api.read_env(ROOT.parent / 'config/sandbox.env')
    values = api.read_env(ROOT / 'readonly.env')
    workspace = args.workspace_id or cfg.get('ACXD_WORKSPACE_ID')
    if not workspace:
        parser.error('Set --workspace-id or ACXD_WORKSPACE_ID')
    for name in ['API_URL_Base', 'API_Key']:
        if not values.get(name):
            parser.error('Missing ' + name + ' in local readonly.env')
    base = values['API_URL_Base'].rstrip('/')
    parsed = urllib.parse.urlsplit(base)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
        parser.error('Backend URL must be a valid HTTPS base URL')
    # Validate the backend before changing the workspace.
    request = urllib.request.Request(base + '/retail-banking/accounts?customerId=CUST-12345', headers={'x-api-key': values['API_Key']})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.load(response)
    if not isinstance(data.get('accounts'), list):
        raise ValueError('Backend did not return the expected accounts collection')
    print(f"Backend verified: {len(data['accounts'])} mock accounts", flush=True)
    client = api.Client(cfg['AWS_DEFAULT_REGION'], workspace, cfg['ACXD_API_KEY'])
    existing = {secret['name']: secret for secret in client.items('secrets')}
    for name, value, sensitive in [('API_URL_Base', base, False), ('API_Key', values['API_Key'], True)]:
        method = 'PATCH' if name in existing else 'POST'
        print(f'{name}: {"update" if name in existing else "create"}; sensitive={sensitive}', flush=True)
        if not args.apply:
            continue
        payload = {'secretValue': value, 'isSensitive': sensitive}
        path = 'secrets'
        if method == 'POST':
            payload['name'] = name
        else:
            path += '/' + urllib.parse.quote(name, safe='')
        request = urllib.request.Request(client.base + '/sdk/' + path, headers={**client.headers, 'Content-Type': 'application/json'}, data=json.dumps(payload).encode(), method=method)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                response.read()  # Never print or save the response containing the secret value.
        except urllib.error.HTTPError as error:
            raise SystemExit(f'ACXD rejected {method} for {name}: HTTP {error.code}. No secret values displayed.') from None
    if args.apply:
        after = {item['name']: item for item in client.items('secrets')}
        assert after['API_URL_Base']['isSensitive'] is False
        assert after['API_Key']['isSensitive'] is True
        print('Verified: both Secrets exist with the expected sensitivity flags. Values were not logged.', flush=True)
    else:
        print('Inspection only. Add --apply to configure the Secrets.', flush=True)


if __name__ == '__main__':
    main()
