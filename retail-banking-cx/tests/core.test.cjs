const { test } = require('node:test');
const assert = require('node:assert/strict');
const { seed, execute } = require('../backend/core.cjs');
const customerId = 'CUST-12345';
const transfer = { customerId, fromAccountId: 'CHK-100', toAccountId: 'SAV-100', amount: '10.25', memo: 'Workshop' };
test('all supplied customer identifiers have independent fixtures', () => {
  const state = seed();
  for (const id of ['CUST-12345', 'CUST-67890', 'CUST-11111']) {
    assert.equal(execute(state, 'GET', '/retail-banking/accounts', { customerId: id }).accounts.length, 2);
    for (const name of ['cards', 'payees', 'disputes']) assert.ok(Array.isArray(execute(state, 'GET', `/retail-banking/${name}`, { customerId: id })[name]));
  }
});
test('transfer conserves money and produces two posted transactions', () => {
  const state = seed();
  const result = execute(state, 'POST', '/retail-banking/transfers', transfer);
  assert.equal(result.fromAccount.availableBalance, 4169.75);
  assert.equal(result.toAccount.availableBalance, 12010.25);
  assert.equal(state.transactions.filter(t => t.transferId === result.transferId).length, 2);
});
test('invalid amounts, insufficient funds, same account, and foreign ownership are rejected without debiting', () => {
  for (const change of [{ amount: '-1' }, { amount: '0' }, { amount: 'NaN' }, { amount: '1.001' }, { amount: '999999' }, { toAccountId: 'CHK-100' }, { toAccountId: 'SAV-200' }, { memo: '' }]) {
    const state = seed();
    assert.throws(() => execute(state, 'POST', '/retail-banking/transfers', { ...transfer, ...change }));
    assert.equal(state.accounts[0].availableCents, 418000);
  }
});
test('payment checks payee ownership and records a debit', () => {
  const state = seed(), q = { customerId, payeeId: 'PAYEE-200', fromAccountId: 'CHK-100', amount: '20' };
  assert.throws(() => execute(state, 'POST', '/retail-banking/payments', q));
  const result = execute(state, 'POST', '/retail-banking/payments', { ...q, payeeId: 'PAYEE-100' });
  assert.equal(result.account.balance, 4160);
  assert.equal(state.transactions.at(-1).paymentId, result.paymentId);
});
test('card freeze is reversible; replaced cards cannot be unlocked', () => {
  const state = seed(), path = '/retail-banking/cards/CARD-1000';
  assert.equal(execute(state, 'POST', `${path}/lock`).card.status, 'locked');
  assert.equal(execute(state, 'POST', `${path}/unlock`).card.status, 'active');
  assert.throws(() => execute(state, 'POST', `${path}/replace`, { reason: 'other' }));
  const result = execute(state, 'POST', `${path}/replace`, { reason: 'lost' });
  assert.equal(result.reversible, false);
  assert.equal(result.replacementCard.status, 'active');
  assert.throws(() => execute(state, 'POST', `${path}/unlock`));
});
test('disputes enforce ownership, amount, and duplicate prevention', () => {
  const state = seed(), q = { customerId, transactionId: 'TXN-BK-1000', amount: '42.50', reason: 'Unrecognized charge' };
  assert.throws(() => execute(state, 'POST', '/retail-banking/disputes', { ...q, amount: '43' }));
  assert.throws(() => execute(state, 'POST', '/retail-banking/disputes', { ...q, customerId: 'CUST-67890' }));
  assert.equal(execute(state, 'POST', '/retail-banking/disputes', q).dispute.status, 'submitted');
  assert.throws(() => execute(state, 'POST', '/retail-banking/disputes', q));
  assert.equal(execute(state, 'GET', '/retail-banking/disputes', { customerId }).disputes.length, 1);
});
test('all 11 imported tool requests map to implemented routes', () => {
  const fs = require('node:fs'), path = require('node:path');
  const dir = path.join(__dirname, '../acxd');
  for (const name of fs.readdirSync(dir).filter(n => n.endsWith('.datarequest.json'))) {
    const request = JSON.parse(fs.readFileSync(path.join(dir, name), 'utf8').replace(/^\uFEFF/, ''));
    const values = { customerId, accountId: 'CHK-100', cardId: 'CARD-1000', fromAccountId: 'CHK-100', toAccountId: 'SAV-100', amount: '1', memo: 'Test', payeeId: 'PAYEE-100', transactionId: 'TXN-BK-1000', reason: 'lost' };
    const raw = request.webhook.environments.production.url.replace('{API_URL_Base:NLX.Secret}', 'https://example.test').replace(/\{(\w+)\}/g, (_, key) => encodeURIComponent(values[key]));
    const url = new URL(raw);
    assert.ok(execute(seed(), request.webhook.method, url.pathname, Object.fromEntries(url.searchParams)), name);
  }
});
