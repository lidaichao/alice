import { useState, useEffect } from 'react';
import { Form, Input, Button, Switch, Select, Typography, Alert, Divider, Space } from 'antd';
import { SaveOutlined, SettingOutlined } from '@ant-design/icons';

const { Title, Text } = Typography;

export default function SettingsPage({ onBack }) {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [initialLoading, setInitialLoading] = useState(true);

  useEffect(() => {
    if (typeof window.baize?.getJiraConfig === 'function') {
      window.baize.getJiraConfig()
        .then((config) => {
          form.setFieldsValue({
            enabled: config?.enabled !== false,
            baseURL: config?.baseURL || '',
            username: config?.username || '',
            apiToken: '',
            defaultProjectKey: config?.defaultProjectKey || ''
          });
        })
        .catch(() => {})
        .finally(() => setInitialLoading(false));
    } else {
      setInitialLoading(false);
    }
  }, [form]);

  const handleSave = async (values) => {
    setLoading(true);
    setResult(null);
    try {
      await window.baize.setJiraConfig({
        enabled: values.enabled,
        baseURL: values.baseURL || undefined,
        username: values.username || undefined,
        apiToken: values.apiToken || undefined,
        defaultProjectKey: values.defaultProjectKey || undefined
      });
      setResult({ type: 'success', message: 'Jira 配置已保存。' });
    } catch (err) {
      setResult({ type: 'error', message: err?.message || '保存失败' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'flex-start', height: '100vh', padding: '40px 24px', overflowY: 'auto'
    }}>
      <div style={{ width: 480 }}>
        <Space style={{ marginBottom: 24 }}>
          <SettingOutlined style={{ fontSize: 24, color: '#1677ff' }} />
          <Title level={3} style={{ margin: 0 }}>设置</Title>
        </Space>

        {result && (
          <Alert
            type={result.type}
            message={result.message}
            style={{ marginBottom: 16 }}
            showIcon
            closable
            onClose={() => setResult(null)}
          />
        )}

        {initialLoading ? (
          <Text type="secondary">加载配置中…</Text>
        ) : (
          <Form form={form} onFinish={handleSave} layout="vertical">
            <Divider orientation="left" plain>
              <Text type="secondary">Jira 配置</Text>
            </Divider>

            <Form.Item name="enabled" label="启用" valuePropName="checked" initialValue={true}>
              <Switch />
            </Form.Item>

            <Form.Item name="baseURL" label="Jira 地址" extra="例如：https://your-domain.atlassian.net">
              <Input placeholder="Jira 服务器地址" />
            </Form.Item>

            <Form.Item name="username" label="用户名 / 邮箱">
              <Input placeholder="Jira 用户名或邮箱" />
            </Form.Item>

            <Form.Item name="apiToken" label="API Token"
              extra="输入新 token 后点击保存（已保存的不会回显）"
            >
              <Input.Password placeholder="Jira API Token" />
            </Form.Item>

            <Form.Item name="defaultProjectKey" label="默认项目 Key">
              <Select
                placeholder="选择或输入项目 Key"
                showSearch
                options={[
                  { value: 'AL', label: 'AL (Alice)' },
                  { value: 'BAIZE', label: 'BAIZE' }
                ]}
              />
            </Form.Item>

            <Divider />

            <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
              <Button onClick={onBack}>返回</Button>
              <Button type="primary" icon={<SaveOutlined />} htmlType="submit" loading={loading}>
                保存
              </Button>
            </Space>
          </Form>
        )}
      </div>
    </div>
  );
}
