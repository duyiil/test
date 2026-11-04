export function formatTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

const ACTION_LABEL: Record<string, string> = {
  "project.create": "创建项目",
  "auth.login": "登录",
  "auth.logout": "退出登录",
  "auth.login_failed": "登录失败",
};

export function actionLabel(action: string): string {
  return ACTION_LABEL[action] ?? action;
}

export const REVIEW_LABEL: Record<string, string> = {
  draft: "草稿",
  pending_review: "待审核",
  confirmed: "已确认",
  rejected: "已驳回",
};

export const RUN_LABEL: Record<string, string> = {
  queued: "排队",
  running: "执行中",
  succeeded: "已完成",
  failed: "平台失败",
  aborted: "已中止",
  cancelling: "取消中",
  cancelled: "已取消",
};

export function isActiveRun(status: string): boolean {
  return status === "queued" || status === "running" || status === "cancelling";
}
