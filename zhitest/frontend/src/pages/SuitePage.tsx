import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Checkbox, Input, List, Modal, Space, Typography } from "antd";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { errorText } from "../api/client";
import { createDependencyDemo, createSuite, listCases, listSuites, runSuite } from "../api/resources";
import { useUiStore } from "../stores/ui";

export function SuitePage() {
  const projectId = useUiStore((state) => state.selectedProjectId);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [regression, setRegression] = useState(true);
  const [caseIds, setCaseIds] = useState<string[]>([]);
  const query = useQuery({
    queryKey: ["suites", projectId],
    queryFn: async () => (await listSuites(projectId ?? "")).data.items,
    enabled: Boolean(projectId),
  });
  const cases = useQuery({
    queryKey: ["cases", projectId, "confirmed"],
    queryFn: async () => (await listCases(projectId ?? "", "confirmed")).data.items,
    enabled: Boolean(projectId) && open,
  });
  const create = useMutation({
    mutationFn: () => createSuite(projectId ?? "", { name: name.trim(), caseIds, isRegression: regression }),
    onSuccess: async () => {
      setOpen(false);
      setName("");
      setCaseIds([]);
      setMessage(null);
      await queryClient.invalidateQueries({ queryKey: ["suites", projectId] });
    },
    onError: (error: unknown) => setMessage(errorText(error)),
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
        <Space>
          <Button type="primary" onClick={() => setOpen(true)}>
            新建用例集
          </Button>
          <Button onClick={() => demo.mutate()} loading={demo.isPending}>
            添加依赖链示例
          </Button>
        </Space>
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
      <Modal
        title="新建用例集"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => create.mutate()}
        okButtonProps={{ disabled: !name.trim() || caseIds.length === 0 }}
        confirmLoading={create.isPending}
      >
        <Space direction="vertical" style={{ width: "100%" }}>
          <Input placeholder="名称" value={name} onChange={(event) => setName(event.target.value)} />
          <Checkbox checked={regression} onChange={(event) => setRegression(event.target.checked)}>
            回归集
          </Checkbox>
          {(cases.data ?? []).length === 0 ? <Typography.Text type="secondary">还没有已确认用例。</Typography.Text> : null}
          <Checkbox.Group
            value={caseIds}
            onChange={(values) => setCaseIds(values.map(String))}
            options={(cases.data ?? []).map((item) => ({ value: item.caseId, label: `${item.method} ${item.name}` }))}
          />
        </Space>
      </Modal>
    </div>
  );
}
