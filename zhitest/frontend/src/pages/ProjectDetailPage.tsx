import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Descriptions, Space, Statistic, Typography } from "antd";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { errorText } from "../api/client";
import { createGeneration, getGeneration, getProject, listEndpoints, loadDemoContract } from "../api/resources";
import { useUiStore } from "../stores/ui";
import { RUN_LABEL, formatTime } from "../utils/format";

export function ProjectDetailPage() {
  const { projectId = "" } = useParams();
  const navigate = useNavigate();
  const setSelectedProjectId = useUiStore((state) => state.setSelectedProjectId);
  const queryClient = useQueryClient();
  const [taskId, setTaskId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ["project", projectId],
    queryFn: async () => (await getProject(projectId)).data,
    enabled: projectId.length > 0,
    retry: false,
  });
  const endpoints = useQuery({
    queryKey: ["endpoints", projectId],
    queryFn: async () => (await listEndpoints(projectId)).data.items,
    enabled: projectId.length > 0,
  });
  const generation = useQuery({
    queryKey: ["generation", taskId],
    queryFn: async () => (await getGeneration(taskId ?? "")).data,
    enabled: Boolean(taskId),
    refetchInterval: (current) => {
      const status = current.state.data?.status;
      return status === "queued" || status === "running" ? 2000 : false;
    },
  });
  const loadContract = useMutation({
    mutationFn: () => loadDemoContract(projectId),
    onSuccess: async () => {
      setActionError(null);
      await queryClient.invalidateQueries({ queryKey: ["endpoints", projectId] });
      await queryClient.invalidateQueries({ queryKey: ["project", projectId] });
    },
    onError: (error: unknown) => setActionError(errorText(error)),
  });
  const generate = useMutation({
    mutationFn: () => createGeneration(projectId),
    onSuccess: (envelope) => {
      setActionError(null);
      setTaskId(envelope.data.id);
    },
    onError: (error: unknown) => setActionError(errorText(error)),
  });

  useEffect(() => {
    if (query.data) setSelectedProjectId(query.data.id);
  }, [query.data, setSelectedProjectId]);

  useEffect(() => {
    if (generation.data?.status === "succeeded" || generation.data?.status === "failed") {
      void queryClient.invalidateQueries({ queryKey: ["project", projectId] });
    }
  }, [generation.data?.status, projectId, queryClient]);

  if (query.isLoading) return <Card loading />;
  if (query.isError || !query.data) {
    return (
      <Alert
        type="error"
        showIcon
        message={errorText(query.error)}
        action={<Button onClick={() => navigate("/projects")}>返回列表</Button>}
      />
    );
  }
  const project = query.data;
  return (
    <div className="page-stack">
      <Space style={{ justifyContent: "space-between" }} wrap>
        <Typography.Title level={3} style={{ margin: 0 }}>
          {project.name}
        </Typography.Title>
        <Button onClick={() => navigate("/projects")}>返回列表</Button>
      </Space>
      <Alert
        type="info"
        showIcon
        message="演示契约是本阶段作者编写的，不是团队缺失的原文档。生成使用 Mock Provider。多环境、归档和删除仍未实现。"
      />
      {actionError ? <Alert type="error" showIcon message={actionError} /> : null}
      <Space wrap>
        <Button onClick={() => loadContract.mutate()} loading={loadContract.isPending}>
          载入演示契约
        </Button>
        <Button type="primary" onClick={() => generate.mutate()} loading={generate.isPending}>
          生成测试草稿
        </Button>
        <Button onClick={() => navigate("/reviews")}>去审核</Button>
      </Space>
      {generation.data ? (
        <Alert
          type={generation.data.status === "failed" ? "error" : "info"}
          showIcon
          message={`生成任务 ${generation.data.status}（${generation.data.provider}）成功 ${generation.data.succeededCount} / 失败 ${generation.data.failedCount}`}
        />
      ) : null}
      <Card title="接口">
        {(endpoints.data ?? []).length === 0 ? "尚未载入契约" : null}
        {(endpoints.data ?? []).map((item) => (
          <div key={item.id}>
            {item.method} {item.path} {item.summary}
          </div>
        ))}
      </Card>
      <Card>
        <Descriptions column={{ xs: 1, md: 2 }}>
          <Descriptions.Item label="环境标签">{project.envLabel}</Descriptions.Item>
          <Descriptions.Item label="Base URL">{project.baseUrl}</Descriptions.Item>
          <Descriptions.Item label="创建时间">{formatTime(project.createdAt)}</Descriptions.Item>
          <Descriptions.Item label="更新时间">{formatTime(project.updatedAt)}</Descriptions.Item>
          <Descriptions.Item label="描述" span={2}>
            {project.description || "无描述"}
          </Descriptions.Item>
        </Descriptions>
      </Card>
      <Space size="large" wrap>
        <Card>
          <Statistic title="接口数" value={project.endpointCount} />
          <div className="stat-note">来自已保存的接口契约</div>
        </Card>
        <Card>
          <Statistic title="用例数" value={project.caseCount} />
          <div className="stat-note">含草稿，不等于已确认</div>
        </Card>
        <Card>
          <Statistic
            title="最近执行"
            value={project.lastRun ? RUN_LABEL[project.lastRun.status] ?? project.lastRun.status : "暂无执行记录"}
          />
        </Card>
      </Space>
    </div>
  );
}
