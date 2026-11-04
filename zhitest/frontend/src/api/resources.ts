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
