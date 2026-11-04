import { PlusOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Card, Col, Empty, List, Row, Space, Statistic, Tooltip, Typography } from "antd";
import { useNavigate } from "react-router-dom";
import { errorText } from "../api/client";
import { dashboardSummary } from "../api/resources";
import { PassRateChart } from "../components/PassRateChart";
import { actionLabel, formatTime } from "../utils/format";

export function DashboardPage() {
  const navigate = useNavigate();
  const query = useQuery({
    queryKey: ["dashboard"],
    queryFn: async () => (await dashboardSummary()).data,
    refetchOnWindowFocus: true,
  });

  if (query.isLoading) {
    return <Card loading />;
  }
  if (query.isError || !query.data) {
    return <Alert type="error" showIcon message={errorText(query.error)} action={<Button onClick={() => query.refetch()}>重试</Button>} />;
  }

  const data = query.data;
  return (
    <div className="page-stack">
      <Space style={{ justifyContent: "space-between" }} align="center">
        <div>
          <Typography.Title level={3} style={{ margin: 0 }}>
            工作台
          </Typography.Title>
          <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
            {data.metricsNote}
          </Typography.Paragraph>
        </div>
        <Space wrap>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate("/projects/new")}>
            快速创建项目
          </Button>
          <Tooltip title="用例生成属于后续 Sprint，本阶段未实现">
            <Button disabled>快速生成测试</Button>
          </Tooltip>
          <Tooltip title="报告属于后续 Sprint，本阶段未实现">
            <Button disabled>快速查看报告</Button>
          </Tooltip>
        </Space>
      </Space>
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} xl={6}>
          <Card>
            <Statistic title="项目数量" value={data.projectCount} />
          </Card>
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <Card>
            <Statistic title="测试用例数量" value={data.caseCount} />
            <div className="stat-note">用例表尚未建立</div>
          </Card>
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <Card>
            <Statistic title="待审核数量" value={data.pendingReviewCount} />
            <div className="stat-note">审核模块尚未建立</div>
          </Card>
        </Col>
        <Col xs={24} sm={12} xl={6}>
          <Card>
            <Statistic title="失败用例数量" value={data.failedCaseCount} />
            <div className="stat-note">尚无执行记录</div>
          </Card>
        </Col>
      </Row>
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={14}>
          <Card title="执行通过率">
            <PassRateChart points={[]} />
            <Typography.Text type="secondary">{data.passRateText}</Typography.Text>
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title="最近执行任务">
            {data.recentTasks.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无执行任务" /> : null}
          </Card>
        </Col>
      </Row>
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title="最近项目">
            {data.recentProjects.length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有项目">
                <Button type="primary" onClick={() => navigate("/projects/new")}>
                  新建项目
                </Button>
              </Empty>
            ) : (
              <List
                dataSource={data.recentProjects}
                renderItem={(project) => (
                  <List.Item actions={[<Button key="open" type="link" onClick={() => navigate(`/projects/${project.id}`)}>查看</Button>]}>
                    <List.Item.Meta title={project.name} description={`${project.envLabel} · ${project.baseUrl}`} />
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="最近项目动态">
            {data.recentActivities.length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无项目动态" />
            ) : (
              <List
                dataSource={data.recentActivities}
                renderItem={(item) => (
                  <List.Item>
                    <List.Item.Meta
                      title={actionLabel(item.action)}
                      description={`${item.detail.name ?? item.resourceId ?? ""} · ${formatTime(item.createdAt)}`}
                    />
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
}
