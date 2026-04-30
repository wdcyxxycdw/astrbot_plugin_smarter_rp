import { useEffect, useMemo, useState } from 'react';
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
  { key: 'dashboard', icon: <DashboardOutlined />, label: 'Dashboard' },
  { key: 'accounts', icon: <UserOutlined />, label: 'Accounts' },
  { key: 'characters', icon: <UserSwitchOutlined />, label: 'Characters' },
  { key: 'lorebooks', icon: <ReadOutlined />, label: 'Lorebooks' },
  { key: 'sessions', icon: <TeamOutlined />, label: 'Sessions' },
  { key: 'memory', icon: <DatabaseOutlined />, label: 'Memory' },
  { key: 'debug', icon: <BugOutlined />, label: 'Debug' },
];

const pageCopy = {
  memory: {
    tag: 'Phase 1 shell',
    title: 'Memory will surface session context safely',
    description:
      'Memory inspection is reserved for the upcoming backend integration. This placeholder keeps the WebUI route visible without fetching data.',
  },
  debug: {
    tag: 'Phase 1 shell',
    title: 'Debug signals will appear here',
    description:
      'Debug output and diagnostics stay behind this pane while token handling and API access are finalized.',
  },
};

const characterTextFields = [
  ['name', 'Name'],
  ['system_prompt', 'System prompt'],
  ['description', 'Description'],
  ['personality', 'Personality'],
  ['scenario', 'Scenario'],
  ['first_message', 'First message'],
  ['speaking_style', 'Speaking style'],
  ['post_history_prompt', 'Post-history prompt'],
  ['author_note', 'Author note'],
];

const characterListFields = [
  ['aliases', 'Aliases'],
  ['alternate_greetings', 'Alternate greetings'],
  ['linked_lorebook_ids', 'Linked lorebook IDs'],
];

const emptyCharacterForm = Object.fromEntries(
  [...characterTextFields, ...characterListFields].map(([field]) => [field, ''])
);


const entryTextFields = [
  ['title', 'Title'],
  ['content', 'Content'],
  ['position', 'Position'],
  ['group', 'Group'],
];

const entryListFields = [
  ['keys', 'Keys'],
  ['secondary_keys', 'Secondary keys'],
  ['character_filter', 'Character filter'],
];

const entryBoolFields = [
  ['enabled', 'Enabled'],
  ['constant', 'Constant'],
  ['selective', 'Selective'],
  ['regex', 'Regex'],
  ['case_sensitive', 'Case sensitive'],
  ['recursive', 'Recursive'],
];

const entryNumberFields = [
  ['depth', 'Depth'],
  ['priority', 'Priority'],
  ['order', 'Order'],
  ['probability', 'Probability'],
  ['cooldown_turns', 'Cooldown turns'],
  ['sticky_turns', 'Sticky turns'],
  ['max_injections_per_chat', 'Max injections per chat'],
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

async function apiFetch(path, options = {}) {
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
  const cards = [
    {
      title: 'Default-on',
      value: 'Enabled',
      tone: 'green',
      icon: <CheckCircleOutlined />,
      description: 'Smarter RP is designed to start active by default for configured conversations.',
    },
    {
      title: 'Accounts',
      value: 'Ready',
      tone: 'blue',
      icon: <UserOutlined />,
      description: 'Per-account enablement, default character, and default lorebooks will be managed here.',
    },
    {
      title: 'Sessions',
      value: 'Prepared',
      tone: 'gold',
      icon: <TeamOutlined />,
      description: 'Active chat sessions will show pause state, character binding, and lorebook binding.',
    },
  ];

  return (
    <section className="page-panel dashboard-panel">
      <div className="hero-copy">
        <Tag className="phase-tag">Phase 1</Tag>
        <Title level={1}>Smarter RP control room</Title>
        <Paragraph>
          A static WebUI shell for account defaults, session state, and upcoming authenticated management flows. No API calls are made in this phase.
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
    </section>
  );
}

function AccountsPage() {
  return (
    <section className="page-panel split-panel">
      <div>
        <Tag className="phase-tag">Accounts</Tag>
        <Title level={1}>Account defaults without surprises</Title>
        <Paragraph>
          This page will let operators enable or disable Smarter RP per account while preserving the default-on behavior for normal use.
        </Paragraph>
      </div>
      <Card className="feature-card" bordered={false}>
        <Title level={3}>Planned controls</Title>
        <ul className="feature-list">
          <li>Toggle Smarter RP for an account without affecting other accounts.</li>
          <li>Choose the account default character for new roleplay sessions.</li>
          <li>Attach default lorebooks that should be available when sessions start.</li>
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
      ...Object.fromEntries(characterTextFields.map(([field]) => [field, character[field] || ''])),
      ...Object.fromEntries(characterListFields.map(([field]) => [field, listToLines(character[field])])),
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
      ...Object.fromEntries(characterTextFields.map(([field]) => [field, formValues[field] || ''])),
      ...Object.fromEntries(characterListFields.map(([field]) => [field, linesToList(formValues[field] || '')])),
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
          <Tag className="phase-tag">Characters API</Tag>
          <Title level={1}>Characters</Title>
          <Paragraph>Manage rich roleplay character profiles. Multi-value fields use one item per line.</Paragraph>
        </div>
        <Button onClick={loadCharacters} loading={loading}>Refresh</Button>
      </div>
      {error && <div className="error-banner">{error}</div>}
      <Row gutter={[18, 18]}>
        <Col xs={24} lg={10}>
          <Card className="feature-card list-card" bordered={false}>
            <Title level={3}>Saved characters</Title>
            {loading ? (
              <Spin />
            ) : characters.length === 0 ? (
              <Text type="secondary">No characters yet.</Text>
            ) : (
              <div className="record-list">
                {characters.map((character) => (
                  <div className="record-item" key={character.id}>
                    <div>
                      <Text strong>{character.name || 'Unnamed character'}</Text>
                      <Text className="record-meta">{character.id}</Text>
                      {character.aliases?.length > 0 && <Text className="record-meta">Aliases: {character.aliases.join(', ')}</Text>}
                    </div>
                    <Space wrap>
                      <Button size="small" onClick={() => startEdit(character)}>Edit</Button>
                      <Popconfirm title="Delete this character?" onConfirm={() => deleteCharacter(character.id)}>
                        <Button size="small" danger>Delete</Button>
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
              <Title level={3}>{editingId ? 'Edit character' : 'Create character'}</Title>
              {editingId && <Tag>{editingId}</Tag>}
            </Space>
            <Form layout="vertical">
              {characterTextFields.map(([field, label]) => (
                <Form.Item label={label} key={field} required={field === 'name'}>
                  {field === 'name' ? (
                    <Input value={formValues[field]} onChange={(event) => setFormValues({ ...formValues, [field]: event.target.value })} />
                  ) : (
                    <TextArea rows={field === 'first_message' ? 3 : 2} value={formValues[field]} onChange={(event) => setFormValues({ ...formValues, [field]: event.target.value })} />
                  )}
                </Form.Item>
              ))}
              {characterListFields.map(([field, label]) => (
                <Form.Item label={`${label} (one per line)`} key={field}>
                  <TextArea rows={3} value={formValues[field]} onChange={(event) => setFormValues({ ...formValues, [field]: event.target.value })} />
                </Form.Item>
              ))}
              <Space wrap>
                <Button type="primary" onClick={saveCharacter} loading={saving} disabled={!formValues.name.trim()}>
                  {editingId ? 'Save changes' : 'Create character'}
                </Button>
                <Button onClick={resetForm}>Clear form</Button>
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
          <Tag className="phase-tag">Lorebooks API</Tag>
          <Title level={1}>Lorebooks</Title>
          <Paragraph>Manage world facts, trigger rules, import/export, and quick matching tests.</Paragraph>
        </div>
        <Button onClick={loadLorebooks} loading={loading}>Refresh</Button>
      </div>
      {error && <div className="error-banner">{error}</div>}
      <Row gutter={[18, 18]}>
        <Col xs={24} lg={9}>
          <Card className="feature-card list-card" bordered={false}>
            <Title level={3}>Saved lorebooks</Title>
            {loading ? (
              <Spin />
            ) : lorebooks.length === 0 ? (
              <Text type="secondary">No lorebooks yet.</Text>
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
                      <Text strong>{book.name || 'Unnamed lorebook'}</Text>
                      <Text className="record-meta">{book.id}</Text>
                      <Text className="record-meta">{book.scope}{book.session_id ? ` · ${book.session_id}` : ''}</Text>
                    </div>
                    <Space wrap>
                      <Button size="small" onClick={() => startBookEdit(book)}>Edit</Button>
                      <Popconfirm title="Delete this lorebook?" onConfirm={() => deleteBook(book.id)}>
                        <Button size="small" danger>Delete</Button>
                      </Popconfirm>
                    </Space>
                  </div>
                ))}
              </div>
            )}
          </Card>
          <Card className="feature-card form-card compact-card" bordered={false}>
            <Space className="form-title-row" align="center">
              <Title level={3}>{editingBookId ? 'Edit lorebook' : 'Create lorebook'}</Title>
              {editingBookId && <Tag>{editingBookId}</Tag>}
            </Space>
            <Form layout="vertical">
              <Form.Item label="Name" required>
                <Input value={bookForm.name} onChange={(event) => setBookForm({ ...bookForm, name: event.target.value })} />
              </Form.Item>
              <Form.Item label="Description">
                <TextArea rows={2} value={bookForm.description} onChange={(event) => setBookForm({ ...bookForm, description: event.target.value })} />
              </Form.Item>
              <Form.Item label="Scope">
                <Select
                  options={[{ value: 'global', label: 'global' }, { value: 'session', label: 'session' }]}
                  value={bookForm.scope}
                  onChange={(value) => setBookForm({ ...bookForm, scope: value })}
                />
              </Form.Item>
              <Form.Item label="Session ID">
                <Input value={bookForm.session_id} onChange={(event) => setBookForm({ ...bookForm, session_id: event.target.value })} disabled={bookForm.scope !== 'session'} />
              </Form.Item>
              <Space wrap>
                <Button type="primary" onClick={saveBook} loading={saving} disabled={!bookForm.name.trim()}>
                  {editingBookId ? 'Save changes' : 'Create lorebook'}
                </Button>
                <Button onClick={resetBookForm}>Clear form</Button>
              </Space>
            </Form>
          </Card>
        </Col>
        <Col xs={24} lg={15}>
          <Card className="feature-card list-card" bordered={false}>
            <div className="section-heading-row">
              <Title level={3}>Entries</Title>
              <Button onClick={() => loadEntries(selectedBookId)} loading={entriesLoading} disabled={!selectedBookId}>Refresh entries</Button>
            </div>
            {!selectedBookId ? (
              <Text type="secondary">Select a lorebook to manage entries.</Text>
            ) : entriesLoading ? (
              <Spin />
            ) : entries.length === 0 ? (
              <Text type="secondary">No entries in this lorebook.</Text>
            ) : (
              <div className="record-list entry-list">
                {entries.map((entry) => (
                  <div className="record-item" key={entry.id}>
                    <div>
                      <Space wrap>
                        <Text strong>{entry.title || 'Untitled entry'}</Text>
                        <Tag color={entry.enabled ? 'green' : 'default'}>{entry.enabled ? 'Enabled' : 'Disabled'}</Tag>
                        {entry.constant && <Tag color="blue">Constant</Tag>}
                      </Space>
                      <Text className="record-meta">{entry.id}</Text>
                      <Text className="record-meta">{entry.position} · priority {entry.priority || 0} · keys {(entry.keys || []).join(', ') || 'none'}</Text>
                    </div>
                    <Space wrap>
                      <Button size="small" onClick={() => startEntryEdit(entry)}>Edit</Button>
                      <Popconfirm title="Delete this entry?" onConfirm={() => deleteEntry(entry.id)}>
                        <Button size="small" danger>Delete</Button>
                      </Popconfirm>
                    </Space>
                  </div>
                ))}
              </div>
            )}
          </Card>
          <Card className="feature-card form-card compact-card" bordered={false}>
            <Space className="form-title-row" align="center">
              <Title level={3}>{editingEntryId ? 'Edit entry' : 'Create entry'}</Title>
              {editingEntryId && <Tag>{editingEntryId}</Tag>}
            </Space>
            <Form layout="vertical" className="entry-form-grid">
              <Form.Item label="Title" required>
                <Input value={entryForm.title} onChange={(event) => setEntryForm({ ...entryForm, title: event.target.value })} />
              </Form.Item>
              <Form.Item label="Position">
                <Select options={positionOptions} value={entryForm.position} onChange={(value) => setEntryForm({ ...entryForm, position: value })} />
              </Form.Item>
              <Form.Item label="Content" className="wide-field" required>
                <TextArea rows={4} value={entryForm.content} onChange={(event) => setEntryForm({ ...entryForm, content: event.target.value })} />
              </Form.Item>
              {entryListFields.map(([field, label]) => (
                <Form.Item label={`${label} (one per line)`} key={field}>
                  <TextArea rows={3} value={entryForm[field]} onChange={(event) => setEntryForm({ ...entryForm, [field]: event.target.value })} />
                </Form.Item>
              ))}
              <Form.Item label="Group">
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
              <Form.Item label="Flags" className="wide-field">
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
                    {editingEntryId ? 'Save entry' : 'Create entry'}
                  </Button>
                  <Button onClick={resetEntryForm}>Clear entry form</Button>
                </Space>
              </Form.Item>
            </Form>
          </Card>
          <Row gutter={[18, 18]}>
            <Col xs={24} xl={12}>
              <Card className="feature-card compact-card" bordered={false}>
                <Title level={3}>Import / export JSON</Title>
                <TextArea className="json-panel" rows={8} value={importJson} onChange={(event) => setImportJson(event.target.value)} placeholder="Paste lorebook JSON to import" />
                <Space wrap className="tool-row">
                  <Button onClick={importLorebook} disabled={!importJson.trim()}>Import JSON</Button>
                  <Button onClick={exportLorebook} disabled={!selectedBookId}>Export selected</Button>
                </Space>
                {exportJson && <TextArea className="json-panel" rows={10} value={exportJson} readOnly />}
              </Card>
            </Col>
            <Col xs={24} xl={12}>
              <Card className="feature-card compact-card" bordered={false}>
                <Title level={3}>Hit test</Title>
                <TextArea rows={5} value={hitInput} onChange={(event) => setHitInput(event.target.value)} placeholder="Type current user input to test against the selected lorebook" />
                <Select
                  allowClear
                  className="full-width-input tool-row"
                  placeholder="Optional session context"
                  options={sessionOptions}
                  value={hitSessionId || undefined}
                  onChange={(value) => setHitSessionId(value || '')}
                />
                <Button onClick={runHitTest} disabled={!selectedBookId || !hitInput.trim()}>Run hit test</Button>
                {hitResult && (
                  <pre className="hit-test-output">{JSON.stringify({ hits: hitResult.hits, filtered: hitResult.filtered, buckets: hitResult.buckets }, null, 2)}</pre>
                )}
              </Card>
            </Col>
          </Row>
          {(accountOptions.length > 0 || sessionOptions.length > 0) && (
            <Card className="feature-card compact-card" bordered={false}>
              <Title level={3}>Assign selected lorebook</Title>
              <Row gutter={[12, 12]}>
                {accountOptions.length > 0 && (
                  <Col xs={24} md={12}>
                    <Space direction="vertical" className="assignment-control">
                      <Text className="control-label">Account default lorebook</Text>
                      <Select allowClear options={accountOptions} value={assignAccountId} onChange={setAssignAccountId} placeholder="Choose account" />
                      <Button onClick={() => assignLorebook('account')} disabled={!selectedBookId || !assignAccountId}>Set account lorebook_ids</Button>
                    </Space>
                  </Col>
                )}
                {sessionOptions.length > 0 && (
                  <Col xs={24} md={12}>
                    <Space direction="vertical" className="assignment-control">
                      <Text className="control-label">Session active lorebook</Text>
                      <Select allowClear options={sessionOptions} value={assignSessionId} onChange={setAssignSessionId} placeholder="Choose session" />
                      <Button onClick={() => assignLorebook('session')} disabled={!selectedBookId || !assignSessionId}>Set session lorebook_ids</Button>
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
          <Tag className="phase-tag">Sessions API</Tag>
          <Title level={1}>Sessions</Title>
          <Paragraph>Assign active characters, pause or resume RP, and manage recent session history.</Paragraph>
        </div>
        <Button onClick={loadSessions} loading={loading}>Refresh</Button>
      </div>
      {error && <div className="error-banner">{error}</div>}
      <Row gutter={[18, 18]}>
        <Col xs={24} lg={11}>
          <Card className="feature-card list-card" bordered={false}>
            <Title level={3}>Live sessions</Title>
            {loading ? (
              <Spin />
            ) : sessions.length === 0 ? (
              <Text type="secondary">No sessions yet.</Text>
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
                      <Text className="record-meta">Turns: {session.turn_count || 0}</Text>
                    </div>
                    <Tag color={session.paused ? 'gold' : 'green'}>{session.paused ? 'Paused' : 'Active'}</Tag>
                  </button>
                ))}
              </div>
            )}
          </Card>
        </Col>
        <Col xs={24} lg={13}>
          <Card className="feature-card form-card" bordered={false}>
            <Title level={3}>Session controls</Title>
            {selectedSession ? (
              <Space direction="vertical" size="middle" className="session-controls">
                <div>
                  <Text className="control-label">Active character</Text>
                  <Select
                    allowClear
                    placeholder="No active character"
                    options={characterOptions}
                    value={selectedSession.active_character_id || undefined}
                    onChange={(value) => patchSession(selectedSession.id, { active_character_id: value || null })}
                  />
                </div>
                <Space wrap>
                  <Button icon={<PauseCircleOutlined />} onClick={() => patchSession(selectedSession.id, { paused: !selectedSession.paused })}>
                    {selectedSession.paused ? 'Resume RP' : 'Pause RP'}
                  </Button>
                  <Button onClick={() => loadHistory(selectedSession.id)} loading={historyLoading}>Refresh history</Button>
                  <Popconfirm title="Clear all visible history?" onConfirm={clearHistory}>
                    <Button danger>Clear history</Button>
                  </Popconfirm>
                  <Button onClick={undoLatestTurn}>Undo latest turn</Button>
                </Space>
              </Space>
            ) : (
              <Text type="secondary">Select a session to manage controls and history.</Text>
            )}
          </Card>
          <Card className="feature-card history-card" bordered={false}>
            <Title level={3}>Recent history</Title>
            {historyLoading ? (
              <Spin />
            ) : history.length === 0 ? (
              <Text type="secondary">No history messages for this session.</Text>
            ) : (
              <div className="history-list">
                {history.map((message) => (
                  <div className="history-message" key={message.id}>
                    <Space className="history-message-head" wrap>
                      <Tag color={message.role === 'assistant' ? 'green' : message.role === 'system' ? 'blue' : 'gold'}>{message.role}</Tag>
                      <Text strong>{message.speaker || 'Unknown'}</Text>
                      <Text className="record-meta">Turn {message.turn_number}</Text>
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

function PlaceholderPage({ page }) {
  return (
    <section className="page-panel placeholder-panel">
      <Tag className="phase-tag">{page.tag}</Tag>
      <Title level={1}>{page.title}</Title>
      <Paragraph>{page.description}</Paragraph>
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
    return <PlaceholderPage page={pageCopy[selectedPage]} />;
  }, [selectedPage]);

  return (
    <ConfigProvider
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
              <Text className="brand-subtitle">AstrBot Plugin</Text>
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
              <Tag color="green">Default-on</Tag>
              <Tag color="blue">Phase 2 API</Tag>
              <Tag color="purple">Bearer token</Tag>
            </Space>
          </Header>
          <Content className="app-content">{content}</Content>
        </Layout>
      </Layout>
    </ConfigProvider>
  );
}

export default App;
