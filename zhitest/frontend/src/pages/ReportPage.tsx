import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Card, Descriptions, List, Space, Typography } from "antd";
import { useState } from "react";
import { DownloadOutlined } from "@ant-design/icons";
import { useNavigate, useSearchParams } from "react-router-dom";
import { errorText } from "../api/client";
import { downloadReport, getReport, listReports } from "../api/resources";
import { useUiStore } from "../stores/ui";
import { RUN_LABEL, formatTime } from "../utils/format";

export function ReportPage() {
  const projectId = useUiStore((state) => state.selectedProjectId);
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const requested = params.get("run");
  const [runId, setRunId] = useState<string | null>(requested);
  const [exportError, setExportError] = useState<string | null>(null);

  const reports = useQuery({
    queryKey: ["reports", projectId],
    queryFn: async () => (await listReports(projectId ?? "")).data.items,
    enabled: Boolean(projectId),
  });
  const activeId = runId ?? reports.data?.[0]?.runId ?? null;
  const report = useQuery({
    queryKey: ["report", activeId],
    queryFn: async () => (await getReport(activeId ?? "")).data,
    enabled: Boolean(activeId),
  });

  if (!projectId) {
    return <Alert type="info" showIcon message="请先选择项目。" action={<Button onClick={() => navigate("/projects")}>项目列表</Button>} />;
  }

  const data = report.data?.data;
  return (
    <div className="page-stack">
      <Typography.Title level={3} style={{ margin: 0 }}>
        测试报告
      </Typography.Title>
      {reports.isError ? <Alert type="error" showIcon message={errorText(reports.error)} /> : null}
      {(reports.data ?? []).length === 0 && !reports.isLoading ? <Alert type="info" showIcon message="还没有数据报告。执行任务进入终态后才会生成。" /> : null}
      <Space wrap>
        {(reports.data ?? []).map((item) => (
          <Button key={item.id} type={item.runId === activeId ? "primary" : "default"} onClick={() => setRunId(item.runId)}>
            {item.runId.slice(0, 8)} · {formatTime(item.createdAt)}
          </Button>
        ))}
      </Space>
      {report.isError ? <Alert type="error" showIcon message={errorText(report.error)} /> : null}
      {exportError ? <Alert type="error" showIcon message={exportError} /> : null}
      {data && activeId ? (
        <>
          <Space>
            <Button
              icon={<DownloadOutlined />}
              onClick={() => {
                setExportError(null);
                downloadReport(activeId, "json").catch((error: unknown) => setExportError(error instanceof Error ? error.message : "导出失败"));
              }}
            >
              下载 JSON
            </Button>
            <Button
              icon={<DownloadOutlined />}
              onClick={() => {
                setExportError(null);
                downloadReport(activeId, "html").catch((error: unknown) => setExportError(error instanceof Error ? error.message : "导出失败"));
              }}
            >
              下载 HTML
            </Button>
          </Space>
          <Alert type={report.data?.aiStatus === "succeeded" ? "success" : "warning"} showIcon message={report.data?.aiMessage} />
          <Card>
            <Descriptions column={{ xs: 1, md: 3 }}>
              <Descriptions.Item label="任务状态">{RUN_LABEL[data.status] ?? data.status}</Descriptions.Item>
              <Descriptions.Item label="断言通过率">{data.passRateText}</Descriptions.Item>
              <Descriptions.Item label="环境">{data.snapshot.baseUrl}</Descriptions.Item>
              <Descriptions.Item label="用例总数">{data.totalCount}</Descriptions.Item>
              <Descriptions.Item label="已执行">{data.executedCount}</Descriptions.Item>
              <Descriptions.Item label="通过">{data.passedCount}</Descriptions.Item>
              <Descriptions.Item label="断言失败">{data.assertionFailedCount}</Descriptions.Item>
              <Descriptions.Item label="执行错误">{data.executionErrorCount}</Descriptions.Item>
              <Descriptions.Item label="跳过">{data.skippedCount}</Descriptions.Item>
            </Descriptions>
          </Card>
          <List
            header="原始结果"
            dataSource={data.results}
            renderItem={(item) => (
              <List.Item>
                <List.Item.Meta
                  title={`${item.request.method ?? ""} ${item.request.url ?? ""} · ${item.status} · HTTP ${item.responseStatus ?? "—"}`}
                  description={item.assertionResults.map((assertion) => assertion.message).join("；") || item.errorMessage}
                />
              </List.Item>
            )}
          />
        </>
      ) : null}
    </div>
  );
}
