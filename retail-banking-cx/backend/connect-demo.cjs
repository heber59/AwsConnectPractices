const { DynamoDBClient, GetItemCommand } = require('@aws-sdk/client-dynamodb');
const db = new DynamoDBClient({});
exports.handler = async event => {
  const details = event.Details;
  if (details?.ContactData?.InstanceARN !== process.env.CONNECT_INSTANCE_ARN) throw new Error('Unexpected Connect instance');
  const customerId = details.Parameters?.customerId;
  const operation = details.Parameters?.operation;
  if (!['accounts', 'cards'].includes(operation) || !customerId) throw new Error('Invalid demo request');
  const result = await db.send(new GetItemCommand({ TableName: process.env.TABLE_NAME, Key: { pk: { S: 'STATE' } }, ConsistentRead: true }));
  const data = JSON.parse(result.Item.payload.S);
  const customer = data.customers.find(c => c.customerId === customerId);
  if (!customer) throw new Error('Customer not found');
  let message;
  if (operation === 'accounts') {
    const accounts = data.accounts.filter(a => a.customerId === customerId);
    message = `Demo customer ${customer.name}. ` + accounts.map(a => `Your ${a.type} account has an available balance of ${(a.availableCents / 100).toFixed(2)} US dollars.`).join(' ');
  } else {
    const cards = data.cards.filter(c => c.customerId === customerId);
    message = `Demo customer ${customer.name}. ` + cards.map(c => `Your card ending ${c.lastFour.split('').join(' ')} is ${c.status}.`).join(' ');
  }
  // Connect STRING_MAP response: the flow reads $.External.Message.
  return { CustomerId: customerId, CustomerName: customer.name, Message: message, Operation: operation };
};
