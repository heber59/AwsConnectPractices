const { test } = require('node:test');
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { once } = require('node:events');
const net = require('node:net');
test('HTTP server rejects missing keys and persists successful writes locally', async () => {
  const probe = net.createServer();
  probe.listen(0, '127.0.0.1'); await once(probe, 'listening');
  const port = probe.address().port;
  await new Promise(resolve => probe.close(resolve));
  const child = spawn(process.execPath, [require.resolve('../backend/server.cjs')], { env: { ...process.env, PORT: String(port), API_KEY: 'test-only-key' }, stdio: ['ignore', 'pipe', 'pipe'] });
  try {
    await Promise.race([once(child.stdout, 'data'), once(child, 'exit').then(() => { throw new Error('Server exited before startup'); }), new Promise((_, reject) => { const timer = setTimeout(() => reject(new Error('Startup timed out')), 5000); timer.unref(); })]);
    const base = `http://127.0.0.1:${port}/retail-banking`;
    assert.equal((await fetch(`${base}/accounts?customerId=CUST-12345`)).status, 403);
    const headers = { 'x-api-key': 'test-only-key' };
    const payment = await fetch(`${base}/payments?customerId=CUST-12345&payeeId=PAYEE-100&fromAccountId=CHK-100&amount=20`, { method: 'POST', headers });
    assert.equal(payment.status, 200);
    const accounts = await (await fetch(`${base}/accounts?customerId=CUST-12345`, { headers })).json();
    assert.equal(accounts.accounts[0].balance, 4160);
    const invalid = await fetch(`${base}/payments?customerId=CUST-12345&payeeId=PAYEE-100&fromAccountId=CHK-100&amount=999999`, { method: 'POST', headers });
    assert.equal(invalid.status, 409);
    const after = await (await fetch(`${base}/accounts?customerId=CUST-12345`, { headers })).json();
    assert.equal(after.accounts[0].balance, 4160);
  } finally {
    const exited = once(child, 'exit'); child.kill(); await exited;
  }
});
