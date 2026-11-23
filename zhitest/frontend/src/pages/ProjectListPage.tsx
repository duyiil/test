import { PlusOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Card, Col, Empty, Input, Pagination, Row, Space, Tag, Typography } from "antd";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { errorText } from "../api/client";
import { listProjects } from "../api/resources";
import { RUN_LABEL, formatTime } from "../utils/format";

export function ProjectListPage() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 9;
  const query = useQuery({
    queryKey: ["projects", q, page, pageSize],
    queryFn: async () => (await listProjects({ q, page, pageSize })).data,
  });

  return (
    <div className="page-stack">
      <Space style={{ justifyContent: "space-between" }} wrap>
        <Typography.Title level={3} style={{ margin: 0 }}>
          项目与资产
        </Typography.Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate("/projects/new")}>
          新建项目
        </Button>
      </Space>
      <Input.Search
        allowClear
        placeholder="搜索项目名称"
        onSearch={(value) => {
          setQ(value.trim());
          setPage(1);
        }}
        style={{ maxWidth: 360 }}
      />
      {query.isError ? <Alert type="error" showIcon message={errorText(query.error)} /> : null}
      {query.isLoading ? <Card loading /> : null}
      {query.data && query.data.total === 0 ? (
        <Card>
          <Empty description={q ? "没有符合条件的项目" : "还没有项目"}>
            {!q ? (
              <Button type="primary" onClick={() => navigate("/projects/new")}>
                新建项目
              </Button>
            ) : null}
          </Empty>
        </Card>
      ) : null}
      {query.data && query.data.items.length > 0 ? (
        <>
          <Row gutter={[16, 16]}>
            {query.data.items.map((project) => (
              <Col xs={24} md={12} xl={8} key={project.id}>
                <Card
                  hoverable
                  title={project.name}
                  extra={
                    <Space>
                      {project.status === "archived" ? <Tag color="default">已归档</Tag> : null}
                      <Tag>{project.envLabel}</Tag>
                    </Space>
                  }
                  onClick={() => navigate(`/projects/${project.id}`)}
                >
                  <Typography.Paragraph ellipsis={{ rows: 2 }}>{project.description || "无描述"}</Typography.Paragraph>
                  <Typography.Text type="secondary">{project.baseUrl}</Typography.Text>
                  <div className="stat-note">接口 {project.endpointCount} · 用例 {project.caseCount}</div>
                  <div className="stat-note">
                    {project.lastRun
                      ? `最近执行 ${RUN_LABEL[project.lastRun.status] ?? project.lastRun.status} · ${project.lastRun.passRateText}`
                      : "暂无执行记录"}
                    {" · 更新于 "}
                    {formatTime(project.updatedAt)}
                  </div>
                </Card>
              </Col>
            ))}
          </Row>
          <Pagination
            current={query.data.page}
            pageSize={query.data.pageSize}
            total={query.data.total}
            onChange={(next) => setPage(next)}
            showSizeChanger={false}
          />
        </>
      ) : null}
    </div>
  );
}
