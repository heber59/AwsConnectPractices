const { randomUUID } = require('node:crypto');
class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}
const fail = (status, message) => { throw new ApiError(status, message); };
const required = (q, key) => typeof q[key] === 'string' && q[key].trim() ? q[key].trim() : fail(400, `${key} is required`);
function seed() {
  const state = { customers: [], accounts: [], cards: [], payees: [], transactions: [], disputes: [] };
  ['12345', '67890', '11111'].forEach((suffix, index) => {
    const n = index + 1, customerId = `CUST-${suffix}`;
    state.customers.push({ customerId, name: ['Alex Morgan', 'Jordan Lee', 'Taylor Reed'][index] });
    for (const [type, cents] of [['CHK', 418000], ['SAV', 1200000]]) {
      state.accounts.push({ customerId, accountId: `${type}-${n}00`, type: type === 'CHK' ? 'checking' : 'savings', currency: 'USD', balanceCents: cents, availableCents: cents });
    }
    state.cards.push({ customerId, cardId: `CARD-${n}000`, accountId: `CHK-${n}00`, lastFour: `${n}242`, status: 'active' });
    state.payees.push({ customerId, payeeId: `PAYEE-${n}00`, name: 'City Utilities' });
    state.transactions.push({ customerId, transactionId: `TXN-BK-${n}000`, accountId: `CHK-${n}00`, merchant: 'Corner Market', date: '2026-10-20', amount: 42.5, type: 'debit' });
  });
  return state;
}
const accountView = ({ balanceCents, availableCents, ...rest }) => ({ ...rest, balance: balanceCents / 100, availableBalance: availableCents / 100 });
function money(value) {
  if (typeof value !== 'string' || !/^\d{1,9}(\.\d{1,2})?$/.test(value)) fail(400, 'amount must be positive dollars with at most two decimal places');
  const [whole, fraction = ''] = value.split('.');
  const cents = Number(whole) * 100 + Number(fraction.padEnd(2, '0'));
  if (cents <= 0) fail(400, 'amount must be positive');
  return cents;
}
function execute(state, method, path, q = {}) {
  const read = method === 'GET', write = method === 'POST';
  const customer = () => {
    const id = required(q, 'customerId');
    if (!state.customers.some(c => c.customerId === id)) fail(404, 'Customer not found');
    return id;
  };
  const ownAccount = (id, customerId) => state.accounts.find(a => a.accountId === id && a.customerId === customerId) || fail(404, 'Account not found for customer');
  const debit = (account, cents) => {
    if (account.availableCents < cents) fail(409, 'Insufficient available balance');
    account.balanceCents -= cents; account.availableCents -= cents;
  };
  const id = prefix => `${prefix}-${randomUUID()}`;
  const today = () => new Date().toISOString().slice(0, 10);
  if (read && ['/accounts', '/cards', '/payees', '/disputes'].some(p => path === `/retail-banking${p}`)) {
    const customerId = customer(), collection = path.split('/').pop();
    const records = state[collection].filter(r => r.customerId === customerId);
    return { [collection]: collection === 'accounts' ? records.map(accountView) : records };
  }
  if (read && path === '/retail-banking/transactions') {
    const accountId = required(q, 'accountId');
    if (!state.accounts.some(a => a.accountId === accountId)) fail(404, 'Account not found');
    return { transactions: state.transactions.filter(t => t.accountId === accountId) };
  }
  const cardRoute = path.match(/^\/retail-banking\/cards\/([^/]+)\/(lock|unlock|replace)$/);
  if (write && cardRoute) {
    const [, cardId, action] = cardRoute;
    const card = state.cards.find(c => c.cardId === cardId) || fail(404, 'Card not found');
    if (card.status === 'replaced') fail(409, 'This card has been replaced and cannot be reactivated');
    if (action === 'replace') {
      const reason = required(q, 'reason');
      if (!['lost', 'stolen', 'damaged'].includes(reason)) fail(400, 'reason must be lost, stolen, or damaged');
      card.status = 'replaced'; card.replacementReason = reason;
      const replacement = { ...card, cardId: id('CARD'), lastFour: String(require('node:crypto').randomInt(1000, 10000)), status: 'active' };
      delete replacement.replacementReason;
      state.cards.push(replacement);
      return { card, replacementCard: replacement, reversible: false };
    }
    card.status = action === 'lock' ? 'locked' : 'active';
    return { card, reversible: true };
  }
  if (write && path === '/retail-banking/transfers') {
    const customerId = customer(), from = ownAccount(required(q, 'fromAccountId'), customerId), to = ownAccount(required(q, 'toAccountId'), customerId);
    const cents = money(q.amount), memo = required(q, 'memo');
    if (from === to) fail(400, 'Source and destination accounts must differ');
    debit(from, cents); to.balanceCents += cents; to.availableCents += cents;
    const transferId = id('TRANSFER');
    for (const [account, type] of [[from, 'debit'], [to, 'credit']]) state.transactions.push({ customerId, transactionId: id('TXN-BK'), accountId: account.accountId, transferId, merchant: 'Internal transfer', memo, date: today(), amount: cents / 100, type });
    return { transferId, status: 'completed', amount: cents / 100, fromAccount: accountView(from), toAccount: accountView(to) };
  }
  if (write && path === '/retail-banking/payments') {
    const customerId = customer(), account = ownAccount(required(q, 'fromAccountId'), customerId), payeeId = required(q, 'payeeId');
    const payee = state.payees.find(p => p.payeeId === payeeId && p.customerId === customerId) || fail(404, 'Payee not found for customer');
    const cents = money(q.amount); debit(account, cents);
    const paymentId = id('PAYMENT');
    state.transactions.push({ customerId, transactionId: id('TXN-BK'), accountId: account.accountId, paymentId, merchant: payee.name, date: today(), amount: cents / 100, type: 'debit' });
    return { paymentId, status: 'completed', payeeId, amount: cents / 100, account: accountView(account) };
  }
  if (write && path === '/retail-banking/disputes') {
    const customerId = customer(), transactionId = required(q, 'transactionId'), reason = required(q, 'reason'), cents = money(q.amount);
    const transaction = state.transactions.find(t => t.transactionId === transactionId && t.customerId === customerId) || fail(404, 'Transaction not found for customer');
    if (transaction.type !== 'debit' || cents > Math.round(transaction.amount * 100)) fail(400, 'Dispute must cover a debit and cannot exceed the charge');
    if (state.disputes.some(d => d.transactionId === transactionId)) fail(409, 'A dispute already exists for this transaction');
    const dispute = { disputeId: id('DISPUTE'), customerId, transactionId, reason, amount: cents / 100, status: 'submitted', date: today() };
    state.disputes.push(dispute); return { dispute };
  }
  fail(404, 'Route not found');
}
module.exports = { seed, execute, ApiError };
