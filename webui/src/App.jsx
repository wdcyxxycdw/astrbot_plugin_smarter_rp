import { useEffect, useState } from 'react';
import {
  deleteAccountBinding,
  deleteChatBinding,
  getAccountBindings,
  getCharacters,
  getChatBindings,
  getSavedToken,
  getStatus,
  getWorldbooks,
  importCharacter,
  importWorldbook,
  saveAccountBinding,
  saveToken,
} from './api.js';

function App() {
  const [token, setToken] = useState(getSavedToken());
  const [status, setStatus] = useState(null);
  const [characters, setCharacters] = useState([]);
  const [worldbooks, setWorldbooks] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [chats, setChats] = useState([]);
  const [message, setMessage] = useState('');
  const [accountForm, setAccountForm] = useState({ adapter: '', platform: '', accountId: '', characterId: '' });
  const [characterForm, setCharacterForm] = useState({ file: null, fileType: 'png', preservedName: '' });
  const [worldbookFile, setWorldbookFile] = useState(null);

  async function loadAll(nextToken = token) {
    saveToken(nextToken);
    setMessage('加载中...');
    try {
      const [statusData, characterData, worldbookData, accountData, chatData] = await Promise.all([
        getStatus(nextToken),
        getCharacters(nextToken),
        getWorldbooks(nextToken),
        getAccountBindings(nextToken),
        getChatBindings(nextToken),
      ]);
      setStatus(statusData);
      setCharacters(characterData.characters || []);
      setWorldbooks(worldbookData.worldbooks || []);
      setAccounts(accountData.bindings || []);
      setChats(chatData.bindings || []);
      setMessage('已刷新');
    } catch (error) {
      setMessage(`请求失败：${error.message}`);
    }
  }

  useEffect(() => {
    if (token) {
      loadAll(token);
    }
  }, []);

  async function handleCharacterImport(event) {
    event.preventDefault();
    if (!characterForm.file) return;
    await importCharacter(token, characterForm.file, characterForm.fileType, characterForm.preservedName);
    setCharacterForm({ file: null, fileType: 'png', preservedName: '' });
    await loadAll();
  }

  async function handleWorldbookImport(event) {
    event.preventDefault();
    if (!worldbookFile) return;
    await importWorldbook(token, worldbookFile);
    setWorldbookFile(null);
    await loadAll();
  }

  async function handleAccountSave(event) {
    event.preventDefault();
    await saveAccountBinding(token, accountForm);
    setAccountForm({ adapter: '', platform: '', accountId: '', characterId: '' });
    await loadAll();
  }

  return (
    <main>
      <header>
        <div>
          <h1>Smarter RP 管理</h1>
          <p>最小 WebUI：状态、导入与绑定管理。</p>
        </div>
        <form className="token-form" onSubmit={(event) => { event.preventDefault(); loadAll(token); }}>
          <input
            type="password"
            placeholder="WebUI Token"
            value={token}
            onChange={(event) => setToken(event.target.value)}
          />
          <button type="submit">连接</button>
        </form>
      </header>

      {message && <p className="message">{message}</p>}

      <section>
        <h2>状态</h2>
        {status ? (
          <div className="status-grid">
            <span>WebUI</span><strong>{status.webui.enabled ? '启用' : '停用'}</strong>
            <span>SillyTavern</span><strong>{status.tavern.online ? '在线' : '离线'}</strong>
            <span>地址</span><code>{status.tavern.baseUrl}</code>
            <span>目录</span><code>{status.tavern.installDir || '-'}</code>
            <span>版本</span><code>{status.tavern.version || '-'}</code>
          </div>
        ) : <p>输入 token 后连接。</p>}
      </section>

      <section>
        <h2>角色卡</h2>
        <form className="inline-form" onSubmit={handleCharacterImport}>
          <input type="file" onChange={(event) => setCharacterForm({ ...characterForm, file: event.target.files[0] })} />
          <input value={characterForm.fileType} onChange={(event) => setCharacterForm({ ...characterForm, fileType: event.target.value })} placeholder="文件类型" />
          <input value={characterForm.preservedName} onChange={(event) => setCharacterForm({ ...characterForm, preservedName: event.target.value })} placeholder="保留名称，可选" />
          <button type="submit">导入角色卡</button>
        </form>
        <SimpleList items={characters} getKey={(item, index) => item.id || item.name || index} />
      </section>

      <section>
        <h2>世界书</h2>
        <form className="inline-form" onSubmit={handleWorldbookImport}>
          <input type="file" accept="application/json,.json" onChange={(event) => setWorldbookFile(event.target.files[0])} />
          <button type="submit">导入世界书</button>
        </form>
        <SimpleList items={worldbooks} getKey={(item, index) => item.name || item.id || index} />
      </section>

      <section>
        <h2>账号绑定</h2>
        <form className="inline-form" onSubmit={handleAccountSave}>
          <input required placeholder="adapter" value={accountForm.adapter} onChange={(event) => setAccountForm({ ...accountForm, adapter: event.target.value })} />
          <input required placeholder="platform" value={accountForm.platform} onChange={(event) => setAccountForm({ ...accountForm, platform: event.target.value })} />
          <input required placeholder="accountId" value={accountForm.accountId} onChange={(event) => setAccountForm({ ...accountForm, accountId: event.target.value })} />
          <input required placeholder="characterId" value={accountForm.characterId} onChange={(event) => setAccountForm({ ...accountForm, characterId: event.target.value })} />
          <button type="submit">保存绑定</button>
        </form>
        <BindingTable
          rows={accounts}
          columns={['adapter', 'platform', 'accountId', 'characterId', 'updatedAt']}
          onDelete={async (row) => { await deleteAccountBinding(token, row); await loadAll(); }}
        />
      </section>

      <section>
        <h2>会话绑定</h2>
        <BindingTable
          rows={chats}
          columns={['adapter', 'platform', 'accountId', 'sessionId', 'characterId', 'chatId', 'updatedAt']}
          onDelete={async (row) => { await deleteChatBinding(token, row); await loadAll(); }}
        />
      </section>
    </main>
  );
}

function SimpleList({ items, getKey }) {
  if (!items.length) return <p className="empty">暂无数据</p>;
  return (
    <ul className="cards">
      {items.map((item, index) => (
        <li key={getKey(item, index)}>
          <strong>{item.name || item.id || `#${index + 1}`}</strong>
          <pre>{JSON.stringify(item, null, 2)}</pre>
        </li>
      ))}
    </ul>
  );
}

function BindingTable({ rows, columns, onDelete }) {
  if (!rows.length) return <p className="empty">暂无绑定</p>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>{columns.map((column) => <th key={column}>{column}</th>)}<th>操作</th></tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.adapter}:${row.platform}:${row.accountId}:${row.sessionId || ''}`}>
              {columns.map((column) => <td key={column}>{String(row[column] ?? '')}</td>)}
              <td><button type="button" onClick={() => onDelete(row)}>删除</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default App;
