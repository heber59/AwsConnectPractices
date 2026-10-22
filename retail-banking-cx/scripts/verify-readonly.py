"""Verify the deployed read-only API without displaying its secret."""
import json
import urllib.request
import urllib.error
from pathlib import Path
root=Path(__file__).resolve().parents[1]
cfg=dict(line.split('=',1) for line in (root/'readonly.env').read_text(encoding='utf-8-sig').splitlines() if '=' in line)
base=cfg['API_URL_Base'].rstrip('/')
checks=[]
for path,collection in [('accounts?customerId=CUST-12345','accounts'),('cards?customerId=CUST-12345','cards'),('payees?customerId=CUST-12345','payees'),('disputes?customerId=CUST-12345','disputes'),('transactions?accountId=CHK-100','transactions')]:
    request=urllib.request.Request(base+'/retail-banking/'+path,headers={'x-api-key':cfg['API_Key']})
    with urllib.request.urlopen(request,timeout=30) as response:
        body=json.load(response)
        assert response.status==200 and isinstance(body[collection],list)
        print('GET',path,response.status,'records='+str(len(body[collection])),flush=True)
        checks.append({'method':'GET','path':path,'status':response.status,'records':len(body[collection])})
for method,path,headers,expected in [('GET','accounts?customerId=CUST-12345',{},403),('POST','payments',{'x-api-key':cfg['API_Key']},405)]:
    request=urllib.request.Request(base+'/retail-banking/'+path,headers=headers,method=method)
    try: urllib.request.urlopen(request,timeout=30)
    except urllib.error.HTTPError as error:
        assert error.code==expected,(error.code,expected)
        print(method,path,error.code,'as expected',flush=True)
        checks.append({'method':method,'path':path,'status':error.code})
    else: raise AssertionError('Expected rejection')
(root/'.build').mkdir(parents=True,exist_ok=True)
(root/'.build/readonly-verification.json').write_text(json.dumps({'baseUrl':base,'checks':checks},indent=2))
print('All 7 deployed endpoint checks passed.',flush=True)
