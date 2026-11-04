import { useQueryClient } from "@tanstack/react-query";
import { App as AntApp, ConfigProvider, theme as antdTheme } from "antd";
import { useEffect } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { AdminLayout } from "./layouts/AdminLayout";
import { AccountPage } from "./pages/AccountPage";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { LogoutPage } from "./pages/LogoutPage";
import { PlaceholderPage } from "./pages/PlaceholderPage";
import { ProjectCreatePage } from "./pages/ProjectCreatePage";
import { ProjectDetailPage } from "./pages/ProjectDetailPage";
import { ProjectListPage } from "./pages/ProjectListPage";
import { ReportPage } from "./pages/ReportPage";
import { ReviewPage } from "./pages/ReviewPage";
import { RunPage } from "./pages/RunPage";
import { RequireAuth } from "./router/RequireAuth";
import { useUiStore } from "./stores/ui";

function AuthEvents() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  useEffect(() => {
    const onUnauthorized = () => {
      queryClient.removeQueries({ queryKey: ["me"] });
      navigate("/login", { replace: true, state: { reason: "expired" } });
    };
    window.addEventListener("zhitest:unauthorized", onUnauthorized);
    return () => window.removeEventListener("zhitest:unauthorized", onUnauthorized);
  }, [navigate, queryClient]);
  return null;
}

export function App() {
  const mode = useUiStore((state) => state.theme);
  return (
    <ConfigProvider
      theme={{
        algorithm: mode === "dark" ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
        token: {
          colorPrimary: "#1d4e89",
          borderRadius: 8,
          fontFamily: '"Segoe UI", "PingFang SC", "Noto Sans SC", "Microsoft YaHei", sans-serif',
        },
      }}
    >
      <AntApp>
        <AuthEvents />
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<RequireAuth />}>
            <Route element={<AdminLayout />}>
              <Route index element={<DashboardPage />} />
              <Route path="projects" element={<ProjectListPage />} />
              <Route path="projects/new" element={<ProjectCreatePage />} />
              <Route path="projects/:projectId" element={<ProjectDetailPage />} />
              <Route path="reviews" element={<ReviewPage />} />
              <Route
                path="suites"
                element={<PlaceholderPage title="测试用例集" note="Phase 2 从执行任务页提交全部已确认用例。依赖编排、变量提取不在本阶段。" />}
              />
              <Route path="runs" element={<RunPage />} />
              <Route path="reports" element={<ReportPage />} />
              <Route
                path="settings"
                element={
                  <PlaceholderPage
                    title="系统配置"
                    note="模型配置、限额、白名单和系统级修改只应由管理员进行。这些页面尚未实现。管理员初始化已在服务端完成。"
                  />
                }
              />
              <Route path="account" element={<AccountPage />} />
              <Route path="logout" element={<LogoutPage />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AntApp>
    </ConfigProvider>
  );
}
