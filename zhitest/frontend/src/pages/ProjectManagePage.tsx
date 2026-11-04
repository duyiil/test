import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App, Button, Card, Input, Modal, Select, Space, Table, Tag, Typography } from "antd";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { errorText } from "../api/client";
import {
  activateEnvironment,
  addMember,
  archiveProject,
  createEnvironment,
  deleteEnvironment,
  deleteProject,
  getProject,
  listEnvironments,
  listMembers,
  removeMember,
  restoreProject,
  updateMemberRole,
} from "../api/resources";
import { useUiStore } from "../stores/ui";

const ROLES = [
  { value: "tester", label: "测试" },
  { value: "readonly", label: "只读" },
];

export function ProjectManagePage() {
  const { projectId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { message } = App.useApp();
  const setSelectedProjectId = useUiStore((state) => state.setSelectedProjectId);
  const [envName, setEnvName] = useState("");
  const [envUrl, setEnvUrl] = useState("");
  const [username, setUsername] = useState("");
  const [role, setRole] = useState("tester");
  const [error, setError] = useState<string | null>(null);
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [confirmName, setConfirmName] = useState("");

  const project = useQuery({
    queryKey: ["project", projectId],
    queryFn: async () => (await getProject(projectId)).data,
    enabled: projectId.length > 0,
  });
  const environments = useQuery({
    queryKey: ["environments", projectId],
    queryFn: async () => (await listEnvironments(projectId)).data.items,
    enabled: projectId.length > 0,
  });
  const members = useQuery({
    queryKey: ["members", projectId],
    queryFn: async () => (await listMembers(projectId)).data,
    enabled: projectId.length > 0,
  });

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["environments", projectId] });
    await queryClient.invalidateQueries({ queryKey: ["members", projectId] });
    await queryClient.invalidateQueries({ queryKey: ["project", projectId] });
    await queryClient.invalidateQueries({ queryKey: ["projects"] });
  };

  const addEnv = useMutation({
    mutationFn: () => createEnvironment(projectId, { name: envName.trim(), baseUrl: envUrl.trim() }),
    onSuccess: async () => {
      setEnvName("");
      setEnvUrl("");
      setError(null);
      message.success("环境已添加");
      await refresh();
    },
    onError: (caught: unknown) => setError(errorText(caught)),
  });
  const activate = useMutation({
    mutationFn: (id: string) => activateEnvironment(projectId, id),
    onSuccess: async () => {
      setError(null);
      await refresh();
    },
    onError: (caught: unknown) => setError(errorText(caught)),
  });
  const dropEnv = useMutation({
    mutationFn: (id: string) => deleteEnvironment(projectId, id),
    onSuccess: async () => {
      setError(null);
      await refresh();
    },
    onError: (caught: unknown) => setError(errorText(caught)),
  });
  const addPerson = useMutation({
    mutationFn: () => addMember(projectId, username.trim(), role),
    onSuccess: async () => {
      setUsername("");
      setError(null);
      message.success("成员已添加");
      await refresh();
    },
    onError: (caught: unknown) => setError(errorText(caught)),
  });
  const changeRole = useMutation({
    mutationFn: (input: { id: string; role: string }) => updateMemberRole(projectId, input.id, input.role),
    onSuccess: async () => {
      setError(null);
      await refresh();
    },
    onError: (caught: unknown) => setError(errorText(caught)),
  });
  const dropMember = useMutation({
    mutationFn: (id: string) => removeMember(projectId, id),
    onSuccess: async () => {
      setError(null);
      await refresh();
    },
    onError: (caught: unknown) => setError(errorText(caught)),
  });
  const archive = useMutation({
    mutationFn: () => (project.data?.status === "archived" ? restoreProject(projectId) : archiveProject(projectId)),
    onSuccess: async () => {
      setArchiveOpen(false);
      setError(null);
      await refresh();
    },
    onError: (caught: unknown) => setError(errorText(caught)),
  });
  const destroy = useMutation({
    mutationFn: () => deleteProject(projectId),
    onSuccess: async () => {
      setSelectedProjectId(null);
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
      navigate("/projects");
    },
    onError: (caught: unknown) => setError(errorText(caught)),
  });

  const archived = project.data?.status === "archived";
  return (
    <div className="page-stack">
      <Space style={{ justifyContent: "space-between" }} wrap>
        <Typography.Title level={3} style={{ margin: 0 }}>
          项目设置 {project.data ? `· ${project.data.name}` : ""}
        </Typography.Title>
        <Button onClick={() => navigate(`/projects/${projectId}`)}>返回项目</Button>
      </Space>
      {error ? <Alert type="error" showIcon message={error} /> : null}
      {archived ? <Alert type="warning" showIcon message="项目已归档，不能再执行。恢复后可以继续使用。" /> : null}

      <Card title="执行环境">
        <Typography.Paragraph type="secondary">
          这里保存项目自己的环境地址。执行时使用当前激活的地址；没有激活环境时仍用项目上的 Base URL。
        </Typography.Paragraph>
        <Space wrap style={{ marginBottom: 16 }}>
          <Input placeholder="环境名称" value={envName} onChange={(event) => setEnvName(event.target.value)} />
          <Input placeholder="http://127.0.0.1:9000" value={envUrl} onChange={(event) => setEnvUrl(event.target.value)} style={{ width: 280 }} />
          <Button type="primary" onClick={() => addEnv.mutate()} loading={addEnv.isPending} disabled={!envName.trim() || !envUrl.trim()}>
            添加环境
          </Button>
        </Space>
        <Table
          rowKey="id"
          loading={environments.isLoading}
          dataSource={environments.data ?? []}
          locale={{ emptyText: "还没有额外环境" }}
          pagination={false}
          columns={[
            { title: "名称", dataIndex: "name" },
            { title: "地址", dataIndex: "baseUrl" },
            {
              title: "状态",
              dataIndex: "isActive",
              render: (active: boolean) => (active ? <Tag color="blue">当前</Tag> : <Tag>未激活</Tag>),
            },
            {
              title: "操作",
              render: (_, row) => (
                <Space>
                  <Button size="small" disabled={row.isActive} onClick={() => activate.mutate(row.id)}>
                    设为当前
                  </Button>
                  <Button size="small" danger onClick={() => dropEnv.mutate(row.id)}>
                    删除
                  </Button>
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <Card title="成员">
        <Typography.Paragraph type="secondary">所有者始终保留。可添加已有账号，角色只有测试和只读。</Typography.Paragraph>
        <Space wrap style={{ marginBottom: 16 }}>
          <Input placeholder="用户名" value={username} onChange={(event) => setUsername(event.target.value)} />
          <Select value={role} options={ROLES} onChange={setRole} style={{ width: 120 }} />
          <Button type="primary" onClick={() => addPerson.mutate()} loading={addPerson.isPending} disabled={!username.trim()}>
            添加成员
          </Button>
        </Space>
        <Table
          rowKey={(row) => row.id || "owner"}
          loading={members.isLoading}
          pagination={false}
          locale={{ emptyText: "还没有其他成员" }}
          dataSource={
            members.data
              ? [{ id: "", username: members.data.owner.username, displayName: members.data.owner.displayName, role: "owner" }, ...members.data.items]
              : []
          }
          columns={[
            { title: "用户名", dataIndex: "username" },
            { title: "显示名", dataIndex: "displayName" },
            {
              title: "角色",
              dataIndex: "role",
              render: (value: string, row) =>
                value === "owner" ? (
                  <Tag>所有者</Tag>
                ) : (
                  <Select
                    size="small"
                    value={value}
                    options={ROLES}
                    onChange={(next) => changeRole.mutate({ id: row.id, role: next })}
                    style={{ width: 110 }}
                  />
                ),
            },
            {
              title: "操作",
              render: (_, row) =>
                row.role === "owner" ? (
                  "不可移除"
                ) : (
                  <Button size="small" danger onClick={() => dropMember.mutate(row.id)}>
                    移除
                  </Button>
                ),
            },
          ]}
        />
      </Card>

      <Card title="归档与删除">
        <Space direction="vertical">
          <Typography.Text>归档会停止新的执行，项目和数据都还在。删除会永久清掉项目及其接口、用例、执行记录和报告。</Typography.Text>
          <Space>
            <Button onClick={() => setArchiveOpen(true)}>{archived ? "恢复项目" : "归档项目"}</Button>
            <Button danger type="primary" onClick={() => setDeleteOpen(true)}>
              删除项目
            </Button>
          </Space>
        </Space>
      </Card>

      <Modal
        title={archived ? "恢复项目" : "归档项目"}
        open={archiveOpen}
        onCancel={() => setArchiveOpen(false)}
        onOk={() => archive.mutate()}
        confirmLoading={archive.isPending}
      >
        {archived ? "恢复后可以继续生成和执行。" : "归档后不能再执行。之后可以恢复。"}
      </Modal>
      <Modal
        title="永久删除项目"
        open={deleteOpen}
        okText="删除"
        okButtonProps={{ danger: true, disabled: confirmName !== project.data?.name }}
        confirmLoading={destroy.isPending}
        onCancel={() => {
          setDeleteOpen(false);
          setConfirmName("");
        }}
        onOk={() => destroy.mutate()}
      >
        <Alert type="error" showIcon message="此操作不可恢复。接口、用例、执行记录和报告会一起删除。" style={{ marginBottom: 12 }} />
        <Typography.Paragraph>
          请输入项目名称 <Typography.Text code>{project.data?.name}</Typography.Text> 以确认。
        </Typography.Paragraph>
        <Input value={confirmName} onChange={(event) => setConfirmName(event.target.value)} placeholder="项目名称" />
      </Modal>
    </div>
  );
}
