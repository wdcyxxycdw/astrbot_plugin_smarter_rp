import {
  bindingKey,
  chatBindingKey,
  createAssistantMessage,
  createDefaultSettings,
  createSerialQueue,
  findAccountBinding,
  makeChatName,
  validateAccountBinding,
  validateGenerateJob,
} from './lib.js';

const EXTENSION_NAME = 'astrbot-smarter-rp';
const SETTINGS_KEY = 'astrbot_smarter_rp';
const SETTINGS_SAVE_LOCK_KEY = `${SETTINGS_KEY}_settings_save_lock`;

let socket = null;
let settings = createDefaultSettings();
const generateQueue = createSerialQueue();

function context() {
  return SillyTavern.getContext();
}

function setStatus(text) {
  const element = document.querySelector('#astrbot_bridge_status');
  if (element) element.textContent = text;
}

function saveSettings() {
  const ctx = context();
  ctx.extensionSettings[SETTINGS_KEY] = settings;
  ctx.saveSettingsDebounced();
}

function mergeAccountBindings(remoteBindings, localBindings) {
  const merged = new Map();
  for (const binding of [...(remoteBindings || []), ...(localBindings || [])]) {
    merged.set(bindingKey(binding), binding);
  }
  return [...merged.values()];
}

function readSettingsSaveLock() {
  try {
    return JSON.parse(localStorage.getItem(SETTINGS_SAVE_LOCK_KEY) || 'null');
  } catch {
    return null;
  }
}

async function withSettingsSaveLock(job) {
  const token = `${Date.now()}:${Math.random()}`;
  const timeoutMs = 10000;
  const startedAt = Date.now();
  while (true) {
    const lock = readSettingsSaveLock();
    if (!lock || Number(lock.expiresAt) <= Date.now()) {
      localStorage.setItem(SETTINGS_SAVE_LOCK_KEY, JSON.stringify({ token, expiresAt: Date.now() + timeoutMs }));
      await delay(20);
      if (readSettingsSaveLock()?.token === token) {
        break;
      }
    }
    if (Date.now() - startedAt >= timeoutMs) {
      throw new Error('timed out waiting for settings save lock');
    }
    await delay(50);
  }

  try {
    return await job();
  } finally {
    if (readSettingsSaveLock()?.token === token) {
      localStorage.removeItem(SETTINGS_SAVE_LOCK_KEY);
    }
  }
}

async function saveSettingsImmediate() {
  return withSettingsSaveLock(async () => {
    const ctx = context();
    const response = await fetch('/api/settings/get', {
      method: 'POST',
      headers: ctx.getRequestHeaders(),
      cache: 'no-cache',
    });
    if (!response.ok) {
      throw new Error(`failed to read settings: ${response.status}`);
    }

    const data = await response.json();
    const persisted = JSON.parse(data.settings);
    persisted.extension_settings = persisted.extension_settings && typeof persisted.extension_settings === 'object' ? persisted.extension_settings : {};
    const remote = persisted.extension_settings[SETTINGS_KEY] || {};
    settings = {
      ...createDefaultSettings(),
      ...remote,
      ...settings,
      accountBindings: mergeAccountBindings(remote.accountBindings, settings.accountBindings),
      chatBindings: { ...(remote.chatBindings || {}), ...(settings.chatBindings || {}) },
    };
    persisted.extension_settings[SETTINGS_KEY] = settings;
    ctx.extensionSettings[SETTINGS_KEY] = settings;

    const saveResponse = await fetch('/api/settings/save', {
      method: 'POST',
      headers: ctx.getRequestHeaders(),
      body: JSON.stringify(persisted),
    });
    if (!saveResponse.ok) {
      throw new Error(`failed to save settings: ${saveResponse.status}`);
    }
  });
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForCharacters(timeoutMs = 30000) {
  const startedAt = Date.now();
  while (!Array.isArray(context().characters) || context().characters.length === 0) {
    if (Date.now() - startedAt >= timeoutMs) {
      throw new Error('characters are not loaded');
    }
    await delay(100);
  }
}

async function waitForBackendConnection(timeoutMs = 30000) {
  if (context().onlineStatus !== 'no_connection') {
    return;
  }

  const connectButton = document.querySelector(`#api_button_${context().mainApi}`);
  if (!connectButton) {
    throw new Error(`cannot connect SillyTavern API: missing button for ${context().mainApi}`);
  }
  connectButton.click();

  const startedAt = Date.now();
  while (context().onlineStatus === 'no_connection') {
    if (Date.now() - startedAt >= timeoutMs) {
      throw new Error('SillyTavern API is not connected');
    }
    await delay(100);
  }
}

function loadSettings() {
  const ctx = context();
  settings = { ...createDefaultSettings(), ...(ctx.extensionSettings[SETTINGS_KEY] ?? {}) };
  settings.accountBindings = Array.isArray(settings.accountBindings) ? settings.accountBindings : [];
  settings.chatBindings = settings.chatBindings && typeof settings.chatBindings === 'object' ? settings.chatBindings : {};
}

async function renderSettings() {
  const ctx = context();
  const html = await ctx.renderExtensionTemplateAsync(`third-party/${EXTENSION_NAME}`, 'settings', {});
  document.querySelector('#extensions_settings2').insertAdjacentHTML('beforeend', html);
  document.querySelector('#astrbot_bridge_url').value = settings.bridgeUrl;
  document.querySelector('#astrbot_bridge_url').addEventListener('change', (event) => {
    settings.bridgeUrl = event.target.value.trim() || createDefaultSettings().bridgeUrl;
    saveSettings();
  });
  document.querySelector('#astrbot_add_binding').addEventListener('click', () => {
    const binding = {
      adapter: document.querySelector('#astrbot_binding_adapter').value.trim(),
      platform: document.querySelector('#astrbot_binding_platform').value.trim(),
      accountId: document.querySelector('#astrbot_binding_account').value.trim(),
      characterId: document.querySelector('#astrbot_binding_character').value.trim(),
    };
    const validation = validateAccountBinding(binding, ctx.characters);
    if (!validation.ok) {
      setStatus(`Binding not saved: ${validation.message}`);
      return;
    }
    settings.accountBindings = settings.accountBindings.filter((existing) => {
      return !(existing.adapter === binding.adapter && existing.platform === binding.platform && existing.accountId === binding.accountId);
    });
    settings.accountBindings.push(binding);
    saveSettings();
    setStatus(`Saved binding for ${binding.adapter}:${binding.platform}:${binding.accountId}`);
  });
  document.querySelector('#astrbot_connect_bridge').addEventListener('click', connectBridge);
}

function sendResult(job, reply, characterId, chatId) {
  socket?.send(JSON.stringify({ type: 'generate_result', jobId: job.jobId, reply, characterId, chatId }));
}

function sendError(jobId, code, message) {
  socket?.send(JSON.stringify({ type: 'generate_error', jobId, code, message }));
}

async function ensureCharacterChat(job, binding) {
  await waitForCharacters();
  const ctx = context();
  const validation = validateAccountBinding(binding, ctx.characters);
  if (!validation.ok) {
    throw new Error(`invalid character binding: ${validation.message}`);
  }
  const characterIndex = Number(binding.characterId);

  const key = chatBindingKey({
    adapter: job.adapter.name,
    platform: job.adapter.platform,
    accountId: job.adapter.accountId,
    sessionId: job.session.id,
  });

  await ctx.selectCharacterById(characterIndex, { switchMenu: false });

  let chatBinding = settings.chatBindings[key];
  if (!chatBinding) {
    const chatName = makeChatName({
      platform: job.adapter.platform,
      displayName: job.session.displayName,
      sessionId: job.session.id,
    });
    const character = ctx.characters[characterIndex];
    const headers = ctx.getRequestHeaders();
    const chatHeader = { chat_metadata: {}, user_name: 'unused', character_name: 'unused' };
    const response = await fetch('/api/chats/save', {
      method: 'POST',
      cache: 'no-cache',
      headers,
      body: JSON.stringify({
        ch_name: character.name,
        file_name: chatName,
        chat: [chatHeader],
        avatar_url: character.avatar,
        force: false,
      }),
    });
    if (!response.ok) {
      throw new Error(`failed to create chat: ${response.status}`);
    }
    chatBinding = { characterId: String(characterIndex), chatId: chatName };
    settings.chatBindings[key] = chatBinding;
    await saveSettingsImmediate();
  }

  await ctx.openCharacterChat(chatBinding.chatId);
  return chatBinding;
}

function appendUserMessage(job) {
  const ctx = context();
  ctx.chat.push({
    name: job.user.name || 'User',
    is_user: true,
    is_system: false,
    mes: job.message.text,
    send_date: new Date().toISOString(),
    extra: {},
  });
}

function appendAssistantMessage(reply, characterId) {
  const ctx = context();
  const character = ctx.characters[Number(characterId)];
  ctx.chat.push(createAssistantMessage(reply, character));
}

async function handleGenerate(job) {
  const validation = validateGenerateJob(job);
  if (!validation.ok) {
    sendError(job.jobId || '', validation.code, validation.message);
    return;
  }

  const binding = findAccountBinding(settings, job.adapter);
  if (!binding) {
    sendError(job.jobId, 'missing_character_binding', `No character binding for ${job.adapter.name}:${job.adapter.platform}:${job.adapter.accountId}`);
    return;
  }

  try {
    await waitForBackendConnection();
    const chatBinding = await ensureCharacterChat(job, binding);
    appendUserMessage(job);
    await context().saveChat();
    const reply = String(await context().generateQuietPrompt({ quietPrompt: job.message.text }) || '').trim();
    if (!reply) {
      throw new Error('empty generation reply');
    }
    appendAssistantMessage(reply, chatBinding.characterId);
    await context().saveChat();
    sendResult(job, reply, chatBinding.characterId, chatBinding.chatId);
  } catch (error) {
    sendError(job.jobId, 'generation_failed', error instanceof Error ? error.message : String(error));
  }
}

function connectBridge() {
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    const previousSocket = socket;
    previousSocket.addEventListener('close', () => {
      if (socket === previousSocket) {
        socket = null;
        connectBridge();
      }
    }, { once: true });
    previousSocket.close();
    return;
  }
  try {
    socket = new WebSocket(settings.bridgeUrl);
  } catch (error) {
    socket = null;
    setStatus(`Connection error: ${error instanceof Error ? error.message : String(error)}`);
    return;
  }
  socket.addEventListener('open', () => {
    setStatus(`Connected to ${settings.bridgeUrl}`);
    socket.send(JSON.stringify({ type: 'hello', client: 'sillytavern-extension', version: '0.1.0' }));
  });
  socket.addEventListener('close', () => setStatus('Disconnected'));
  socket.addEventListener('error', () => setStatus('Connection error'));
  socket.addEventListener('message', async (event) => {
    let payload;
    try {
      payload = JSON.parse(event.data);
    } catch {
      return;
    }
    if (payload.type === 'hello_ack') {
      setStatus(`Connected: ${payload.server}`);
      return;
    }
    if (payload.type === 'generate') {
      await generateQueue(() => handleGenerate(payload));
    }
  });
}

jQuery(async () => {
  loadSettings();
  await renderSettings();
  connectBridge();
});
