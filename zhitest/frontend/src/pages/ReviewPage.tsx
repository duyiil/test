import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Drawer, Form, Input, Modal, Space, Table, Tabs, Tag, Typography } from "antd";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { errorText } from "../api/client";
import { approveCase, batchReview, editCase, listCases, rejectCase, submitCase } from "../api/resources";
import type { CaseVersion } from "../api/resources";
import { useUiStore } from "../stores/ui";
import { REVIEW_LABEL } from "../utils/format";

const TABS = [
  { key: "draft", label: "草稿" },
  { key: "pending_review", label: "待审核" },
  { key: "confirmed", label: "已确认" },
  { key: "rejected", label: "已驳回" },
];

export function ReviewPage() {
  const projectId = useUiStore((state) => state.selectedProjectId);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState("draft");
  const [current, setCurrent] = useState<CaseVersion | null>(null);
  const [name, setName] = useState("");
  const [rejectOpen, setRejectOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [batchRejectOpen, setBatchRejectOpen] = useState(false);
  const [batchReason, setBatchReason] = useState("");

  useEffect(() => {
    setSelected([]);
  }, [tab, projectId]);

  const query = useQuery({
    queryKey: ["cases", projectId, tab],
    queryFn: async () => (await listCases(projectId ?? "", tab)).data.items,
    enabled: Boolean(projectId),
  });

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["cases", projectId] });
    await queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const act = useMutation({
    mutationFn: async (action: "submit" | "approve" | "reject" | "edit") => {
      if (!current) return;
      if (action === "submit") return submitCase(current.id);
      if (action === "approve") return approveCase(current.id);
      if (action === "reject") return rejectCase(current.id, reason);
      return editCase(current.id, { name });
    },
    onSuccess: async (envelope) => {
      setMessage(null);
      if (envelope) setCurrent(envelope.data);
      setRejectOpen(false);
      setReason("");
      await refresh();
    },
    onError: (error: unknown) => setMessage(errorText(error)),
  });

  const batch = useMutation({
    mutationFn: (action: "approve" | "reject") => batchReview(projectId ?? "", action, selected, batchReason),
    onSuccess: async (envelope) => {
      setMessage(null);
      setSelected([]);
      setBatchRejectOpen(false);
      setBatchReason("");
      setCurrent(null);
      await refresh();
      setMessage(`已处理 ${envelope.data.count} 条`);
    },
    onError: (error: unknown) => setMessage(errorText(error)),
  });

  if (!projectId) {
    return (
      <Alert
        type="info"
        showIcon
        message="请先在顶部选择项目，或从项目详情进入。"
        action={<Button onClick={() => navigate("/projects")}>项目列表</Button>}
      />
    );
  }

  return (
    <div className="page-stack">
      <Typography.Title level={3} style={{ margin: 0 }}>
        测试用例审核
      </Typography.Title>
      <Alert type="info" showIcon message="生成结果先进入草稿。通过后才能执行。修改已确认内容会生成新版本并回到待审核。驳回必须填写原因。" />
      {query.isError ? <Alert type="error" showIcon message={errorText(query.error)} /> : null}
      {message && !rejectOpen && !batchRejectOpen ? <Alert type={message.startsWith("已处理") ? "success" : "error"} showIcon message={message} /> : null}
      <Tabs activeKey={tab} items={TABS} onChange={setTab} />
      {tab === "pending_review" ? (
        <Space>
          <Button type="primary" disabled={selected.length === 0} loading={batch.isPending} onClick={() => batch.mutate("approve")}>
            批量通过
          </Button>
          <Button danger disabled={selected.length === 0} onClick={() => setBatchRejectOpen(true)}>
            批量驳回
          </Button>
          <Typography.Text type="secondary">已选 {selected.length} 条</Typography.Text>
        </Space>
      ) : null}
      <Table
        rowKey="id"
        loading={query.isLoading}
        dataSource={query.data ?? []}
        locale={{ emptyText: "这一栏没有用例" }}
        rowSelection={
          tab === "pending_review"
            ? { selectedRowKeys: selected, onChange: (keys) => setSelected(keys.map(String)) }
            : undefined
        }
        pagination={{ pageSize: 8 }}
        onRow={(record) => ({
          onClick: () => {
            setCurrent(record);
            setName(record.name);
            setMessage(null);
          },
        })}
        columns={[
          { title: "用例", dataIndex: "name" },
          { title: "方法", dataIndex: "method", width: 90 },
          { title: "路径", dataIndex: "relativePath" },
          {
            title: "状态",
            dataIndex: "reviewStatus",
            width: 110,
            render: (value: string) => <Tag>{REVIEW_LABEL[value] ?? value}</Tag>,
          },
          { title: "版本", dataIndex: "versionNumber", width: 80 },
          { title: "断言数", width: 90, render: (_, row) => row.assertions.length },
        ]}
      />
      <Drawer
        title={current?.name}
        width={640}
        open={current !== null}
        onClose={() => setCurrent(null)}
      >
        {current ? (
          <Space direction="vertical" style={{ width: "100%" }} size="middle">
            {message ? <Alert type="error" showIcon message={message} /> : null}
            <div>来源：{current.origin === "mock" ? "MockGenerationProvider（不是真实模型）" : current.origin}</div>
            <div>场景：{current.scenario}</div>
            <Typography.Paragraph>{current.basis}</Typography.Paragraph>
            <Typography.Text type="secondary">
              {current.method} {current.relativePath}
            </Typography.Text>
            <pre className="json-preview">{JSON.stringify({ body: current.body, assertions: current.assertions }, null, 2)}</pre>
            <Form layout="vertical">
              <Form.Item label="用例名称">
                <Input value={name} onChange={(event) => setName(event.target.value)} />
              </Form.Item>
            </Form>
            <Space wrap>
              <Button onClick={() => act.mutate("edit")} loading={act.isPending}>
                保存为新版本
              </Button>
              <Button onClick={() => act.mutate("submit")} disabled={current.reviewStatus !== "draft" && current.reviewStatus !== "rejected"}>
                提交审核
              </Button>
              <Button type="primary" onClick={() => act.mutate("approve")} disabled={current.reviewStatus !== "pending_review"}>
                审核通过
              </Button>
              <Button danger onClick={() => setRejectOpen(true)} disabled={current.reviewStatus !== "pending_review"}>
                驳回
              </Button>
            </Space>
            <Typography.Title level={5}>版本</Typography.Title>
            {current.history.map((item) => (
              <div key={item.id}>
                v{item.versionNumber} {REVIEW_LABEL[item.reviewStatus] ?? item.reviewStatus} {item.name}
              </div>
            ))}
            <Typography.Title level={5}>审核记录</Typography.Title>
            {current.events.length === 0 ? <div>暂无</div> : null}
            {current.events.map((event) => (
              <div key={event.id}>
                {event.action} {event.reason ?? ""} {event.createdAt}
              </div>
            ))}
          </Space>
        ) : null}
      </Drawer>
      <Modal
        title="驳回原因"
        open={rejectOpen}
        onCancel={() => setRejectOpen(false)}
        onOk={() => act.mutate("reject")}
        okButtonProps={{ disabled: reason.trim().length === 0 }}
      >
        <Input.TextArea value={reason} onChange={(event) => setReason(event.target.value)} placeholder="必填" rows={4} />
        {message && rejectOpen ? <Alert style={{ marginTop: 12 }} type="error" message={message} /> : null}
      </Modal>
      <Modal
        title="批量驳回"
        open={batchRejectOpen}
        onCancel={() => setBatchRejectOpen(false)}
        onOk={() => batch.mutate("reject")}
        okButtonProps={{ disabled: batchReason.trim().length === 0, danger: true }}
        confirmLoading={batch.isPending}
      >
        <Input.TextArea value={batchReason} onChange={(event) => setBatchReason(event.target.value)} placeholder="驳回原因，必填" rows={4} />
      </Modal>
    </div>
  );
}
