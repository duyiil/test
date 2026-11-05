import { LockOutlined, UserOutlined } from "@ant-design/icons";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Alert, App, Button, Card, Form, Input, Typography } from "antd";
import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ApiClientError, errorText } from "../api/client";
import { login } from "../api/resources";

interface LoginForm {
  username: string;
  password: string;
}

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const { message } = App.useApp();
  const [error, setError] = useState<string | null>(null);
  const reason = (location.state as { reason?: string } | null)?.reason;
  const from = (location.state as { from?: string } | null)?.from;

  const mutation = useMutation({
    mutationFn: (values: LoginForm) => login(values.username, values.password),
    onSuccess: async (envelope) => {
      queryClient.setQueryData(["me"], envelope.data);
      message.success("登录成功");
      navigate(from && from !== "/login" ? from : "/", { replace: true });
    },
    onError: (err: unknown) => {
      setError(err instanceof ApiClientError ? err.message : errorText(err));
    },
  });

  return (
    <div className="login-shell">
      <section className="login-brand">
        <div>
          <div className="brand-mark">智</div>
          <h1>智测 ZhiTest</h1>
          <p>基于大语言模型智能体的软件自动化测试与质量保障平台。已交付主链路：用例生成（Mock）→ 审核 → 执行（Worker）→ 数据报告。</p>
        </div>
        <Typography.Text style={{ color: "#9fb3c8" }}>首版不开放公开注册，账号由管理员创建。</Typography.Text>
      </section>
      <section className="login-panel">
        <Card className="login-card" title="登录">
          {reason === "expired" ? (
            <Alert
              style={{ marginBottom: 16 }}
              type="warning"
              showIcon
              message="登录已失效，请重新登录。正在编辑的非敏感草稿仍保留在本次浏览器会话中，密码不会被保存。"
            />
          ) : null}
          {error ? <Alert style={{ marginBottom: 16 }} type="error" showIcon message={error} /> : null}
          <Form<LoginForm>
            layout="vertical"
            autoComplete="on"
            onFinish={(values) => {
              setError(null);
              mutation.mutate(values);
            }}
          >
            <Form.Item label="用户名" name="username" rules={[{ required: true, message: "请输入用户名" }]}>
              <Input prefix={<UserOutlined />} autoComplete="username" />
            </Form.Item>
            <Form.Item label="密码" name="password" rules={[{ required: true, message: "请输入密码" }]}>
              <Input.Password prefix={<LockOutlined />} autoComplete="current-password" />
            </Form.Item>
            <Button type="primary" htmlType="submit" block loading={mutation.isPending}>
              登录
            </Button>
          </Form>
        </Card>
      </section>
    </div>
  );
}
