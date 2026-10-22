const { DynamoDBClient, GetItemCommand } = require('@aws-sdk/client-dynamodb');
const { timingSafeEqual } = require('node:crypto');
const { execute, ApiError } = require('./core.cjs');
const db = new DynamoDBClient({});
const response = (statusCode, body) => ({ statusCode, headers: { 'content-type': 'application/json', 'cache-control': 'no-store' }, body: JSON.stringify(body) });
exports.handler = async event => {
  const provided = Object.entries(event.headers || {}).find(([key]) => key.toLowerCase() === 'x-api-key')?.[1];
  const expected = process.env.API_KEY;
  if (!provided || !expected || typeof provided !== 'string') return response(403, { error: { message: 'Forbidden' } });
  const actualBuffer = Buffer.from(provided), expectedBuffer = Buffer.from(expected);
  if (actualBuffer.length !== expectedBuffer.length || !timingSafeEqual(actualBuffer, expectedBuffer)) return response(403, { error: { message: 'Forbidden' } });
  const method = event.requestContext?.http?.method || event.httpMethod;
  // Deny every write before retrieving or modifying data.
  if (method !== 'GET') return response(405, { error: { message: 'This sandbox endpoint is read-only. No changes were made.' } });
  try {
    const result = await db.send(new GetItemCommand({ TableName: process.env.TABLE_NAME, Key: { pk: { S: 'STATE' } }, ConsistentRead: true }));
    if (!result.Item?.payload?.S) return response(503, { error: { message: 'Workshop data has not been initialized' } });
    const data = JSON.parse(result.Item.payload.S);
    return response(200, execute(data, method, event.rawPath || event.path, event.queryStringParameters || {}));
  } catch (error) {
    if (error instanceof ApiError) return response(error.status, { error: { message: error.message } });
    console.error('Read-only backend failure', error.name);
    return response(500, { error: { message: 'Unable to retrieve workshop data' } });
  }
};
