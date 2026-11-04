import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Drawer, Empty, Select, Space, Table, Tag, Typography } from "antd";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { errorText } from "../api/client";
import { getDefect, listDefects, updateDefectStatus, type DefectItem } from "../api/resources";
import { useUiStore } from "../stores/ui";
import { formatTime } from "../utils/format";

const STATUS: Record<string, string> = {
  candidate: "候选",
  watching: "继续观察",
  dismissed: "已排除",
};

export function DefectPage() {
  const projectId = useUiStore((state) => state.selectedProjectId);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ["defects", projectId],
    queryFn: async () => (await listDefects(projectId ?? "")).data,
    enabled: Boolean(projectId),
  });
  const detail = useQuery({
    queryKey: ["defect", currentId],
    queryFn: async () => (await getDefect(currentId ?? "")).data,
    enabled: Boolean(currentId),
  });
  const change = useMutation({
    mutationFn: (input: { id: string; status: string }) => updateDefectStatus(input.id, input.status),
    onSuccess: async () => {
      setError(null);
      await queryClient.invalidateQueries({ queryKey: ["defects", projectId] });
      await queryClient.invalidateQueries({ queryKey: ["defect", currentId] });
    },
    onError: (caught: unknown) => setError(errorText(caught)),
  });

  if (!projectId) {
    return <Alert type="info" showIcon message="请先选择项目。" action={<Button onClick={() => navigate("/projects")}>项目列表</Button>} />;
  }

  const items = query.data?.items ?? [];
  return (
    <div className="page-stack">
      <Typography.Title level={3} style={{ margin: 0 }}>
        候选缺陷
      </Typography.Title>
      <Alert type="warning" showIcon message={query.data?.label ?? "这些记录是失败候选，不是已确认缺陷，也不是已确认漏洞。"} />
      {query.isError ? <Alert type="error" showIcon message={errorText(query.error)} /> : null}
      {error ? <Alert type="error" showIcon message={error} /> : null}
      {!query.isLoading && items.length === 0 ? (
        <Empty description="还没有候选缺陷。执行出现断言失败后才会生成。" />
      ) : (
        <Table<DefectItem>
          rowKey="id"
          loading={query.isLoading}
          dataSource={items}
          pagination={{ pageSize: 8 }}
          onRow={(record) => ({ onClick: () => setCurrentId(record.id) })}
          columns={[
            { title: "标题", dataIndex: "title" },
            {
              title: "状态",
              dataIndex: "status",
              render: (value: string) => <Tag>{STATUS[value] ?? value}</Tag>,
            },
            { title: "时间", dataIndex: "createdAt", render: (value: string) => formatTime(value) },
          ]}
        />
      )}
      <Drawer title="候选详情" open={currentId !== null} width={560} onClose={() => setCurrentId(null)}>
        {detail.data ? (
          <Space direction="vertical" style={{ width: "100%" }} size="middle">
            <Alert type="warning" showIcon message={detail.data.label} />
            <div>{detail.data.title}</div>
            <Select
              value={detail.data.status}
              options={Object.entries(STATUS).map(([value, label]) => ({ value, label }))}
              onChange={(status) => change.mutate({ id: detail.data.id, status })}
              style={{ width: 180 }}
            />
            <Typography.Text type="secondary">关联执行 {detail.data.runId ?? "无"}</Typography.Text>
            <pre className="json-preview">{JSON.stringify(detail.data.detail, null, 2)}</pre>
          </Space>
        ) : null}
      </Drawer>
    </div>
  );
}
