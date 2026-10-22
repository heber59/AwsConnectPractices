const { test } = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const { seed } = require('../backend/core.cjs');
function load(send) {
  const exports = {};
  vm.runInNewContext(fs.readFileSync(require.resolve('../backend/readonly.cjs'), 'utf8'), {
    exports, console, Buffer, process: { env: { API_KEY: 'test-key', TABLE_NAME: 'test' } },
    require: name => name === '@aws-sdk/client-dynamodb' ? { DynamoDBClient: class { send(command) { return send(command); } }, GetItemCommand: class { constructor(input) { this.input = input; } } } : require(name === './core.cjs' ? '../backend/core.cjs' : name)
  });
  return exports.handler;
}
const event = { headers: { 'x-api-key': 'test-key' }, requestContext: { http: { method: 'GET' } }, rawPath: '/retail-banking/accounts', queryStringParameters: { customerId: 'CUST-12345' } };
test('read-only endpoint authenticates before accessing storage', async () => {
  let reads = 0;
  const handler = load(async () => { reads++; return {}; });
  assert.equal((await handler({ ...event, headers: {} })).statusCode, 403);
  assert.equal((await handler({ ...event, headers: { 'x-api-key': 'wrong' } })).statusCode, 403);
  assert.equal(reads, 0);
});
test('read-only endpoint rejects all writes before storage access', async () => {
  let reads = 0;
  const handler = load(async () => { reads++; return {}; });
  assert.equal((await handler({ ...event, requestContext: { http: { method: 'POST' } } })).statusCode, 405);
  assert.equal(reads, 0);
});
test('Function URL GET returns the seeded accounts', async () => {
  const handler = load(async command => { assert.equal(command.input.TableName, 'test'); return { Item: { payload: { S: JSON.stringify(seed()) } } }; });
  const result = await handler(event);
  assert.equal(result.statusCode, 200);
  assert.equal(JSON.parse(result.body).accounts[0].availableBalance, 4180);
});
