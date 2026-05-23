export function createDefaultSettings() {
  return {
    bridgeUrl: 'ws://127.0.0.1:8008/ws',
    accountBindings: [],
    chatBindings: {},
  };
}

export function cleanPart(value, fallback = 'unknown') {
  const text = String(value ?? '').trim();
  return text || fallback;
}

export function shortSessionId(sessionId) {
  const text = cleanPart(sessionId);
  if (text === 'unknown' || text.length <= 10) {
    return text;
  }
  return `${text.slice(0, 6)}${text.slice(-4)}`;
}

export function bindingKey({ adapter, platform, accountId }) {
  return [cleanPart(adapter), cleanPart(platform), cleanPart(accountId)].join(':');
}

export function chatBindingKey({ adapter, platform, accountId, sessionId }) {
  return [cleanPart(adapter), cleanPart(platform), cleanPart(accountId), cleanPart(sessionId)].join(':');
}

export function makeChatName({ platform, displayName, sessionId }) {
  return `[AstrBot] ${cleanPart(platform)}-${cleanPart(displayName)}-${shortSessionId(sessionId)}`;
}

export function findAccountBinding(settings, adapter) {
  if (!Array.isArray(settings?.accountBindings)) {
    return null;
  }
  const key = bindingKey({ adapter: adapter.name, platform: adapter.platform, accountId: adapter.accountId });
  return settings.accountBindings.find((binding) => bindingKey(binding) === key) ?? null;
}

export function validateAccountBinding(binding, characters = []) {
  for (const field of ['adapter', 'platform', 'accountId', 'characterId']) {
    if (!cleanPart(binding?.[field], '')) {
      return { ok: false, message: `${field} is required` };
    }
  }

  const characterIndex = Number(binding.characterId);
  if (!Number.isInteger(characterIndex) || characterIndex < 0 || !characters[characterIndex]) {
    return { ok: false, message: 'characterId must be an existing character index' };
  }

  return { ok: true };
}

export function createAssistantMessage(reply, character, sendDate = new Date().toISOString()) {
  return {
    name: character?.name || 'Assistant',
    is_user: false,
    is_system: false,
    mes: String(reply || '').trim(),
    send_date: sendDate,
    extra: {},
  };
}

export function createSerialQueue() {
  let tail = Promise.resolve();
  return (job) => {
    const run = tail.then(job, job);
    tail = run.catch(() => {});
    return run;
  };
}

export function validateGenerateJob(job) {
  if (!job || job.type !== 'generate') {
    return { ok: false, code: 'invalid_generate_job', message: 'type must be generate' };
  }
  if (!cleanPart(job.jobId, '')) {
    return { ok: false, code: 'invalid_generate_job', message: 'jobId is required' };
  }
  if (!cleanPart(job?.message?.text, '')) {
    return { ok: false, code: 'invalid_generate_job', message: 'message.text is required' };
  }
  if (!cleanPart(job?.adapter?.name, '')) {
    return { ok: false, code: 'invalid_generate_job', message: 'adapter.name is required' };
  }
  if (!cleanPart(job?.adapter?.platform, '')) {
    return { ok: false, code: 'invalid_generate_job', message: 'adapter.platform is required' };
  }
  if (!cleanPart(job?.adapter?.accountId, '')) {
    return { ok: false, code: 'invalid_generate_job', message: 'adapter.accountId is required' };
  }
  if (!cleanPart(job?.session?.id, '')) {
    return { ok: false, code: 'invalid_generate_job', message: 'session.id is required' };
  }
  return { ok: true };
}
