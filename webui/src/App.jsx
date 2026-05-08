import React, { useEffect, useMemo, useState } from 'react';
import zhCN from 'antd/locale/zh_CN';
import {
  BugOutlined,
  CheckCircleOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  PauseCircleOutlined,
  ReadOutlined,
  TeamOutlined,
  UserOutlined,
  UserSwitchOutlined,
} from '@ant-design/icons';
import {
  Button,
  Card,
  Checkbox,
  Col,
  ConfigProvider,
  Form,
  Input,
  InputNumber,
  Layout,
  Menu,
  Popconfirm,
  Row,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
  theme,
} from 'antd';

const { Header, Sider, Content } = Layout;
const { Title, Paragraph, Text } = Typography;
const { TextArea } = Input;

const menuItems = [
  { key: 'dashboard', icon: <DashboardOutlined />, label: '控制台' },
  { key: 'accounts', icon: <UserOutlined />, label: '账号' },
  { key: 'characters', icon: <UserSwitchOutlined />, label: '角色' },
  { key: 'lorebooks', icon: <ReadOutlined />, label: '世界书' },
  { key: 'sessions', icon: <TeamOutlined />, label: '会话' },
  { key: 'memory', icon: <DatabaseOutlined />, label: '记忆' },
  { key: 'debug', icon: <BugOutlined />, label: '调试' },
];

const characterTextFields = [
  ['name', '名称'],
  ['system_prompt', '完整角色提示词'],
];

const emptyCharacterForm = Object.fromEntries(characterTextFields.map(([field]) => [field, '']));


const entryTextFields = [
  ['title', '标题'],
  ['content', '内容'],
  ['position', '插入位置'],
  ['group', '分组'],
];

const entryListFields = [
  ['keys', '关键词'],
  ['secondary_keys', '二级关键词'],
  ['character_filter', '角色过滤'],
];

const entryBoolFields = [
  ['enabled', '已启用'],
  ['constant', '常驻'],
  ['selective', '选择性触发'],
  ['regex', '正则'],
  ['case_sensitive', '区分大小写'],
  ['recursive', '递归'],
];

const entryNumberFields = [
  ['depth', '深度'],
  ['priority', '优先级'],
  ['order', '排序'],
  ['probability', '触发概率'],
  ['cooldown_turns', '冷却轮数'],
  ['sticky_turns', '粘滞轮数'],
  ['max_injections_per_chat', '单聊最大注入次数'],
];

const entryIntegerFields = new Set([
  'depth',
  'priority',
  'order',
  'cooldown_turns',
  'sticky_turns',
  'max_injections_per_chat',
]);

const positionOptions = [
  'before_character',
  'after_character',
  'before_history',
  'in_history',
  'after_history',
  'post_history',
].map((value) => ({ value, label: value }));

const emptyLorebookForm = {
  name: '',
  description: '',
  scope: 'global',
  session_id: '',
};

const emptyEntryForm = {
  title: '',
  content: '',
  enabled: true,
  constant: false,
  keys: '',
  secondary_keys: '',
  selective: false,
  regex: false,
  case_sensitive: false,
  position: 'before_history',
  depth: 0,
  priority: 0,
  order: 0,
  probability: 1,
  cooldown_turns: 0,
  sticky_turns: 0,
  recursive: false,
  group: '',
  character_filter: '',
  max_injections_per_chat: null,
};

function linesToList(value) {
  return value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
}

function listToLines(value) {
  return Array.isArray(value) ? value.join('\n') : '';
}

function pluginPageBridge() {
  return window.AstrBotPluginPage || null;
}

function pluginEndpoint(path) {
  return `api/${path.replace(/^\/api\//, '')}`;
}

async function apiFetch(path, options = {}) {
  const bridge = pluginPageBridge();
  const method = (options.method || 'GET').toUpperCase();
  if (bridge) {
    await bridge.ready();
    if (method === 'GET') {
      return bridge.apiGet(pluginEndpoint(path));
    }
    if (method === 'POST' || method === 'PATCH' || method === 'DELETE') {
      const body = options.body ? JSON.parse(options.body) : null;
      return bridge.apiPost(pluginEndpoint(path), { method, body });
    }
  }

  const token = new URLSearchParams(window.location.search).get('token');
  const headers = new Headers(options.headers || {});
  headers.set('Accept', 'application/json');
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(path, { ...options, headers });
  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!response.ok) {
    const detail = data?.detail || data?.message || response.statusText;
    throw new Error(`${response.status} ${detail}`);
  }
  return data;
}

function DashboardPage() {
  const [globalPrompt, setGlobalPrompt] = useState('');
  const [loadingConfig, setLoadingConfig] = useState(false);
  const [savingConfig, setSavingConfig] = useState(false);
  const [configError, setConfigError] = useState('');
  const [configSaved, setConfigSaved] = useState(false);

  async function loadConfig() {
    setLoadingConfig(true);
    setConfigError('');
    try {
      const data = await apiFetch('/api/dashboard/config');
      setGlobalPrompt(data?.global_prompt || '');
    } catch (err) {
      setConfigError(err.message);
    } finally {
      setLoadingConfig(false);
    }
  }

  async function saveConfig() {
    setSavingConfig(true);
    setConfigError('');
    setConfigSaved(false);
    try {
      const data = await apiFetch('/api/dashboard/config', {
        method: 'PATCH',
        body: JSON.stringify({ global_prompt: globalPrompt }),
      });
      setGlobalPrompt(data?.global_prompt || '');
      setConfigSaved(true);
    } catch (err) {
      setConfigError(err.message);
    } finally {
      setSavingConfig(false);
    }
  }

  useEffect(() => {
    loadConfig();
  }, []);

  const cards = [
    {
      title: '默认启用',
      value: '已启用',
      tone: 'green',
      icon: <CheckCircleOutlined />,
      description: 'Smarter RP 会在已配置的会话中默认保持启用。',
    },
    {
      title: '角色',
      value: 'API 驱动',
      tone: 'blue',
      icon: <UserSwitchOutlined />,
      description: '角色档案、人设提示词和关联世界书都可以在 WebUI 中管理。',
    },
    {
      title: '记忆',
      value: '自动管理',
      tone: 'gold',
      icon: <DatabaseOutlined />,
      description: '会话摘要、结构化状态、检索到的记忆和调试轨迹都通过令牌鉴权访问。',
    },
  ];

  return (
    <section className="page-panel dashboard-panel">
      <div className="hero-copy">
        <Tag className="phase-tag">WebUI</Tag>
        <Title level={1}>Smarter RP 控制台</Title>
        <Paragraph>
          通过受令牌保护的 API 面板管理角色、世界书、会话、记忆和调试轨迹。
        </Paragraph>
      </div>
      <Row gutter={[18, 18]} className="status-grid">
        {cards.map((card) => (
          <Col xs={24} lg={8} key={card.title}>
            <Card className={`status-card status-card-${card.tone}`} bordered={false}>
              <Space className="status-card-header" align="start">
                <span className="status-icon">{card.icon}</span>
                <Tag color={card.tone}>{card.title}</Tag>
              </Space>
              <Title level={2}>{card.value}</Title>
              <Paragraph>{card.description}</Paragraph>
            </Card>
          </Col>
        ))}
      </Row>
      <Card className="feature-card form-card" bordered={false}>
        <Space className="form-title-row" align="center">
          <Title level={3}>全局提示词</Title>
          {configSaved && <Tag color="green">已保存</Tag>}
        </Space>
        <Paragraph type="secondary">
          这段提示词会注入到 Smarter RP 的全局规则块中，并追加在 AstrBot 原有系统提示词之后。
        </Paragraph>
        {configError && <div className="error-banner">{configError}</div>}
        <Form layout="vertical">
          <Form.Item label="全局提示词">
            <TextArea
              rows={6}
              value={globalPrompt}
              disabled={loadingConfig}
              onChange={(event) => {
                setGlobalPrompt(event.target.value);
                setConfigSaved(false);
              }}
            />
          </Form.Item>
          <Space wrap>
            <Button type="primary" onClick={saveConfig} loading={savingConfig}>
              保存全局提示词
            </Button>
            <Button onClick={loadConfig} loading={loadingConfig}>重新加载</Button>
          </Space>
        </Form>
      </Card>
    </section>
  );
}

function AccountsPage() {
  return (
    <section className="page-panel split-panel">
      <div>
        <Tag className="phase-tag">账号</Tag>
        <Title level={1}>账号默认设置</Title>
        <Paragraph>
          账号 API 可管理每个账号的默认设置，同时保留日常使用时默认启用的行为。
        </Paragraph>
      </div>
      <Card className="feature-card" bordered={false}>
        <Title level={3}>账号控制</Title>
        <ul className="feature-list">
          <li>为单个账号开启或关闭 Smarter RP，不影响其他账号。</li>
          <li>为新角色扮演会话选择账号默认角色。</li>
          <li>绑定会话开始时默认可用的世界书。</li>
        </ul>
      </Card>
    </section>
  );
}

function CharactersPage() {
  const [characters, setCharacters] = useState([]);
  const [formValues, setFormValues] = useState(emptyCharacterForm);
  const [editingId, setEditingId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  async function loadCharacters() {
    setLoading(true);
    setError('');
    try {
      const data = await apiFetch('/api/characters');
      setCharacters(data?.characters || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadCharacters();
  }, []);

  function startEdit(character) {
    setEditingId(character.id);
    setFormValues({
      name: character.name || '',
      system_prompt: character.system_prompt || '',
    });
  }

  function resetForm() {
    setEditingId(null);
    setFormValues(emptyCharacterForm);
  }

  async function saveCharacter() {
    setSaving(true);
    setError('');
    const body = {
      name: formValues.name || '',
      system_prompt: formValues.system_prompt || '',
    };
    try {
      await apiFetch(editingId ? `/api/characters/${editingId}` : '/api/characters', {
        method: editingId ? 'PATCH' : 'POST',
        body: JSON.stringify(body),
      });
      resetForm();
      await loadCharacters();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function deleteCharacter(id) {
    setError('');
    try {
      await apiFetch(`/api/characters/${id}`, { method: 'DELETE' });
      if (editingId === id) {
        resetForm();
      }
      await loadCharacters();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <section className="page-panel management-panel">
      <div className="management-heading">
        <div>
          <Tag className="phase-tag">角色 API</Tag>
          <Title level={1}>角色</Title>
          <Paragraph>直接粘贴完整角色卡或角色 prompt，不需要拆分字段。</Paragraph>
        </div>
        <Button onClick={loadCharacters} loading={loading}>刷新</Button>
      </div>
      {error && <div className="error-banner">{error}</div>}
      <Row gutter={[18, 18]}>
        <Col xs={24} lg={10}>
          <Card className="feature-card list-card" bordered={false}>
            <Title level={3}>已保存角色</Title>
            {loading ? (
              <Spin />
            ) : characters.length === 0 ? (
              <Text type="secondary">还没有角色。</Text>
            ) : (
              <div className="record-list">
                {characters.map((character) => (
                  <div className="record-item" key={character.id}>
                    <div>
                      <Text strong>{character.name || '未命名角色'}</Text>
                      <Text className="record-meta">{character.id}</Text>
                      {character.aliases?.length > 0 && <Text className="record-meta">别名：{character.aliases.join(', ')}</Text>}
                    </div>
                    <Space wrap>
                      <Button size="small" onClick={() => startEdit(character)}>编辑</Button>
                      <Popconfirm title="确定删除这个角色吗？" onConfirm={() => deleteCharacter(character.id)}>
                        <Button size="small" danger>删除</Button>
                      </Popconfirm>
                    </Space>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </Col>
        <Col xs={24} lg={14}>
          <Card className="feature-card form-card" bordered={false}>
            <Space className="form-title-row" align="center">
              <Title level={3}>{editingId ? '编辑角色' : '创建角色'}</Title>
              {editingId && <Tag>{editingId}</Tag>}
            </Space>
            <Form layout="vertical">
              {characterTextFields.map(([field, label]) => (
                <Form.Item label={label} key={field} required={field === 'name'}>
                  {field === 'name' ? (
                    <Input value={formValues[field]} onChange={(event) => setFormValues({ ...formValues, [field]: event.target.value })} />
                  ) : (
                    <TextArea rows={16} placeholder="粘贴完整角色卡或角色 prompt" value={formValues[field]} onChange={(event) => setFormValues({ ...formValues, [field]: event.target.value })} />
                  )}
                </Form.Item>
              ))}
              <Space wrap>
                <Button type="primary" onClick={saveCharacter} loading={saving} disabled={!formValues.name.trim()}>
                  {editingId ? '保存修改' : '创建角色'}
                </Button>
                <Button onClick={resetForm}>清空表单</Button>
              </Space>
            </Form>
          </Card>
        </Col>
      </Row>
    </section>
  );
}


function LorebooksPage() {
  const [lorebooks, setLorebooks] = useState([]);
  const [entries, setEntries] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [selectedBookId, setSelectedBookId] = useState(null);
  const [bookForm, setBookForm] = useState(emptyLorebookForm);
  const [entryForm, setEntryForm] = useState(emptyEntryForm);
  const [editingBookId, setEditingBookId] = useState(null);
  const [editingEntryId, setEditingEntryId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [entriesLoading, setEntriesLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [entrySaving, setEntrySaving] = useState(false);
  const [error, setError] = useState('');
  const [importJson, setImportJson] = useState('');
  const [exportJson, setExportJson] = useState('');
  const [hitInput, setHitInput] = useState('');
  const [hitResult, setHitResult] = useState(null);
  const [hitSessionId, setHitSessionId] = useState('');
  const [assignAccountId, setAssignAccountId] = useState(undefined);
  const [assignSessionId, setAssignSessionId] = useState(undefined);

  const selectedBook = lorebooks.find((book) => book.id === selectedBookId);

  async function loadLorebooks() {
    setLoading(true);
    setError('');
    try {
      const [bookData, accountData, sessionData] = await Promise.allSettled([
        apiFetch('/api/lorebooks'),
        apiFetch('/api/accounts'),
        apiFetch('/api/sessions'),
      ]);
      if (bookData.status === 'rejected') {
        throw bookData.reason;
      }
      const nextBooks = bookData.value?.lorebooks || [];
      setLorebooks(nextBooks);
      setSelectedBookId((current) => (nextBooks.some((book) => book.id === current) ? current : nextBooks[0]?.id || null));
      if (accountData.status === 'fulfilled') {
        setAccounts(Array.isArray(accountData.value) ? accountData.value : []);
      }
      if (sessionData.status === 'fulfilled') {
        setSessions(Array.isArray(sessionData.value) ? sessionData.value : []);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadEntries(bookId) {
    if (!bookId) {
      setEntries([]);
      return;
    }
    setEntriesLoading(true);
    setError('');
    try {
      const data = await apiFetch(`/api/lorebooks/${bookId}/entries`);
      setEntries(data?.entries || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setEntriesLoading(false);
    }
  }

  useEffect(() => {
    loadLorebooks();
  }, []);

  useEffect(() => {
    loadEntries(selectedBookId);
    setEditingEntryId(null);
    setEntryForm(emptyEntryForm);
    setExportJson('');
    setHitResult(null);
  }, [selectedBookId]);

  function startBookEdit(book) {
    setEditingBookId(book.id);
    setBookForm({
      name: book.name || '',
      description: book.description || '',
      scope: book.scope || 'global',
      session_id: book.session_id || '',
    });
  }

  function resetBookForm() {
    setEditingBookId(null);
    setBookForm(emptyLorebookForm);
  }

  function startEntryEdit(entry) {
    setEditingEntryId(entry.id);
    setEntryForm({
      ...emptyEntryForm,
      ...Object.fromEntries(entryTextFields.map(([field]) => [field, entry[field] ?? emptyEntryForm[field]])),
      ...Object.fromEntries(entryListFields.map(([field]) => [field, listToLines(entry[field])])),
      ...Object.fromEntries(entryBoolFields.map(([field]) => [field, Boolean(entry[field])])),
      ...Object.fromEntries(entryNumberFields.map(([field]) => [field, entry[field] ?? emptyEntryForm[field]])),
    });
  }

  function resetEntryForm() {
    setEditingEntryId(null);
    setEntryForm(emptyEntryForm);
  }

  async function saveBook() {
    setSaving(true);
    setError('');
    const body = {
      name: bookForm.name,
      description: bookForm.description,
      scope: bookForm.scope,
      session_id: bookForm.scope === 'session' ? bookForm.session_id || null : null,
    };
    try {
      const saved = await apiFetch(editingBookId ? `/api/lorebooks/${editingBookId}` : '/api/lorebooks', {
        method: editingBookId ? 'PATCH' : 'POST',
        body: JSON.stringify(body),
      });
      resetBookForm();
      await loadLorebooks();
      setSelectedBookId(saved.id);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function deleteBook(id) {
    setError('');
    try {
      await apiFetch(`/api/lorebooks/${id}`, { method: 'DELETE' });
      if (editingBookId === id) {
        resetBookForm();
      }
      if (selectedBookId === id) {
        setSelectedBookId(null);
      }
      await loadLorebooks();
    } catch (err) {
      setError(err.message);
    }
  }

  async function saveEntry() {
    if (!selectedBookId) return;
    setEntrySaving(true);
    setError('');
    const integerValue = (field, fallback = 0) => {
      const value = Number(entryForm[field] ?? fallback);
      return Number.isFinite(value) ? Math.trunc(value) : fallback;
    };
    const body = {
      title: entryForm.title,
      content: entryForm.content,
      enabled: entryForm.enabled,
      constant: entryForm.constant,
      keys: linesToList(entryForm.keys || ''),
      secondary_keys: linesToList(entryForm.secondary_keys || ''),
      selective: entryForm.selective,
      regex: entryForm.regex,
      case_sensitive: entryForm.case_sensitive,
      position: entryForm.position,
      depth: integerValue('depth'),
      priority: integerValue('priority'),
      order: integerValue('order'),
      probability: Number(entryForm.probability ?? 1),
      cooldown_turns: integerValue('cooldown_turns'),
      sticky_turns: integerValue('sticky_turns'),
      recursive: entryForm.recursive,
      group: entryForm.group?.trim() || null,
      character_filter: linesToList(entryForm.character_filter || ''),
      max_injections_per_chat: entryForm.max_injections_per_chat === null || entryForm.max_injections_per_chat === undefined ? null : integerValue('max_injections_per_chat'),
    };
    try {
      await apiFetch(
        editingEntryId ? `/api/lorebooks/${selectedBookId}/entries/${editingEntryId}` : `/api/lorebooks/${selectedBookId}/entries`,
        {
          method: editingEntryId ? 'PATCH' : 'POST',
          body: JSON.stringify(body),
        }
      );
      resetEntryForm();
      await loadEntries(selectedBookId);
    } catch (err) {
      setError(err.message);
    } finally {
      setEntrySaving(false);
    }
  }

  async function deleteEntry(entryId) {
    if (!selectedBookId) return;
    setError('');
    try {
      await apiFetch(`/api/lorebooks/${selectedBookId}/entries/${entryId}`, { method: 'DELETE' });
      if (editingEntryId === entryId) {
        resetEntryForm();
      }
      await loadEntries(selectedBookId);
    } catch (err) {
      setError(err.message);
    }
  }

  async function importLorebook() {
    setError('');
    try {
      const imported = await apiFetch('/api/lorebooks/import', {
        method: 'POST',
        body: JSON.stringify(JSON.parse(importJson)),
      });
      setImportJson('');
      await loadLorebooks();
      setSelectedBookId(imported.id);
    } catch (err) {
      setError(err.message);
    }
  }

  async function exportLorebook() {
    if (!selectedBookId) return;
    setError('');
    try {
      const data = await apiFetch(`/api/lorebooks/${selectedBookId}/export`);
      setExportJson(JSON.stringify(data, null, 2));
    } catch (err) {
      setError(err.message);
    }
  }

  async function runHitTest() {
    if (!selectedBookId) return;
    setError('');
    try {
      const data = await apiFetch('/api/lorebooks/hit-test', {
        method: 'POST',
        body: JSON.stringify({
          lorebook_ids: [selectedBookId],
          input: hitInput,
          session_id: hitSessionId || selectedBook?.session_id || null,
        }),
      });
      setHitResult(data);
    } catch (err) {
      setError(err.message);
    }
  }

  async function assignLorebook(kind) {
    if (!selectedBookId) return;
    const targetId = kind === 'account' ? assignAccountId : assignSessionId;
    if (!targetId) return;
    setError('');
    try {
      await apiFetch(`/api/${kind === 'account' ? 'accounts' : 'sessions'}/${targetId}/lorebooks`, {
        method: 'PATCH',
        body: JSON.stringify({ lorebook_ids: [selectedBookId] }),
      });
      await loadLorebooks();
    } catch (err) {
      setError(err.message);
    }
  }

  const accountOptions = accounts.map((account) => ({
    value: account.id,
    label: account.display_name ? `${account.display_name} (${account.id})` : account.id,
  }));
  const sessionOptions = sessions.map((session) => ({
    value: session.id,
    label: session.unified_msg_origin ? `${session.unified_msg_origin} (${session.id})` : session.id,
  }));

  return (
    <section className="page-panel management-panel lorebooks-panel">
      <div className="management-heading">
        <div>
          <Tag className="phase-tag">世界书 API</Tag>
          <Title level={1}>世界书</Title>
          <Paragraph>管理世界设定、触发规则、导入导出和快速命中测试。</Paragraph>
        </div>
        <Button onClick={loadLorebooks} loading={loading}>刷新</Button>
      </div>
      {error && <div className="error-banner">{error}</div>}
      <Row gutter={[18, 18]}>
        <Col xs={24} lg={9}>
          <Card className="feature-card list-card" bordered={false}>
            <Title level={3}>已保存世界书</Title>
            {loading ? (
              <Spin />
            ) : lorebooks.length === 0 ? (
              <Text type="secondary">还没有世界书。</Text>
            ) : (
              <div className="record-list">
                {lorebooks.map((book) => (
                  <div
                    className={`record-item session-item ${selectedBookId === book.id ? 'selected' : ''}`}
                    key={book.id}
                  >
                    <div
                      className="record-select-area"
                      role="button"
                      tabIndex={0}
                      onClick={() => setSelectedBookId(book.id)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault();
                          setSelectedBookId(book.id);
                        }
                      }}
                    >
                      <Text strong>{book.name || '未命名世界书'}</Text>
                      <Text className="record-meta">{book.id}</Text>
                      <Text className="record-meta">{book.scope}{book.session_id ? ` · ${book.session_id}` : ''}</Text>
                    </div>
                    <Space wrap>
                      <Button size="small" onClick={() => startBookEdit(book)}>编辑</Button>
                      <Popconfirm title="确定删除这个世界书吗？" onConfirm={() => deleteBook(book.id)}>
                        <Button size="small" danger>删除</Button>
                      </Popconfirm>
                    </Space>
                  </div>
                ))}
              </div>
            )}
          </Card>
          <Card className="feature-card form-card compact-card" bordered={false}>
            <Space className="form-title-row" align="center">
              <Title level={3}>{editingBookId ? '编辑世界书' : '创建世界书'}</Title>
              {editingBookId && <Tag>{editingBookId}</Tag>}
            </Space>
            <Form layout="vertical">
              <Form.Item label="名称" required>
                <Input value={bookForm.name} onChange={(event) => setBookForm({ ...bookForm, name: event.target.value })} />
              </Form.Item>
              <Form.Item label="描述">
                <TextArea rows={2} value={bookForm.description} onChange={(event) => setBookForm({ ...bookForm, description: event.target.value })} />
              </Form.Item>
              <Form.Item label="作用域">
                <Select
                  options={[{ value: 'global', label: '全局' }, { value: 'session', label: '会话' }]}
                  value={bookForm.scope}
                  onChange={(value) => setBookForm({ ...bookForm, scope: value })}
                />
              </Form.Item>
              <Form.Item label="会话 ID">
                <Input value={bookForm.session_id} onChange={(event) => setBookForm({ ...bookForm, session_id: event.target.value })} disabled={bookForm.scope !== 'session'} />
              </Form.Item>
              <Space wrap>
                <Button type="primary" onClick={saveBook} loading={saving} disabled={!bookForm.name.trim()}>
                  {editingBookId ? '保存修改' : '创建世界书'}
                </Button>
                <Button onClick={resetBookForm}>清空表单</Button>
              </Space>
            </Form>
          </Card>
        </Col>
        <Col xs={24} lg={15}>
          <Card className="feature-card list-card" bordered={false}>
            <div className="section-heading-row">
              <Title level={3}>条目</Title>
              <Button onClick={() => loadEntries(selectedBookId)} loading={entriesLoading} disabled={!selectedBookId}>刷新条目</Button>
            </div>
            {!selectedBookId ? (
              <Text type="secondary">请选择一个世界书来管理条目。</Text>
            ) : entriesLoading ? (
              <Spin />
            ) : entries.length === 0 ? (
              <Text type="secondary">这个世界书还没有条目。</Text>
            ) : (
              <div className="record-list entry-list">
                {entries.map((entry) => (
                  <div className="record-item" key={entry.id}>
                    <div>
                      <Space wrap>
                        <Text strong>{entry.title || '未命名条目'}</Text>
                        <Tag color={entry.enabled ? 'green' : 'default'}>{entry.enabled ? '已启用' : '已禁用'}</Tag>
                        {entry.constant && <Tag color="blue">常驻</Tag>}
                      </Space>
                      <Text className="record-meta">{entry.id}</Text>
                      <Text className="record-meta">{entry.position} · 优先级 {entry.priority || 0} · 关键词 {(entry.keys || []).join(', ') || '无'}</Text>
                    </div>
                    <Space wrap>
                      <Button size="small" onClick={() => startEntryEdit(entry)}>编辑</Button>
                      <Popconfirm title="确定删除这个条目吗？" onConfirm={() => deleteEntry(entry.id)}>
                        <Button size="small" danger>删除</Button>
                      </Popconfirm>
                    </Space>
                  </div>
                ))}
              </div>
            )}
          </Card>
          <Card className="feature-card form-card compact-card" bordered={false}>
            <Space className="form-title-row" align="center">
              <Title level={3}>{editingEntryId ? '编辑条目' : '创建条目'}</Title>
              {editingEntryId && <Tag>{editingEntryId}</Tag>}
            </Space>
            <Form layout="vertical" className="entry-form-grid">
              <Form.Item label="标题" required>
                <Input value={entryForm.title} onChange={(event) => setEntryForm({ ...entryForm, title: event.target.value })} />
              </Form.Item>
              <Form.Item label="插入位置">
                <Select options={positionOptions} value={entryForm.position} onChange={(value) => setEntryForm({ ...entryForm, position: value })} />
              </Form.Item>
              <Form.Item label="内容" className="wide-field" required>
                <TextArea rows={4} value={entryForm.content} onChange={(event) => setEntryForm({ ...entryForm, content: event.target.value })} />
              </Form.Item>
              {entryListFields.map(([field, label]) => (
                <Form.Item label={`${label}（每行一项）`} key={field}>
                  <TextArea rows={3} value={entryForm[field]} onChange={(event) => setEntryForm({ ...entryForm, [field]: event.target.value })} />
                </Form.Item>
              ))}
              <Form.Item label="分组">
                <Input value={entryForm.group} onChange={(event) => setEntryForm({ ...entryForm, group: event.target.value })} />
              </Form.Item>
              {entryNumberFields.map(([field, label]) => (
                <Form.Item label={label} key={field}>
                  <InputNumber
                    className="full-width-input"
                    min={field === 'probability' ? 0 : undefined}
                    max={field === 'probability' ? 1 : undefined}
                    step={field === 'probability' ? 0.05 : 1}
                    precision={entryIntegerFields.has(field) ? 0 : undefined}
                    value={entryForm[field]}
                    onChange={(value) => setEntryForm({ ...entryForm, [field]: entryIntegerFields.has(field) && value !== null ? Math.trunc(value) : value })}
                  />
                </Form.Item>
              ))}
              <Form.Item label="标记" className="wide-field">
                <Space wrap>
                  {entryBoolFields.map(([field, label]) => (
                    <Checkbox key={field} checked={entryForm[field]} onChange={(event) => setEntryForm({ ...entryForm, [field]: event.target.checked })}>
                      {label}
                    </Checkbox>
                  ))}
                </Space>
              </Form.Item>
              <Form.Item className="wide-field">
                <Space wrap>
                  <Button type="primary" onClick={saveEntry} loading={entrySaving} disabled={!selectedBookId || !entryForm.title.trim() || !entryForm.content.trim()}>
                    {editingEntryId ? '保存条目' : '创建条目'}
                  </Button>
                  <Button onClick={resetEntryForm}>清空条目表单</Button>
                </Space>
              </Form.Item>
            </Form>
          </Card>
          <Row gutter={[18, 18]}>
            <Col xs={24} xl={12}>
              <Card className="feature-card compact-card" bordered={false}>
                <Title level={3}>导入 / 导出 JSON</Title>
                <TextArea className="json-panel" rows={8} value={importJson} onChange={(event) => setImportJson(event.target.value)} placeholder="粘贴要导入的世界书 JSON" />
                <Space wrap className="tool-row">
                  <Button onClick={importLorebook} disabled={!importJson.trim()}>导入 JSON</Button>
                  <Button onClick={exportLorebook} disabled={!selectedBookId}>导出所选</Button>
                </Space>
                {exportJson && <TextArea className="json-panel" rows={10} value={exportJson} readOnly />}
              </Card>
            </Col>
            <Col xs={24} xl={12}>
              <Card className="feature-card compact-card" bordered={false}>
                <Title level={3}>命中测试</Title>
                <TextArea rows={5} value={hitInput} onChange={(event) => setHitInput(event.target.value)} placeholder="输入当前用户发言，用所选世界书测试命中" />
                <Select
                  allowClear
                  className="full-width-input tool-row"
                  placeholder="可选会话上下文"
                  options={sessionOptions}
                  value={hitSessionId || undefined}
                  onChange={(value) => setHitSessionId(value || '')}
                />
                <Button onClick={runHitTest} disabled={!selectedBookId || !hitInput.trim()}>运行命中测试</Button>
                {hitResult && (
                  <pre className="hit-test-output">{JSON.stringify({ hits: hitResult.hits, filtered: hitResult.filtered, buckets: hitResult.buckets }, null, 2)}</pre>
                )}
              </Card>
            </Col>
          </Row>
          {(accountOptions.length > 0 || sessionOptions.length > 0) && (
            <Card className="feature-card compact-card" bordered={false}>
              <Title level={3}>分配所选世界书</Title>
              <Row gutter={[12, 12]}>
                {accountOptions.length > 0 && (
                  <Col xs={24} md={12}>
                    <Space direction="vertical" className="assignment-control">
                      <Text className="control-label">账号默认世界书</Text>
                      <Select allowClear options={accountOptions} value={assignAccountId} onChange={setAssignAccountId} placeholder="选择账号" />
                      <Button onClick={() => assignLorebook('account')} disabled={!selectedBookId || !assignAccountId}>设置账号 lorebook_ids</Button>
                    </Space>
                  </Col>
                )}
                {sessionOptions.length > 0 && (
                  <Col xs={24} md={12}>
                    <Space direction="vertical" className="assignment-control">
                      <Text className="control-label">会话启用世界书</Text>
                      <Select allowClear options={sessionOptions} value={assignSessionId} onChange={setAssignSessionId} placeholder="选择会话" />
                      <Button onClick={() => assignLorebook('session')} disabled={!selectedBookId || !assignSessionId}>设置会话 lorebook_ids</Button>
                    </Space>
                  </Col>
                )}
              </Row>
            </Card>
          )}
        </Col>
      </Row>
    </section>
  );
}

function SessionsPage() {
  const [sessions, setSessions] = useState([]);
  const [characters, setCharacters] = useState([]);
  const [selectedSessionId, setSelectedSessionId] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [error, setError] = useState('');

  async function loadSessions() {
    setLoading(true);
    setError('');
    try {
      const [sessionData, characterData] = await Promise.all([
        apiFetch('/api/sessions'),
        apiFetch('/api/characters'),
      ]);
      const nextSessions = Array.isArray(sessionData) ? sessionData : [];
      setSessions(nextSessions);
      setCharacters(characterData?.characters || []);
      setSelectedSessionId((current) => current || nextSessions[0]?.id || null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadHistory(sessionId) {
    if (!sessionId) {
      setHistory([]);
      return;
    }
    setHistoryLoading(true);
    setError('');
    try {
      const data = await apiFetch(`/api/sessions/${sessionId}/history?limit=20`);
      setHistory(data?.messages || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setHistoryLoading(false);
    }
  }

  useEffect(() => {
    loadSessions();
  }, []);

  useEffect(() => {
    loadHistory(selectedSessionId);
  }, [selectedSessionId]);

  async function patchSession(sessionId, updates) {
    setError('');
    try {
      const updated = await apiFetch(`/api/sessions/${sessionId}`, {
        method: 'PATCH',
        body: JSON.stringify(updates),
      });
      setSessions((current) => current.map((session) => (session.id === sessionId ? updated : session)));
    } catch (err) {
      setError(err.message);
    }
  }

  async function clearHistory() {
    if (!selectedSessionId) return;
    setError('');
    try {
      await apiFetch(`/api/sessions/${selectedSessionId}/history`, { method: 'DELETE' });
      await loadHistory(selectedSessionId);
      await loadSessions();
    } catch (err) {
      setError(err.message);
    }
  }

  async function undoLatestTurn() {
    if (!selectedSessionId) return;
    setError('');
    try {
      await apiFetch(`/api/sessions/${selectedSessionId}/history/undo`, { method: 'POST' });
      await loadHistory(selectedSessionId);
      await loadSessions();
    } catch (err) {
      setError(err.message);
    }
  }

  const selectedSession = sessions.find((session) => session.id === selectedSessionId);
  const characterOptions = characters.map((character) => ({
    value: character.id,
    label: character.name ? `${character.name} (${character.id})` : character.id,
  }));

  return (
    <section className="page-panel management-panel">
      <div className="management-heading">
        <div>
          <Tag className="phase-tag">会话 API</Tag>
          <Title level={1}>会话</Title>
          <Paragraph>分配当前角色、暂停或恢复 RP，并管理最近的会话历史。</Paragraph>
        </div>
        <Button onClick={loadSessions} loading={loading}>刷新</Button>
      </div>
      {error && <div className="error-banner">{error}</div>}
      <Row gutter={[18, 18]}>
        <Col xs={24} lg={11}>
          <Card className="feature-card list-card" bordered={false}>
            <Title level={3}>当前会话</Title>
            {loading ? (
              <Spin />
            ) : sessions.length === 0 ? (
              <Text type="secondary">还没有会话。</Text>
            ) : (
              <div className="record-list">
                {sessions.map((session) => (
                  <button
                    className={`record-item session-item ${selectedSessionId === session.id ? 'selected' : ''}`}
                    key={session.id}
                    type="button"
                    onClick={() => setSelectedSessionId(session.id)}
                  >
                    <div>
                      <Text strong>{session.unified_msg_origin || session.id}</Text>
                      <Text className="record-meta">{session.id}</Text>
                      <Text className="record-meta">轮次：{session.turn_count || 0}</Text>
                    </div>
                    <Tag color={session.paused ? 'gold' : 'green'}>{session.paused ? '已暂停' : '运行中'}</Tag>
                  </button>
                ))}
              </div>
            )}
          </Card>
        </Col>
        <Col xs={24} lg={13}>
          <Card className="feature-card form-card" bordered={false}>
            <Title level={3}>会话控制</Title>
            {selectedSession ? (
              <Space direction="vertical" size="middle" className="session-controls">
                <div>
                  <Text className="control-label">当前角色</Text>
                  <Select
                    allowClear
                    placeholder="未设置当前角色"
                    options={characterOptions}
                    value={selectedSession.active_character_id || undefined}
                    onChange={(value) => patchSession(selectedSession.id, { active_character_id: value || null })}
                  />
                </div>
                <Space wrap>
                  <Button icon={<PauseCircleOutlined />} onClick={() => patchSession(selectedSession.id, { paused: !selectedSession.paused })}>
                    {selectedSession.paused ? '恢复 RP' : '暂停 RP'}
                  </Button>
                  <Button onClick={() => loadHistory(selectedSession.id)} loading={historyLoading}>刷新历史</Button>
                  <Popconfirm title="确定清空当前可见历史吗？" onConfirm={clearHistory}>
                    <Button danger>清空历史</Button>
                  </Popconfirm>
                  <Button onClick={undoLatestTurn}>撤销最新轮次</Button>
                </Space>
              </Space>
            ) : (
              <Text type="secondary">请选择一个会话来管理控制项和历史。</Text>
            )}
          </Card>
          <Card className="feature-card history-card" bordered={false}>
            <Title level={3}>最近历史</Title>
            {historyLoading ? (
              <Spin />
            ) : history.length === 0 ? (
              <Text type="secondary">这个会话还没有历史消息。</Text>
            ) : (
              <div className="history-list">
                {history.map((message) => (
                  <div className="history-message" key={message.id}>
                    <Space className="history-message-head" wrap>
                      <Tag color={message.role === 'assistant' ? 'green' : message.role === 'system' ? 'blue' : 'gold'}>{message.role}</Tag>
                      <Text strong>{message.speaker || '未知'}</Text>
                      <Text className="record-meta">轮次 {message.turn_number}</Text>
                    </Space>
                    <Paragraph>{message.content}</Paragraph>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </Col>
      </Row>
    </section>
  );
}

function MemoryPage() {
  const [sessions, setSessions] = useState([]);
  const [selectedSessionId, setSelectedSessionId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState('');

  async function loadSessions() {
    setLoading(true);
    setError('');
    try {
      const data = await apiFetch('/api/memory/sessions');
      const nextSessions = Array.isArray(data) ? data : [];
      setSessions(nextSessions);
      setSelectedSessionId((current) => (nextSessions.some((session) => session.id === current) ? current : nextSessions[0]?.id || null));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadDetail(sessionId) {
    if (!sessionId) {
      setDetail(null);
      return;
    }
    setDetailLoading(true);
    setError('');
    try {
      setDetail(await apiFetch(`/api/memory/sessions/${sessionId}`));
    } catch (err) {
      setError(err.message);
    } finally {
      setDetailLoading(false);
    }
  }

  useEffect(() => {
    loadSessions();
  }, []);

  useEffect(() => {
    loadDetail(selectedSessionId);
  }, [selectedSessionId]);

  async function deleteMemory(memoryId) {
    setError('');
    try {
      await apiFetch(`/api/memory/memories/${memoryId}`, { method: 'DELETE' });
      await loadDetail(selectedSessionId);
      await loadSessions();
    } catch (err) {
      setError(err.message);
    }
  }

  async function clearSessionMemory() {
    if (!selectedSessionId) return;
    setError('');
    try {
      await apiFetch(`/api/memory/sessions/${selectedSessionId}`, { method: 'DELETE' });
      await loadDetail(selectedSessionId);
      await loadSessions();
    } catch (err) {
      setError(err.message);
    }
  }

  const status = detail?.status || sessions.find((session) => session.id === selectedSessionId);
  const memories = detail?.memories || [];

  return (
    <section className="page-panel management-panel">
      <div className="management-heading">
        <div>
          <Tag className="phase-tag">记忆 API</Tag>
          <Title level={1}>记忆</Title>
          <Paragraph>查看会话摘要、结构化状态、检索命中和事件记忆。</Paragraph>
        </div>
        <Button onClick={loadSessions} loading={loading}>刷新</Button>
      </div>
      {error && <div className="error-banner">{error}</div>}
      <Row gutter={[18, 18]}>
        <Col xs={24} lg={9}>
          <Card className="feature-card list-card" bordered={false}>
            <Title level={3}>记忆会话</Title>
            {loading ? (
              <Spin />
            ) : sessions.length === 0 ? (
              <Text type="secondary">还没有记忆会话。</Text>
            ) : (
              <div className="record-list">
                {sessions.map((session) => (
                  <button
                    className={`record-item session-item ${selectedSessionId === session.id ? 'selected' : ''}`}
                    key={session.id}
                    type="button"
                    onClick={() => setSelectedSessionId(session.id)}
                  >
                    <div>
                      <Text strong>{session.unified_msg_origin || session.id}</Text>
                      <Text className="record-meta">{session.id}</Text>
                      <Text className="record-meta">记忆：{session.memory_count || 0} · 轮次：{session.turn_count || 0}</Text>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </Card>
        </Col>
        <Col xs={24} lg={15}>
          <Card className="feature-card form-card" bordered={false}>
            <div className="section-heading-row">
              <Title level={3}>会话记忆状态</Title>
              <Space wrap>
                <Button onClick={() => loadDetail(selectedSessionId)} loading={detailLoading} disabled={!selectedSessionId}>刷新详情</Button>
                <Popconfirm title="确定清空这个会话的全部记忆吗？" onConfirm={clearSessionMemory}>
                  <Button danger disabled={!selectedSessionId}>清空会话记忆</Button>
                </Popconfirm>
              </Space>
            </div>
            {!status ? (
              <Text type="secondary">请选择一个会话来查看记忆。</Text>
            ) : detailLoading ? (
              <Spin />
            ) : (
              <Space direction="vertical" className="session-controls" size="middle">
                <div>
                  <Text strong>{status.unified_msg_origin || status.id}</Text>
                  <Text className="record-meta">{status.id}</Text>
                </div>
                <div>
                  <Text className="control-label">摘要</Text>
                  <Paragraph>{status.summary || '尚未保存摘要。'}</Paragraph>
                </div>
                <div>
                  <Text className="control-label">状态 JSON</Text>
                  <pre className="hit-test-output">{JSON.stringify(status.state || {}, null, 2)}</pre>
                </div>
                <div>
                  <Text className="control-label">最近记忆命中 JSON</Text>
                  <pre className="hit-test-output">{JSON.stringify(status.last_memory_hits || [], null, 2)}</pre>
                </div>
              </Space>
            )}
          </Card>
          <Card className="feature-card history-card" bordered={false}>
            <Title level={3}>事件记忆</Title>
            {detailLoading ? (
              <Spin />
            ) : memories.length === 0 ? (
              <Text type="secondary">这个会话还没有事件记忆。</Text>
            ) : (
              <div className="record-list">
                {memories.map((memory) => (
                  <div className="record-item" key={memory.id}>
                    <div>
                      <Space wrap>
                        <Text strong>{memory.content}</Text>
                        <Tag color="green">{memory.type}</Tag>
                        <Tag>重要性 {memory.importance}</Tag>
                        <Tag>置信度 {memory.confidence}</Tag>
                      </Space>
                      <Text className="record-meta">{memory.id}</Text>
                      <Text className="record-meta">轮次 {memory.turn_range?.join('-') || '无'} · 来源 {(memory.source_message_ids || []).join(', ') || '无'}</Text>
                    </div>
                    <Popconfirm title="确定删除这条记忆吗？" onConfirm={() => deleteMemory(memory.id)}>
                      <Button size="small" danger>删除</Button>
                    </Popconfirm>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </Col>
      </Row>
    </section>
  );
}

function DebugPage() {
  const [sessions, setSessions] = useState([]);
  const [selectedSessionId, setSelectedSessionId] = useState('');
  const [snapshots, setSnapshots] = useState([]);
  const [memoryTraces, setMemoryTraces] = useState([]);
  const [toolTraces, setToolTraces] = useState([]);
  const [loreHits, setLoreHits] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function loadDebug() {
    setLoading(true);
    setError('');
    try {
      const [sessionResult, snapshotResult, memoryResult, toolResult] = await Promise.allSettled([
        apiFetch('/api/sessions'),
        apiFetch('/api/debug/snapshots'),
        apiFetch('/api/debug/memory'),
        apiFetch('/api/debug/tools'),
      ]);
      if (snapshotResult.status === 'rejected') {
        throw snapshotResult.reason;
      }
      if (memoryResult.status === 'rejected') {
        throw memoryResult.reason;
      }
      if (toolResult.status === 'rejected') {
        throw toolResult.reason;
      }
      const nextSessions = sessionResult.status === 'fulfilled' && Array.isArray(sessionResult.value) ? sessionResult.value : [];
      setSessions(nextSessions);
      setSelectedSessionId((current) => (current && nextSessions.some((session) => session.id === current) ? current : nextSessions[0]?.id || ''));
      setSnapshots((snapshotResult.value || []).filter((snapshot) => snapshot.type === 'prompt' || snapshot.type === 'raw_request'));
      setMemoryTraces(memoryResult.value || []);
      setToolTraces(toolResult.value || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadLoreHits(sessionId) {
    if (!sessionId) {
      setLoreHits([]);
      return;
    }
    setError('');
    try {
      const data = await apiFetch(`/api/debug/lore-hits?session_id=${encodeURIComponent(sessionId)}`);
      setLoreHits(data?.hits || []);
    } catch (err) {
      setError(err.message);
      setLoreHits([]);
    }
  }

  useEffect(() => {
    loadDebug();
  }, []);

  useEffect(() => {
    loadLoreHits(selectedSessionId);
  }, [selectedSessionId]);

  const sessionOptions = sessions.map((session) => ({
    value: session.id,
    label: session.unified_msg_origin ? `${session.unified_msg_origin} (${session.id})` : session.id,
  }));

  return (
    <section className="page-panel management-panel">
      <div className="management-heading">
        <div>
          <Tag className="phase-tag">调试 API</Tag>
          <Title level={1}>调试</Title>
          <Paragraph>查看提示词快照、原始请求快照、记忆轨迹、工具轨迹和世界书命中。</Paragraph>
        </div>
        <Button onClick={loadDebug} loading={loading}>刷新</Button>
      </div>
      {error && <div className="error-banner">{error}</div>}
      <Row gutter={[18, 18]}>
        <Col xs={24} lg={12}>
          <Card className="feature-card list-card" bordered={false}>
            <Title level={3}>提示词 / 原始请求快照</Title>
            {loading ? (
              <Spin />
            ) : snapshots.length === 0 ? (
              <Text type="secondary">还没有提示词或原始请求快照。</Text>
            ) : (
              <div className="record-list">
                {snapshots.map((snapshot) => (
                  <div className="history-message" key={snapshot.id}>
                    <Space className="history-message-head" wrap>
                      <Tag color={snapshot.type === 'prompt' ? 'green' : 'blue'}>{snapshot.type}</Tag>
                      <Text className="record-meta">{snapshot.session_id || '全局'} · {snapshot.id}</Text>
                    </Space>
                    <pre className="hit-test-output">{snapshot.content}</pre>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card className="feature-card list-card" bordered={false}>
            <Title level={3}>记忆轨迹</Title>
            {loading ? (
              <Spin />
            ) : memoryTraces.length === 0 ? (
              <Text type="secondary">还没有记忆调试轨迹。</Text>
            ) : (
              <div className="record-list">
                {memoryTraces.map((snapshot) => (
                  <div className="history-message" key={snapshot.id}>
                    <Space className="history-message-head" wrap>
                      <Tag color="purple">memory</Tag>
                      <Text className="record-meta">{snapshot.session_id || '全局'} · {snapshot.id}</Text>
                    </Space>
                    <pre className="hit-test-output">{snapshot.content}</pre>
                  </div>
                ))}
              </div>
            )}
          </Card>
          <Card className="feature-card compact-card" bordered={false}>
            <Title level={3}>工具轨迹</Title>
            {loading ? (
              <Spin />
            ) : toolTraces.length === 0 ? (
              <Text type="secondary">还没有工具调试轨迹。</Text>
            ) : (
              <div className="record-list">
                {toolTraces.map((snapshot) => (
                  <div className="history-message" key={snapshot.id}>
                    <Space className="history-message-head" wrap>
                      <Tag color="cyan">tools</Tag>
                      <Text className="record-meta">{snapshot.session_id || '全局'} · {snapshot.id}</Text>
                    </Space>
                    <pre className="hit-test-output">{snapshot.content}</pre>
                  </div>
                ))}
              </div>
            )}
          </Card>
          <Card className="feature-card compact-card" bordered={false}>
            <Title level={3}>世界书命中</Title>
            <Select
              allowClear
              className="full-width-input"
              placeholder="选择会话"
              options={sessionOptions}
              value={selectedSessionId || undefined}
              onChange={(value) => setSelectedSessionId(value || '')}
            />
            <pre className="hit-test-output">{JSON.stringify(loreHits, null, 2)}</pre>
          </Card>
        </Col>
      </Row>
    </section>
  );
}

function PlaceholderPage() {
  return (
    <section className="page-panel placeholder-panel">
      <Tag className="phase-tag">WebUI</Tag>
      <Title level={1}>页面不可用</Title>
      <Paragraph>请从侧边栏选择一个管理区域。</Paragraph>
    </section>
  );
}

function App() {
  const [selectedPage, setSelectedPage] = useState('dashboard');

  const content = useMemo(() => {
    if (selectedPage === 'dashboard') {
      return <DashboardPage />;
    }
    if (selectedPage === 'accounts') {
      return <AccountsPage />;
    }
    if (selectedPage === 'characters') {
      return <CharactersPage />;
    }
    if (selectedPage === 'lorebooks') {
      return <LorebooksPage />;
    }
    if (selectedPage === 'sessions') {
      return <SessionsPage />;
    }
    if (selectedPage === 'memory') {
      return <MemoryPage />;
    }
    if (selectedPage === 'debug') {
      return <DebugPage />;
    }
    return <PlaceholderPage />;
  }, [selectedPage]);

  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: theme.darkAlgorithm,
        token: {
          colorPrimary: '#68d391',
          borderRadius: 14,
          fontFamily: 'Avenir Next, Helvetica Neue, sans-serif',
        },
      }}
    >
      <Layout className="app-shell">
        <Sider className="app-sider" width={248}>
          <div className="brand">
            <div className="brand-mark">SR</div>
            <div>
              <Text className="brand-title">Smarter RP</Text>
              <Text className="brand-subtitle">AstrBot 插件</Text>
            </div>
          </div>
          <Menu
            className="nav-menu"
            mode="inline"
            selectedKeys={[selectedPage]}
            onClick={({ key }) => setSelectedPage(key)}
            items={menuItems}
          />
        </Sider>
        <Layout>
          <Header className="app-header">
            <Menu
              className="mobile-nav-menu"
              mode="horizontal"
              selectedKeys={[selectedPage]}
              onClick={({ key }) => setSelectedPage(key)}
              items={menuItems}
            />
            <Space className="header-tags" size="small">
              <Tag color="green">默认启用</Tag>
              <Tag color="blue">Phase 2 API</Tag>
              <Tag color="purple">Bearer 令牌</Tag>
            </Space>
          </Header>
          <Content className="app-content">{content}</Content>
        </Layout>
      </Layout>
    </ConfigProvider>
  );
}

export default App;
