import assert from 'node:assert/strict';
import test from 'node:test';

import {
  bindingKey,
  chatBindingKey,
  createDefaultSettings,
  createAssistantMessage,
  createSerialQueue,
  findAccountBinding,
  makeChatName,
  shortSessionId,
  validateAccountBinding,
  validateGenerateJob,
} from '../sillytavern_extension/astrbot-smarter-rp/lib.js';

test('bindingKey combines adapter platform and account', () => {
  assert.equal(bindingKey({ adapter: 'aiocqhttp', platform: 'qq', accountId: '123' }), 'aiocqhttp:qq:123');
});

test('chatBindingKey includes session id', () => {
  assert.equal(
    chatBindingKey({ adapter: 'aiocqhttp', platform: 'qq', accountId: '123', sessionId: 'session-1' }),
    'aiocqhttp:qq:123:session-1',
  );
});

test('makeChatName uses readable AstrBot source', () => {
  assert.equal(makeChatName({ platform: 'qq', displayName: '测试群', sessionId: 'abcdef123456' }), '[AstrBot] qq-测试群-abcdef3456');
});

test('shortSessionId keeps common prefix sessions distinct', () => {
  assert.equal(shortSessionId('session-e2e-001'), 'sessio-001');
  assert.equal(shortSessionId('session-e2e-002'), 'sessio-002');
});

test('shortSessionId removes unsafe empty value', () => {
  assert.equal(shortSessionId('abcdef123456'), 'abcdef3456');
  assert.equal(shortSessionId(''), 'unknown');
});

test('findAccountBinding matches adapter facts', () => {
  const settings = createDefaultSettings();
  settings.accountBindings.push({ adapter: 'aiocqhttp', platform: 'qq', accountId: '123', characterId: 'alice' });

  assert.deepEqual(findAccountBinding(settings, { name: 'aiocqhttp', platform: 'qq', accountId: '123' }), {
    adapter: 'aiocqhttp',
    platform: 'qq',
    accountId: '123',
    characterId: 'alice',
  });
});

test('findAccountBinding returns null if settings.accountBindings is missing', () => {
  const settings = { chatBindings: {} };
  assert.equal(findAccountBinding(settings, { name: 'aiocqhttp', platform: 'qq', accountId: '123' }), null);
});

test('findAccountBinding returns null if settings.accountBindings is not an array', () => {
  const settings = { accountBindings: 'not-an-array', chatBindings: {} };
  assert.equal(findAccountBinding(settings, { name: 'aiocqhttp', platform: 'qq', accountId: '123' }), null);
});

test('findAccountBinding returns null if settings.accountBindings is null', () => {
  const settings = { accountBindings: null, chatBindings: {} };
  assert.equal(findAccountBinding(settings, { name: 'aiocqhttp', platform: 'qq', accountId: '123' }), null);
});

test('validateGenerateJob accepts minimal valid job', () => {
  assert.equal(validateGenerateJob({
    type: 'generate',
    jobId: 'job-1',
    adapter: { name: 'aiocqhttp', platform: 'qq', accountId: '123' },
    session: { id: 'session-1', displayName: '测试群' },
    user: { id: 'user-1', name: 'Alice' },
    message: { text: 'hello' },
  }).ok, true);
});

test('validateGenerateJob rejects missing message text', () => {
  assert.deepEqual(validateGenerateJob({ type: 'generate', jobId: 'job-1' }), {
    ok: false,
    code: 'invalid_generate_job',
    message: 'message.text is required',
  });
});

test('validateGenerateJob rejects missing adapter.name', () => {
  assert.deepEqual(validateGenerateJob({
    type: 'generate',
    jobId: 'job-1',
    adapter: { platform: 'qq', accountId: '123' },
    session: { id: 'session-1' },
    message: { text: 'hello' },
  }), {
    ok: false,
    code: 'invalid_generate_job',
    message: 'adapter.name is required',
  });
});

test('validateGenerateJob rejects missing adapter.platform', () => {
  assert.deepEqual(validateGenerateJob({
    type: 'generate',
    jobId: 'job-1',
    adapter: { name: 'aiocqhttp', accountId: '123' },
    session: { id: 'session-1' },
    message: { text: 'hello' },
  }), {
    ok: false,
    code: 'invalid_generate_job',
    message: 'adapter.platform is required',
  });
});

test('validateAccountBinding rejects blank required fields', () => {
  assert.deepEqual(validateAccountBinding({ adapter: 'aiocqhttp', platform: 'qq', accountId: '123', characterId: '' }, [{ name: 'Alice' }]), {
    ok: false,
    message: 'characterId is required',
  });
});

test('validateAccountBinding rejects whitespace characterId before numeric coercion', () => {
  assert.deepEqual(validateAccountBinding({ adapter: 'aiocqhttp', platform: 'qq', accountId: '123', characterId: '   ' }, [{ name: 'Alice' }]), {
    ok: false,
    message: 'characterId is required',
  });
});

test('validateAccountBinding rejects non-existing character indexes', () => {
  assert.deepEqual(validateAccountBinding({ adapter: 'aiocqhttp', platform: 'qq', accountId: '123', characterId: '1' }, [{ name: 'Alice' }]), {
    ok: false,
    message: 'characterId must be an existing character index',
  });
});

test('validateAccountBinding accepts an existing integer character index', () => {
  assert.deepEqual(validateAccountBinding({ adapter: 'aiocqhttp', platform: 'qq', accountId: '123', characterId: '0' }, [{ name: 'Alice' }]), {
    ok: true,
  });
});

test('createAssistantMessage uses character name and non-user shape', () => {
  assert.deepEqual(createAssistantMessage(' hello ', { name: 'Alice' }, '2026-01-02T03:04:05.000Z'), {
    name: 'Alice',
    is_user: false,
    is_system: false,
    mes: 'hello',
    send_date: '2026-01-02T03:04:05.000Z',
    extra: {},
  });
});

test('createSerialQueue runs jobs one at a time in arrival order', async () => {
  const queue = createSerialQueue();
  const events = [];
  let releaseFirst;
  const firstCanFinish = new Promise((resolve) => {
    releaseFirst = resolve;
  });

  const first = queue(async () => {
    events.push('first start');
    await firstCanFinish;
    events.push('first end');
    return 'first';
  });
  const second = queue(async () => {
    events.push('second start');
    return 'second';
  });

  await Promise.resolve();
  assert.deepEqual(events, ['first start']);
  releaseFirst();
  assert.equal(await first, 'first');
  assert.equal(await second, 'second');
  assert.deepEqual(events, ['first start', 'first end', 'second start']);
});
