import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Descriptions, Input, Space, Statistic, Typography } from "antd";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { errorText } from "../api/client";
import {
  checkTarget,
  confirmOpenApi,
  createGeneration,
  detectGithubProject,
  getGeneration,
  getProject,
  importGithubSpec,
  listEndpoints,
  loadDemoContract,
  previewOpenApi,
  type GithubDetection,
} from "../api/resources";
import { useUiStore } from "../stores/ui";
import { RUN_LABEL, formatTime } from "../utils/format";

export function ProjectDetailPage() {
  const { projectId = "" } = useParams();
  const navigate = useNavigate();
  const setSelectedProjectId = useUiStore((state) => state.setSelectedProjectId);
  const queryClient = useQueryClient();
  const [taskId, setTaskId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [openApiText, setOpenApiText] = useState("");
  const [previewText, setPreviewText] = useState("");
  const [githubUrl, setGithubUrl] = useState("");
  const [githubResult, setGithubResult] = useState<GithubDetection | null>(null);
  const [githubBusy, setGithubBusy] = useState(false);
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
        message="演示契约是本阶段作者编写的，不是团队缺失的原文档。没有配置密钥时生成仍使用 Mock Provider。"
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
        <Button onClick={() => navigate("/suites")}>用例集</Button>
        <Button onClick={() => navigate(`/projects/${projectId}/manage`)}>环境与成员</Button>
        <Button onClick={() => navigate("/defects")}>候选缺陷</Button>
        <Button onClick={() => navigate("/schedules")}>定时执行</Button>
        <Button
          onClick={async () => {
            try {
              const result = await checkTarget(projectId);
              setActionError(null);
              setPreviewText(`目标 ${result.data.baseUrl} 通过检查`);
            } catch (error) {
              setActionError(errorText(error));
            }
          }}
        >
          检查执行目标
        </Button>
      </Space>
      <Card title="OpenAPI 3.x">
        <Input.TextArea rows={6} value={openApiText} onChange={(event) => setOpenApiText(event.target.value)} placeholder="粘贴 JSON 或 YAML" />
        <Space style={{ marginTop: 12 }}>
          <Button
            onClick={async () => {
              try {
                const result = await previewOpenApi(projectId, openApiText);
                setActionError(null);
                const lines = result.data.endpoints.map((item) => `${item.method} ${item.path}`);
                const notes = (result.data.warnings ?? []).map((item) => item.msg);
                setPreviewText([...lines, ...notes].join("\n") || "没有接口");
              } catch (error) {
                setActionError(errorText(error));
              }
            }}
          >
            预览
          </Button>
          <Button
            type="primary"
            onClick={async () => {
              try {
                const result = await confirmOpenApi(projectId, openApiText);
                setActionError(null);
                setPreviewText(`已保存 ${result.data.saved} 个接口`);
                await queryClient.invalidateQueries({ queryKey: ["endpoints", projectId] });
                await queryClient.invalidateQueries({ queryKey: ["project", projectId] });
              } catch (error) {
                setActionError(errorText(error));
              }
            }}
          >
            确认导入
          </Button>
          <input
            aria-label="上传 OpenAPI 文件"
            type="file"
            accept=".json,.yaml,.yml"
            onChange={async (event) => {
              const file = event.target.files?.[0];
              if (!file) return;
              setOpenApiText(await file.text());
            }}
          />
        </Space>
        {previewText ? <pre className="json-preview">{previewText}</pre> : null}
      </Card>
      <Card title="GitHub 项目接入">
        <Space wrap>
          <Input
            style={{ width: 380 }}
            value={githubUrl}
            onChange={(event) => setGithubUrl(event.target.value)}
            placeholder="https://github.com/owner/repo"
          />
          <Button
            loading={githubBusy}
            onClick={async () => {
              try {
                setGithubBusy(true);
                const result = await detectGithubProject(projectId, githubUrl);
                setActionError(null);
                setGithubResult(result.data);
              } catch (error) {
                setGithubResult(null);
                setActionError(errorText(error));
              } finally {
                setGithubBusy(false);
              }
            }}
          >
            检测项目
          </Button>
        </Space>
        {githubResult ? (
          <div className="page-stack" style={{ marginTop: 12 }}>
            <Alert
              type="success"
              showIcon
              message={`${githubResult.repo.fullName}（${githubResult.repo.language || "未标注语言"}，分支 ${githubResult.ref}，约 ${githubResult.fileCount} 个文件）`}
              description={
                githubResult.repo.description
                  ? `${githubResult.repo.description}；框架指纹：${githubResult.frameworks.join("、")}`
                  : `框架指纹：${githubResult.frameworks.join("、")}`
              }
            />
            {githubResult.specCandidates.length === 0 ? (
              <Alert
                type="warning"
                showIcon
                message="没有找到 OpenAPI/Swagger 接口定义文件。可以粘贴文档到上方 OpenAPI 区域，或检查仓库中是否包含 openapi.json / swagger.yaml 等文件。"
              />
            ) : (
              githubResult.specCandidates.map((candidate) => (
                <Card key={candidate.path} size="small" title={candidate.path}>
                  {candidate.parseOk ? (
                    <Space wrap>
                      <span>
                        解析通过，{candidate.endpointCount} 个接口（OpenAPI {candidate.openapi ?? ""}）
                      </span>
                      <Button
                        onClick={async () => {
                          try {
                            const result = await importGithubSpec(projectId, githubUrl, candidate.path, false);
                            setActionError(null);
                            setPreviewText(`已导入 ${result.data.saved} 个接口`);
                            await queryClient.invalidateQueries({ queryKey: ["endpoints", projectId] });
                            await queryClient.invalidateQueries({ queryKey: ["project", projectId] });
                          } catch (error) {
                            setActionError(errorText(error));
                          }
                        }}
                      >
                        导入接口
                      </Button>
                      <Button
                        type="primary"
                        onClick={async () => {
                          try {
                            const result = await importGithubSpec(projectId, githubUrl, candidate.path, true);
                            setActionError(null);
                            setPreviewText(`已导入 ${result.data.saved} 个接口，用例生成任务已入队`);
                            await queryClient.invalidateQueries({ queryKey: ["endpoints", projectId] });
                            await queryClient.invalidateQueries({ queryKey: ["project", projectId] });
                            if (result.data.generationTaskId) setTaskId(result.data.generationTaskId);
                          } catch (error) {
                            setActionError(errorText(error));
                          }
                        }}
                      >
                        导入并生成用例
                      </Button>
                    </Space>
                  ) : (
                    <span>解析失败：{candidate.error || "未知原因"}</span>
                  )}
                </Card>
              ))
            )}
          </div>
        ) : null}
      </Card>
      {generation.data ? (
        <Alert
          type={generation.data.status === "failed" ? "error" : "info"}
          showIcon
          message={`生成任务 ${generation.data.status}（${generation.data.model ? `${generation.data.provider} / ${generation.data.model}` : generation.data.provider}）成功 ${generation.data.succeededCount} / 失败 ${generation.data.failedCount}`}
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
