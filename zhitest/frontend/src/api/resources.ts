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
