export interface User {
  id: string;
  username: string;
  displayName: string;
  role: string;
}

export interface Project {
  id: string;
  ownerId: string;
  name: string;
  description: string;
  baseUrl: string;
  envLabel: string;
  endpointCount: number;
  caseCount: number;
  lastRun: {
    id: string;
    status: string;
    finishedAt: string | null;
    passRate: number | null;
    passRateText: string;
  } | null;
  createdAt: string;
  updatedAt: string;
}

export interface ProjectPage {
  items: Project[];
  page: number;
  pageSize: number;
  total: number;
}

export interface RecentTask {
  id: string;
  projectId: string;
  projectName: string;
  status: string;
  createdAt: string;
  passRate: number | null;
  passRateText: string;
}

export interface Activity {
  id: string;
  action: string;
  resourceType: string | null;
  resourceId: string | null;
  detail: Record<string, string>;
  createdAt: string;
}

export interface DashboardSummary {
  projectCount: number;
  caseCount: number;
  pendingReviewCount: number;
  failedCaseCount: number;
  passRate: number | null;
  passRateText: string;
  executionDataAvailable: boolean;
  metricsNote: string;
  recentTasks: RecentTask[];
  recentProjects: Project[];
  recentActivities: Activity[];
}

export interface AuditItem {
  id: string;
  action: string;
  resourceType: string | null;
  resourceId: string | null;
  detail: Record<string, string>;
  requestId: string | null;
  createdAt: string;
}

export interface ProjectDraft {
  name: string;
  description: string;
  baseUrl: string;
  envLabel: string;
}
