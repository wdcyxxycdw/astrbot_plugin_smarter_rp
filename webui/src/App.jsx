import { useMemo, useState } from 'react';
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
import { Card, Col, ConfigProvider, Layout, Menu, Row, Space, Tag, Typography, theme } from 'antd';

const { Header, Sider, Content } = Layout;
const { Title, Paragraph, Text } = Typography;

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
  characters: {
    tag: 'Phase 1 shell',
    title: 'Characters stay connected to roleplay identity',
    description:
      'Character management remains in the navigation shell and will connect to configured character profiles in a later API-backed task.',
  },
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

function SessionsPage() {
  return (
    <section className="page-panel split-panel">
      <div>
        <Tag className="phase-tag">Sessions</Tag>
        <Title level={1}>Live sessions stay readable</Title>
        <Paragraph>
          Session management will focus on operational state: whether RP is paused, which character is active, and which lorebooks are bound.
        </Paragraph>
      </div>
      <Card className="feature-card" bordered={false}>
        <Space className="pause-line">
          <PauseCircleOutlined />
          <Text>Pause and resume controls will appear here after API wiring.</Text>
        </Space>
        <ul className="feature-list">
          <li>Review each active session at a glance.</li>
          <li>See the active character selected for the conversation.</li>
          <li>Confirm the lorebooks currently influencing replies.</li>
        </ul>
      </Card>
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
              <Tag color="blue">Static Phase 1</Tag>
              <Tag color="purple">No API fetch</Tag>
            </Space>
          </Header>
          <Content className="app-content">{content}</Content>
        </Layout>
      </Layout>
    </ConfigProvider>
  );
}

export default App;
