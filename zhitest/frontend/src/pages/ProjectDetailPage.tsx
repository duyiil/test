import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Card, Descriptions, Space, Statistic, Typography } from "antd";
import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { errorText } from "../api/client";
import { getProject } from "../api/resources";
import { useUiStore } from "../stores/ui";
import { formatTime } from "../utils/format";

export function ProjectDetailPage() {
  const { projectId = "" } = useParams();
  const navigate = useNavigate();
  const setSelectedProjectId = useUiStore((state) => state.setSelectedProjectId);
  const query = useQuery({
    queryKey: ["project", projectId],
    queryFn: async () => (await getProject(projectId)).data,
    enabled: projectId.length > 0,
    retry: false,
  });

  useEffect(() => {
    if (query.data) setSelectedProjectId(query.data.id);
  }, [query.data, setSelectedProjectId]);

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
      <Alert type="info" showIcon message="编辑、多环境切换、归档和删除不在 Phase 1。当前页面只读。" />
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
          <div className="stat-note">接口模块尚未上线</div>
        </Card>
        <Card>
          <Statistic title="用例数" value={project.caseCount} />
          <div className="stat-note">用例模块尚未上线</div>
        </Card>
        <Card>
          <Statistic title="最近执行" value="暂无执行记录" />
        </Card>
      </Space>
    </div>
  );
}
