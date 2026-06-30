import { useState, useEffect, useCallback } from 'react';
import { Form, Input, Button, Tabs, Typography, Alert, Progress, Space } from 'antd';
import { UserOutlined, LockOutlined, DownloadOutlined, ReloadOutlined } from '@ant-design/icons';

const { Title, Text } = Typography;

export default function LoginPage({ onLoginSuccess }) {
  const [tab, setTab] = useState('login');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [updateState, setUpdateState] = useState(null);
  const [form] = Form.useForm();

  const isRegister = tab === 'register';

  const fetchUpdateStatus = useCallback(async () => {
    try {
      const status = await window.baize.getUpdateStatus();
      setUpdateState(status);
    } catch {}
  }, []);

  useEffect(() => {
    fetchUpdateStatus();
    if (typeof window.baize?.onUpdateState === 'function') {
      return window.baize.onUpdateState((state) => {
        setUpdateState(state);
      });
    }
  }, [fetchUpdateStatus]);

  const handleSubmit = async (values) => {
    setLoading(true);
    setError('');
    try {
      const result = isRegister
        ? await window.baize.register({ username: values.username, password: values.password })
        : await window.baize.login({ username: values.username, password: values.password });
      onLoginSuccess(result.user);
    } catch (err) {
      const statusCode = err?.status || err?.statusCode;
      if (statusCode === 429) {
        const retryAfter = err?.retryAfter || err?.data?.retryAfter || 30;
        setError(`操作过于频繁，请 ${retryAfter} 秒后重试。`);
      } else {
        setError(err?.message || err?.data?.error || `${isRegister ? '注册' : '登录'}失败`);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleCheckUpdate = async () => {
    try {
      await window.baize.checkForUpdate();
      fetchUpdateStatus();
    } catch {}
  };

  const handleDownloadUpdate = async () => {
    try {
      await window.baize.downloadUpdate();
    } catch {}
  };

  const handleInstallUpdate = async () => {
    try {
      await window.baize.installUpdate();
    } catch {}
  };

  const view = updateState && updateState.versionStatus && updateState.versionStatus.enabled
    && (updateState.versionStatus.updateAvailable || ['checking', 'downloading', 'downloaded', 'error'].includes(updateState.status));

  const updateRequired = updateState?.versionStatus?.updateRequired;
  const isDownloading = updateState?.status === 'downloading';
  const progress = updateState && Number.isFinite(updateState.progress) ? Math.max(0, Math.min(100, updateState.progress)) : 0;

  const items = [
    {
      key: 'login',
      label: '登录',
      children: null
    },
    {
      key: 'register',
      label: '注册',
      children: null
    }
  ];

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', height: '100vh', padding: 24
    }}>
      <div style={{ width: 360 }}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <Title level={2} style={{ margin: 0 }}>Alice</Title>
          <Text type="secondary">AI 工程助手</Text>
        </div>

        {view && (
          <Alert
            style={{ marginBottom: 16 }}
            type={updateRequired ? 'warning' : 'info'}
            message={updateRequired ? '强制更新' : '客户端更新'}
            description={
              <div>
                <div style={{ marginBottom: 8 }}>{updateState?.message || '有可用更新。'}</div>
                {isDownloading && <Progress percent={progress} size="small" style={{ marginBottom: 8 }} />}
                <Space>
                  {updateState?.status === 'available' && (
                    <Button type="primary" size="small" icon={<DownloadOutlined />} onClick={handleDownloadUpdate}>
                      下载更新
                    </Button>
                  )}
                  <Button size="small" icon={<ReloadOutlined />} onClick={handleCheckUpdate}>检查</Button>
                  {updateState?.status === 'downloaded' && (
                    <Button type="primary" size="small" onClick={handleInstallUpdate}>重启安装</Button>
                  )}
                </Space>
              </div>
            }
            showIcon
          />
        )}

        {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} showIcon closable onClose={() => setError('')} />}

        <Tabs activeKey={tab} onChange={(key) => { setTab(key); setError(''); form.resetFields(); }} items={items} centered />

        <Form form={form} onFinish={handleSubmit} layout="vertical">
          <Form.Item
            name="username"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input
              prefix={<UserOutlined />}
              placeholder="用户名"
              autoFocus
              size="large"
            />
          </Form.Item>

          <Form.Item
            name="password"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="密码"
              size="large"
            />
          </Form.Item>

          {isRegister && (
            <Form.Item
              name="confirmPassword"
              dependencies={['password']}
              rules={[
                { required: true, message: '请再次输入密码' },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    if (!value || getFieldValue('password') === value) return Promise.resolve();
                    return Promise.reject(new Error('两次输入的密码不一致'));
                  }
                })
              ]}
            >
              <Input.Password
                prefix={<LockOutlined />}
                placeholder="确认密码"
                size="large"
              />
            </Form.Item>
          )}

          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block size="large">
              {isRegister ? '注册并登录' : '登录'}
            </Button>
          </Form.Item>
        </Form>

        <div style={{ textAlign: 'center' }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            登录后可在 Windows 和 Android 共用同一个 Alice 账号。
          </Text>
        </div>
      </div>
    </div>
  );
}
