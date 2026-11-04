import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Form, Input, Space, Typography } from "antd";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { errorText } from "../api/client";
import { createProject } from "../api/resources";
import type { ProjectDraft } from "../api/types";
import { useUiStore } from "../stores/ui";
import { clearProjectDraft, loadProjectDraft, saveProjectDraft } from "../utils/draft";

function validateBaseUrl(_: unknown, value: string) {
  const raw = (value ?? "").trim();
  if (!raw) return Promise.reject(new Error("Base URL 必填"));
  let parsed: URL;
  try {
    parsed = new URL(raw);
  } catch {
    return Promise.reject(new Error("Base URL 格式非法"));
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return Promise.reject(new Error("Base URL 格式非法"));
  }
  if (parsed.username || parsed.password) {
    return Promise.reject(new Error("Base URL 不能包含用户名或密码"));
  }
  return Promise.resolve();
}

export function ProjectCreatePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const setSelectedProjectId = useUiStore((state) => state.setSelectedProjectId);
  const [form] = Form.useForm<ProjectDraft>();
  const [error, setError] = useState<string | null>(null);
  const [initialValues] = useState<ProjectDraft>(
    () => loadProjectDraft() ?? { name: "", description: "", baseUrl: "", envLabel: "测试" },
  );

  const mutation = useMutation({
    mutationFn: (values: ProjectDraft) => createProject(values),
    onSuccess: async (envelope) => {
      clearProjectDraft();
      setSelectedProjectId(envelope.data.id);
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
      await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      navigate(`/projects/${envelope.data.id}`, { replace: true });
    },
    onError: (err: unknown) => setError(errorText(err)),
  });

  return (
    <div className="page-stack">
      <Typography.Title level={3} style={{ margin: 0 }}>
        新建项目
      </Typography.Title>
      <Alert
        type="info"
        showIcon
        message="同一账号下项目名称不可重复。Phase 1 只保存一个环境标签和 Base URL，服务器不会访问该地址。多环境、归档和删除尚未实现。"
      />
      <Card>
        {error ? <Alert style={{ marginBottom: 16 }} type="error" showIcon message={error} /> : null}
        <Form<ProjectDraft>
          form={form}
          layout="vertical"
          initialValues={initialValues}
          onValuesChange={(_, values) =>
            saveProjectDraft({
              name: values.name ?? "",
              description: values.description ?? "",
              baseUrl: values.baseUrl ?? "",
              envLabel: values.envLabel ?? "",
            })
          }
          onFinish={(values) => {
            setError(null);
            mutation.mutate({
              name: values.name.trim(),
              description: values.description.trim(),
              baseUrl: values.baseUrl.trim(),
              envLabel: values.envLabel.trim(),
            });
          }}
        >
          <Form.Item label="项目名称" name="name" rules={[{ required: true, whitespace: true, message: "请输入项目名称" }, { max: 100 }]}>
            <Input />
          </Form.Item>
          <Form.Item label="描述" name="description" rules={[{ max: 2000 }]}>
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item label="Base URL" name="baseUrl" rules={[{ validator: validateBaseUrl }]}>
            <Input placeholder="http://127.0.0.1:9000" />
          </Form.Item>
          <Form.Item
            label="环境标签"
            name="envLabel"
            rules={[{ required: true, whitespace: true, message: "请输入环境标签" }, { max: 32 }]}
          >
            <Input placeholder="开发 / 测试 / 预发" />
          </Form.Item>
          <Space>
            <Button type="primary" htmlType="submit" loading={mutation.isPending}>
              保存
            </Button>
            <Button onClick={() => navigate("/projects")}>返回列表</Button>
            <Button
              type="link"
              onClick={() => {
                clearProjectDraft();
                form.setFieldsValue({ name: "", description: "", baseUrl: "", envLabel: "测试" });
              }}
            >
              清空草稿
            </Button>
          </Space>
        </Form>
      </Card>
    </div>
  );
}
