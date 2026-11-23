import type { ProjectDraft } from "../api/types";

const KEY = "zhitest.draft.project";

export function loadProjectDraft(): ProjectDraft | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<ProjectDraft>;
    return {
      name: parsed.name ?? "",
      description: parsed.description ?? "",
      baseUrl: parsed.baseUrl ?? "",
      envLabel: parsed.envLabel ?? "测试",
    };
  } catch {
    return null;
  }
}

export function saveProjectDraft(draft: ProjectDraft): void {
  sessionStorage.setItem(KEY, JSON.stringify(draft));
}

export function clearProjectDraft(): void {
  sessionStorage.removeItem(KEY);
}
