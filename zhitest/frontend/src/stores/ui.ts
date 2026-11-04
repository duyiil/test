import { create } from "zustand";
import { persist } from "zustand/middleware";

interface UiState {
  theme: "light" | "dark";
  selectedProjectId: string | null;
  setTheme: (theme: "light" | "dark") => void;
  setSelectedProjectId: (id: string | null) => void;
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      theme: "light",
      selectedProjectId: null,
      setTheme: (theme) => set({ theme }),
      setSelectedProjectId: (selectedProjectId) => set({ selectedProjectId }),
    }),
    { name: "zhitest-ui" },
  ),
);
