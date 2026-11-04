import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, List, Space, Typography } from "antd";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { errorText } from "../api/client";
import { createDependencyDemo, listSuites, runSuite } from "../api/resources";
import { useUiStore } from "../stores/ui";

export function SuitePage() {
  const projectId = useUiStore((state) => state.selectedProjectId);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ["suites", projectId],
    queryFn: async () => (await listSuites(projectId ?? "")).data.items,
    enabled: Boolean(projectId),
  });
  const demo = useMutation({
    mutationFn: () => createDependencyDemo(projectId ?? ""),
    onSuccess: async () => {
      setMessage(null);
      await queryClient.invalidateQueries({ queryKey: ["suites", projectId] });
    },
    onError: (error: unknown) => setMessage(errorText(error)),
  });
  const run = useMutation({
    mutationFn: (suiteId: string) => runSuite(suiteId, true),
    onSuccess: () => navigate("/runs"),
    onError: (error: unknown) => setMessage(errorText(error)),
  });

  if (!projectId) {
    return <Alert type="info" showIcon message="请先选择项目。" />;
  }
  return (
    <div className="page-stack">
      <Space style={{ justifyContent: "space-between" }} wrap>
        <Typography.Title level={3} style={{ margin: 0 }}>
          测试用例集
        </Typography.Title>
        <Button onClick={() => demo.mutate()} loading={demo.isPending}>
          添加依赖链示例
        </Button>
      </Space>
      <Alert type="info" showIcon message="依赖链示例会创建“创建商品并提取编号”和“用提取的编号查询商品”。执行时第二步使用第一步提取的 productId。" />
      {message ? <Alert type="error" showIcon message={message} /> : null}
      <List
        loading={query.isLoading}
        dataSource={query.data ?? []}
        locale={{ emptyText: "还没有用例集" }}
        renderItem={(item) => (
          <List.Item
            actions={[
              <Button key="run" type="primary" onClick={() => run.mutate(item.id)} loading={run.isPending}>
                执行用例集
              </Button>,
            ]}
          >
            <List.Item.Meta title={item.name} description={`${item.caseIds.length} 条用例${item.isRegression ? " · 回归集" : ""}`} />
          </List.Item>
        )}
      />
    </div>
  );
}
