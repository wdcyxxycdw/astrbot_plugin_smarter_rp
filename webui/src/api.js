const TOKEN_KEY = 'smarterRpWebToken';

export function getSavedToken() {
  return localStorage.getItem(TOKEN_KEY) || '';
}

export function saveToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

export async function apiFetch(path, { token, ...options } = {}) {
  const headers = new Headers(options.headers || {});
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

export function getStatus(token) {
  return apiFetch('/api/status', { token });
}

export function getCharacters(token) {
  return apiFetch('/api/characters', { token });
}

export function importCharacter(token, file, fileType, preservedName) {
  const form = new FormData();
  form.append('file', file);
  form.append('fileType', fileType || 'png');
  if (preservedName) {
    form.append('preservedName', preservedName);
  }
  return apiFetch('/api/characters/import', { token, method: 'POST', body: form });
}

export function getWorldbooks(token) {
  return apiFetch('/api/worldbooks', { token });
}

export function importWorldbook(token, file) {
  const form = new FormData();
  form.append('file', file);
  return apiFetch('/api/worldbooks/import', { token, method: 'POST', body: form });
}

export function getAccountBindings(token) {
  return apiFetch('/api/bindings/accounts', { token });
}

export function saveAccountBinding(token, binding) {
  const path = `/api/bindings/accounts/${encodeURIComponent(binding.adapter)}/${encodeURIComponent(binding.platform)}/${encodeURIComponent(binding.accountId)}`;
  return apiFetch(path, {
    token,
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ characterId: binding.characterId }),
  });
}

export function deleteAccountBinding(token, binding) {
  const path = `/api/bindings/accounts/${encodeURIComponent(binding.adapter)}/${encodeURIComponent(binding.platform)}/${encodeURIComponent(binding.accountId)}`;
  return apiFetch(path, { token, method: 'DELETE' });
}

export function getChatBindings(token) {
  return apiFetch('/api/bindings/chats', { token });
}

export function deleteChatBinding(token, binding) {
  const path = `/api/bindings/chats/${encodeURIComponent(binding.adapter)}/${encodeURIComponent(binding.platform)}/${encodeURIComponent(binding.accountId)}/${encodeURIComponent(binding.sessionId)}`;
  return apiFetch(path, { token, method: 'DELETE' });
}
