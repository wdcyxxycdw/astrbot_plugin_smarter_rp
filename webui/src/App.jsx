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
  Col,
  ConfigProvider,
  Form,
  Input,
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
  lorebooks: {
    tag: 'Phase 1 shell',
    title: 'Lorebooks keep shared world facts close',
    description:
      'Lorebook tools remain available as a static pane until CRUD and binding controls are wired to the authenticated API.',
  },
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
