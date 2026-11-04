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
