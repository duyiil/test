import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Descriptions, List, Modal, Space, Table, Typography } from "antd";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiClientError, errorText } from "../api/client";
import { cancelRun, createRun, listRuns } from "../api/resources";
import type { RunItem } from "../api/resources";
import { useUiStore } from "../stores/ui";
import { RUN_LABEL, formatTime, isActiveRun } from "../utils/format";

export function RunPage() {
  const projectId = useUiStore((state) => state.selectedProjectId);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<RunItem | null>(null);
  const [writes, setWrites] = useState<{ name: string; method: string; path: string }[] | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ["runs", projectId],
    queryFn: async () => (await listRuns(projectId ?? "")).data.items,
    enabled: Boolean(projectId),
    refetchOnWindowFocus: true,
    refetchInterval: (q) => ((q.state.data ?? []).some((item) => isActiveRun(item.status)) ? 5000 : false),
  });

  useEffect(() => {
    if (!selected || !query.data) return;
    const fresh = query.data.find((item) => item.id === selected.id);
    if (!fresh) return;
    if (
      fresh.status !== selected.status ||
      fresh.executedCount !== selected.executedCount ||
      fresh.results.length !== selected.results.length
    ) {
      setSelected(fresh);
    }
  }, [query.data, selected]);

  const start = useMutation({
    mutationFn: (confirmWrites: boolean) => createRun(projectId ?? "", confirmWrites),
    onSuccess: async (envelope) => {
      setWrites(null);
      setNotice(null);
      setSelected(envelope.data);
      await queryClient.invalidateQueries({ queryKey: ["runs", projectId] });
    },
    onError: (error: unknown) => {
      if (error instanceof ApiClientError && error.code === "WRITE_CONFIRMATION_REQUIRED" && Array.isArray((error.details as { operations?: unknown })?.operations)) {
        setWrites((error.details as { operations: { name: string; method: string; path: string }[] }).operations);
        return;
      }
      setNotice(errorText(error));
    },
  });

  const cancel = useMutation({
    mutationFn: (id: string) => cancelRun(id),
    onSuccess: async (envelope) => {
      setSelected(envelope.data);
      await queryClient.invalidateQueries({ queryKey: ["runs", projectId] });
    },
    onError: (error: unknown) => setNotice(errorText(error)),
  });

  if (!projectId) {
    return <Alert type="info" showIcon message="请先在顶部选择项目。" action={<Button onClick={() => navigate("/projects")}>项目列表</Button>} />;
  }

  const updated = query.dataUpdatedAt ? formatTime(new Date(query.dataUpdatedAt).toISOString()) : "—";

  return (
    <div className="page-stack">
      <Space style={{ justifyContent: "space-between" }} wrap>
        <Typography.Title level={3} style={{ margin: 0 }}>
          执行任务
        </Typography.Title>
        <Button type="primary" onClick={() => start.mutate(false)} loading={start.isPending}>
          执行已确认用例
        </Button>
      </Space>
      <Typography.Text type="secondary">每 5 秒刷新未结束任务。上次成功刷新：{updated}。网络失败不会被记成测试失败。</Typography.Text>
      {query.isError ? (
        <Alert type="warning" showIcon message={`网络异常，以下为上次成功数据。${errorText(query.error)}`} />
      ) : null}
      {notice ? <Alert type="error" showIcon message={notice} /> : null}
      <Table
        rowKey="id"
        loading={query.isLoading}
        dataSource={query.data ?? []}
        locale={{ emptyText: "暂无执行任务" }}
        onRow={(record) => ({ onClick: () => setSelected(record) })}
        columns={[
          { title: "任务", dataIndex: "id", render: (value: string) => value.slice(0, 8) },
          { title: "状态", dataIndex: "status", render: (value: string) => RUN_LABEL[value] ?? value },
          { title: "已执行", dataIndex: "executedCount" },
          { title: "通过", dataIndex: "passedCount" },
          { title: "断言失败", dataIndex: "assertionFailedCount" },
          { title: "执行错误", dataIndex: "executionErrorCount" },
          { title: "跳过", dataIndex: "skippedCount" },
          { title: "通过率", dataIndex: "passRateText" },
          {
            title: "操作",
            render: (_, row) =>
              isActiveRun(row.status) ? (
                <Button
                  size="small"
                  onClick={(event) => {
                    event.stopPropagation();
                    cancel.mutate(row.id);
                  }}
                >
                  取消
                </Button>
              ) : (
                <Link to={`/reports?run=${row.id}`}>数据报告</Link>
              ),
          },
        ]}
      />
      {selected ? (
        <Descriptions bordered size="small" column={2} title="任务明细">
          <Descriptions.Item label="状态">{RUN_LABEL[selected.status] ?? selected.status}</Descriptions.Item>
          <Descriptions.Item label="说明">{selected.status === "succeeded" ? "流程完成。断言失败不等于任务失败。" : selected.abortReason || "—"}</Descriptions.Item>
        </Descriptions>
      ) : null}
      {selected ? (
        <List
          dataSource={selected.results}
          locale={{ emptyText: "还没有结果" }}
          renderItem={(item) => (
            <List.Item>
              <List.Item.Meta
                title={`${item.request.method ?? ""} ${item.request.url ?? ""} · ${item.status}`}
                description={
                  <div>
                    <div>HTTP {item.responseStatus ?? "—"} {item.errorMessage ?? ""}</div>
                    {item.assertionResults.map((assertion, index) => (
                      <div key={`${item.id}-${index}`}>
                        {assertion.passed ? "通过" : "失败"} {assertion.type} {assertion.message}
                      </div>
                    ))}
                  </div>
                }
              />
            </List.Item>
          )}
        />
      ) : null}
      <Modal
        title="确认写操作"
        open={writes !== null}
        onCancel={() => setWrites(null)}
        onOk={() => start.mutate(true)}
        okText="确认执行"
      >
        <p>以下用例会向演示服务发送写请求。确认后才会创建任务。</p>
        <ul>
          {(writes ?? []).map((item) => (
            <li key={`${item.method}-${item.path}-${item.name}`}>
              {item.method} {item.path} {item.name}
            </li>
          ))}
        </ul>
      </Modal>
    </div>
  );
}
