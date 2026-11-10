import { http, unwrap } from "./client";
import type { AuditItem, DashboardSummary, Project, ProjectDraft, ProjectPage, User } from "./types";

export function login(username: string, password: string) {
  return unwrap<User>(http.post("/auth/login", { username, password }));
}

export function logout() {
  return unwrap<{ loggedOut: boolean }>(http.post("/auth/logout"));
}

export function currentUser() {
  return unwrap<User>(http.get("/auth/me"));
}

export function myAudit() {
  return unwrap<{ items: AuditItem[] }>(http.get("/auth/audit"));
}

export function listProjects(params: { q?: string; page: number; pageSize: number }) {
  return unwrap<ProjectPage>(http.get("/projects", { params }));
}

export function createProject(body: ProjectDraft) {
  return unwrap<Project>(http.post("/projects", body));
}

export function getProject(id: string) {
  return unwrap<Project>(http.get(`/projects/${id}`));
}

export function dashboardSummary() {
  return unwrap<DashboardSummary>(http.get("/dashboard/summary"));
}

export interface EndpointItem {
  id: string;
  method: string;
  path: string;
  summary: string;
  specVersion: number;
}

export interface GenerationTask {
  id: string;
  status: string;
  provider: string;
  model?: string | null;
  targetCount: number;
  succeededCount: number;
  failedCount: number;
  error: string | null;
}

export interface Assertion {
  type: string;
  expected?: unknown;
  path?: string;
  minimum?: number;
  maximum?: number;
}

export interface CaseVersion {
  id: string;
  caseId: string;
  projectId: string | null;
  versionNumber: number;
  name: string;
  description: string;
  scenario: string;
  basis: string;
  method: string;
  relativePath: string;
  body: unknown;
  assertions: Assertion[];
  reviewStatus: string;
  origin: string;
  events: { id: string; action: string; reason: string | null; createdAt: string }[];
  history: { id: string; versionNumber: number; reviewStatus: string; name: string }[];
}

export interface RunItem {
  id: string;
  projectId: string;
  projectName: string | null;
  status: string;
  totalCount: number;
  executedCount: number;
  passedCount: number;
  assertionFailedCount: number;
  executionErrorCount: number;
  skippedCount: number;
  passRate: number | null;
  passRateText: string;
  abortReason: string | null;
  createdAt: string;
  finishedAt: string | null;
  results: {
    id: string;
    status: string;
    responseStatus: number | null;
    errorClass: string | null;
    errorMessage: string | null;
    request: { method?: string; url?: string; body?: unknown };
    responseBody: string | null;
    assertionResults: { type: string; passed: boolean; message: string; errorClass: string | null; expected: unknown; actual: unknown }[];
  }[];
}

export interface ReportItem {
  id: string;
  runId: string;
  aiStatus: string;
  aiMessage: string;
  createdAt: string;
  data: {
    status: string;
    totalCount: number;
    executedCount: number;
    passedCount: number;
    assertionFailedCount: number;
    executionErrorCount: number;
    skippedCount: number;
    passRate: number | null;
    passRateText: string;
    snapshot: { baseUrl?: string; specVersions?: number[] };
    results: RunItem["results"];
  };
}

export function loadDemoContract(projectId: string) {
  return unwrap<{ items: EndpointItem[] }>(http.post(`/projects/${projectId}/contract/demo`));
}

export function listEndpoints(projectId: string) {
  return unwrap<{ items: EndpointItem[] }>(http.get(`/projects/${projectId}/endpoints`));
}

export function createGeneration(projectId: string) {
  return unwrap<GenerationTask>(http.post(`/projects/${projectId}/generation-tasks`));
}

export function getGeneration(taskId: string) {
  return unwrap<GenerationTask>(http.get(`/generation-tasks/${taskId}`));
}

export function listCases(projectId: string, reviewStatus?: string) {
  return unwrap<{ items: CaseVersion[] }>(http.get(`/projects/${projectId}/cases`, { params: { reviewStatus } }));
}

export function submitCase(versionId: string) {
  return unwrap<CaseVersion>(http.post(`/case-versions/${versionId}/submit`));
}

export function approveCase(versionId: string) {
  return unwrap<CaseVersion>(http.post(`/case-versions/${versionId}/approve`));
}

export function rejectCase(versionId: string, reason: string) {
  return unwrap<CaseVersion>(http.post(`/case-versions/${versionId}/reject`, { reason }));
}

export function editCase(versionId: string, body: { name?: string; description?: string; assertions?: Assertion[] }) {
  return unwrap<CaseVersion>(http.post(`/case-versions/${versionId}/edit`, body));
}

export function createRun(projectId: string, confirmWrites: boolean) {
  return unwrap<RunItem>(http.post(`/projects/${projectId}/runs`, { confirmWrites }));
}

export function listRuns(projectId: string) {
  return unwrap<{ items: RunItem[] }>(http.get(`/projects/${projectId}/runs`));
}

export function getRun(runId: string) {
  return unwrap<RunItem>(http.get(`/runs/${runId}`));
}

export function cancelRun(runId: string) {
  return unwrap<RunItem>(http.post(`/runs/${runId}/cancel`));
}

export function getReport(runId: string) {
  return unwrap<ReportItem>(http.get(`/runs/${runId}/report`));
}

export function listReports(projectId: string) {
  return unwrap<{ items: ReportItem[] }>(http.get(`/projects/${projectId}/reports`));
}

export function previewOpenApi(projectId: string, document: string) {
  return unwrap<{
    endpoints: { method: string; path: string; summary: string }[];
    errors: { loc: string; msg: string }[];
    warnings?: { loc: string; msg: string }[];
  }>(
    http.post(`/projects/${projectId}/openapi/preview`, { document }),
  );
}

export function confirmOpenApi(projectId: string, document: string) {
  return unwrap<{ saved: number; disabled: number }>(http.post(`/projects/${projectId}/openapi/confirm`, { document }));
}

export function checkTarget(projectId: string) {
  return unwrap<{ baseUrl: string; allowed: boolean }>(http.post(`/projects/${projectId}/target-check`));
}

export interface GithubCandidate {
  path: string;
  parseOk: boolean;
  endpointCount: number;
  error: string;
  openapi?: string;
}

export interface GithubDetection {
  url: string;
  repo: { fullName: string; description: string; language: string; defaultBranch: string; htmlUrl: string };
  ref: string;
  fileCount: number;
  frameworks: string[];
  specCandidates: GithubCandidate[];
}

export function detectGithubProject(projectId: string, url: string) {
  return unwrap<GithubDetection>(http.post(`/projects/${projectId}/github/detect`, { url }));
}

export function importGithubSpec(projectId: string, url: string, specPath: string, autoGenerate: boolean) {
  return unwrap<{ saved: number; disabled: number; generationTaskId?: string }>(
    http.post(`/projects/${projectId}/github/import`, { url, specPath, autoGenerate }),
  );
}

export function createDependencyDemo(projectId: string) {
  return unwrap<{ suiteId: string }>(http.post(`/projects/${projectId}/dependency-demo`));
}

export function listSuites(projectId: string) {
  return unwrap<{ items: { id: string; name: string; isRegression: boolean; caseIds: string[] }[] }>(
    http.get(`/projects/${projectId}/suites`),
  );
}

export function runSuite(suiteId: string, confirmWrites: boolean) {
  return unwrap<RunItem>(http.post(`/suites/${suiteId}/runs`, { confirmWrites }));
}

export interface EnvironmentItem {
  id: string;
  name: string;
  baseUrl: string;
  isActive: boolean;
}

export interface MemberItem {
  id: string;
  username: string;
  displayName: string;
  role: string;
}

export interface NotificationItem {
  id: string;
  title: string;
  body: string;
  readAt: string | null;
  createdAt: string;
}

export interface DefectItem {
  id: string;
  projectId: string;
  runId: string | null;
  title: string;
  status: string;
  detail: Record<string, unknown>;
  createdAt: string;
  label: string;
}

export interface ScheduleItem {
  id: string;
  suiteId: string;
  suiteName: string;
  isRegression: boolean;
  cron: string;
  enabled: boolean;
  nextRunAt: string | null;
  createdAt: string;
}

export interface ScheduleEventItem {
  id: string;
  kind: string;
  message: string;
  runId: string | null;
  createdAt: string;
}

export function listEnvironments(projectId: string) {
  return unwrap<{ items: EnvironmentItem[] }>(http.get(`/projects/${projectId}/environments`));
}

export function createEnvironment(projectId: string, body: { name: string; baseUrl: string }) {
  return unwrap<EnvironmentItem>(http.post(`/projects/${projectId}/environments`, body));
}

export function activateEnvironment(projectId: string, environmentId: string) {
  return unwrap<{ active: string }>(http.post(`/projects/${projectId}/environments/${environmentId}/activate`));
}

export function deleteEnvironment(projectId: string, environmentId: string) {
  return unwrap<{ deleted: boolean }>(http.delete(`/projects/${projectId}/environments/${environmentId}`));
}

export function archiveProject(projectId: string) {
  return unwrap<{ id: string; status: string }>(http.post(`/projects/${projectId}/archive`));
}

export function restoreProject(projectId: string) {
  return unwrap<{ id: string; status: string }>(http.post(`/projects/${projectId}/restore`));
}

export function deleteProject(projectId: string) {
  return unwrap<{ deleted: boolean }>(http.post(`/projects/${projectId}/delete`, { confirm: true }));
}

export function listMembers(projectId: string) {
  return unwrap<{ owner: MemberItem & { userId: string }; items: MemberItem[] }>(http.get(`/projects/${projectId}/members`));
}

export function addMember(projectId: string, username: string, role: string) {
  return unwrap<{ id: string; role: string }>(http.post(`/projects/${projectId}/members`, { username, role }));
}

export function updateMemberRole(projectId: string, memberId: string, role: string) {
  return unwrap<{ id: string; role: string }>(http.post(`/projects/${projectId}/members/${memberId}/role`, { role }));
}

export function removeMember(projectId: string, memberId: string) {
  return unwrap<{ deleted: boolean }>(http.delete(`/projects/${projectId}/members/${memberId}`));
}

export function batchReview(projectId: string, action: "approve" | "reject", versionIds: string[], reason?: string) {
  return unwrap<{ count: number }>(http.post(`/projects/${projectId}/reviews/batch`, { action, versionIds, reason }));
}

export function listNotifications() {
  return unwrap<{ items: NotificationItem[]; unreadCount: number }>(http.get("/notifications"));
}

export function markNotificationRead(id: string) {
  return unwrap<NotificationItem>(http.post(`/notifications/${id}/read`));
}

export function markAllNotificationsRead() {
  return unwrap<{ count: number }>(http.post("/notifications/read-all"));
}

export function listDefects(projectId: string) {
  return unwrap<{ items: DefectItem[]; label: string }>(http.get(`/projects/${projectId}/defects`));
}

export function getDefect(id: string) {
  return unwrap<DefectItem>(http.get(`/defects/${id}`));
}

export function updateDefectStatus(id: string, status: string) {
  return unwrap<DefectItem>(http.post(`/defects/${id}/status`, { status }));
}

export function listSchedules(projectId: string) {
  return unwrap<{ items: ScheduleItem[]; note: string }>(http.get(`/projects/${projectId}/schedules`));
}

export function createSchedule(suiteId: string, cron: string) {
  return unwrap<{ id: string; cron: string; enabled: boolean; note: string }>(http.post(`/suites/${suiteId}/schedules`, { cron }));
}

export function updateSchedule(scheduleId: string, body: { cron?: string; enabled?: boolean }) {
  return unwrap<{ id: string; cron: string; enabled: boolean }>(http.post(`/schedules/${scheduleId}`, body));
}

export function listScheduleEvents(scheduleId: string) {
  return unwrap<{ items: ScheduleEventItem[] }>(http.get(`/schedules/${scheduleId}/events`));
}

export function createSuite(projectId: string, body: { name: string; caseIds: string[]; isRegression: boolean }) {
  return unwrap<{ id: string; name: string; isRegression: boolean }>(http.post(`/projects/${projectId}/suites`, body));
}

export async function downloadReport(runId: string, format: "html" | "json") {
  const response = await fetch(`/api/v1/runs/${runId}/report/export?format=${format}`, { credentials: "include" });
  if (!response.ok) {
    let message = "导出失败";
    try {
      const body = (await response.json()) as { message?: string };
      if (body.message) message = body.message;
    } catch {
      message = "导出失败";
    }
    throw new Error(message);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `zhitest-report-${runId.slice(0, 8)}.${format === "html" ? "html" : "json"}`;
  link.click();
  URL.revokeObjectURL(url);
}
