import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Empty, Input, List, Modal, Select, Space, Switch, Table, Typography } from "antd";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { errorText } from "../api/client";
import { createSchedule, listScheduleEvents, listSchedules, listSuites, updateSchedule, type ScheduleItem } from "../api/resources";
import { useUiStore } from "../stores/ui";
import { formatTime } from "../utils/format";

function History({ scheduleId }: { scheduleId: string }) {
  const query = useQuery({
    queryKey: ["schedule-events", scheduleId],
    queryFn: async () => (await listScheduleEvents(scheduleId)).data.items,
  });
  if (query.isLoading) return <Typography.Text type="secondary">正在加载记录</Typography.Text>;
  if (!query.data?.length) return <Typography.Text type="secondary">还没有记录</Typography.Text>;
  return (
    <List
      size="small"
      dataSource={query.data}
      renderItem={(item) => (
        <List.Item>
          {formatTime(item.createdAt)} · {item.kind} · {item.message}
          {item.runId ? ` · 任务 ${item.runId.slice(0, 8)}` : ""}
        </List.Item>
      )}
    />
  );
}

export function SchedulePage() {
  const projectId = useUiStore((state) => state.selectedProjectId);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [suiteId, setSuiteId] = useState<string>();
  const [cron, setCron] = useState("0 2 * * *");
  const [editing, setEditing] = useState<ScheduleItem | null>(null);
  const [nextCron, setNextCron] = useState("");
  const [error, setError] = useState<string | null>(null);

  const suites = useQuery({
    queryKey: ["suites", projectId],
    queryFn: async () => (await listSuites(projectId ?? "")).data.items,
    enabled: Boolean(projectId),
  });
  const schedules = useQuery({
    queryKey: ["schedules", projectId],
    queryFn: async () => (await listSchedules(projectId ?? "")).data,
    enabled: Boolean(projectId),
  });
  const refresh = async (id?: string) => {
    await queryClient.invalidateQueries({ queryKey: ["schedules", projectId] });
    if (id) await queryClient.invalidateQueries({ queryKey: ["schedule-events", id] });
  };
  const create = useMutation({
    mutationFn: () => createSchedule(suiteId ?? "", cron.trim()),
    onSuccess: async (envelope) => {
      setError(null);
      await refresh(envelope.data.id);
    },
    onError: (caught: unknown) => setError(errorText(caught)),
  });
  const save = useMutation({
    mutationFn: (input: { id: string; cron?: string; enabled?: boolean }) => updateSchedule(input.id, input),
    onSuccess: async (_, input) => {
      setEditing(null);
      setError(null);
      await refresh(input.id);
    },
    onError: (caught: unknown) => setError(errorText(caught)),
  });

  if (!projectId) {
    return <Alert type="info" showIcon message="请先选择项目。" action={<Button onClick={() => navigate("/projects")}>项目列表</Button>} />;
  }

  const items = schedules.data?.items ?? [];
  return (
    <div className="page-stack">
      <Typography.Title level={3} style={{ margin: 0 }}>
        定时执行
      </Typography.Title>
      <Alert type="info" showIcon message={schedules.data?.note ?? "只保存计划。这里没有验证操作系统级 cron 一直在跑。"} />
      {error ? <Alert type="error" showIcon message={error} /> : null}
      <Space wrap>
        <Select
          placeholder="选择用例集"
          style={{ minWidth: 220 }}
          value={suiteId}
          options={(suites.data ?? []).map((item) => ({ value: item.id, label: `${item.name}${item.isRegression ? " · 回归" : ""}` }))}
          onChange={setSuiteId}
        />
        <Input value={cron} onChange={(event) => setCron(event.target.value)} style={{ width: 180 }} aria-label="cron" />
        <Button type="primary" disabled={!suiteId || cron.trim().split(/\s+/).length !== 5} loading={create.isPending} onClick={() => create.mutate()}>
          保存计划
        </Button>
      </Space>
      {(suites.data ?? []).length === 0 && !suites.isLoading ? <Empty description="还没有用例集，不能创建计划。" /> : null}
      {!schedules.isLoading && items.length === 0 ? <Empty description="还没有定时计划" /> : null}
      {items.length > 0 ? (
        <Table<ScheduleItem>
          rowKey="id"
          dataSource={items}
          pagination={false}
          expandable={{ expandedRowRender: (row) => <History scheduleId={row.id} /> }}
          columns={[
            { title: "用例集", dataIndex: "suiteName", render: (name: string, row) => `${name}${row.isRegression ? " · 回归" : ""}` },
            { title: "cron", dataIndex: "cron" },
            {
              title: "启用",
              dataIndex: "enabled",
              render: (enabled: boolean, row) => (
                <Switch checked={enabled} onChange={(checked) => save.mutate({ id: row.id, enabled: checked })} />
              ),
            },
            {
              title: "操作",
              render: (_, row) => (
                <Button
                  size="small"
                  onClick={() => {
                    setEditing(row);
                    setNextCron(row.cron);
                  }}
                >
                  修改 cron
                </Button>
              ),
            },
          ]}
        />
      ) : null}
      <Modal
        title="修改 cron"
        open={editing !== null}
        onCancel={() => setEditing(null)}
        onOk={() => editing && save.mutate({ id: editing.id, cron: nextCron.trim() })}
        confirmLoading={save.isPending}
      >
        <Input value={nextCron} onChange={(event) => setNextCron(event.target.value)} aria-label="新的 cron" />
      </Modal>
    </div>
  );
}
