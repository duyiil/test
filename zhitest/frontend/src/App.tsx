import { useQueryClient } from "@tanstack/react-query";
import { App as AntApp, ConfigProvider, theme as antdTheme } from "antd";
import { lazy, Suspense, useEffect } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { AdminLayout } from "./layouts/AdminLayout";
import { RequireAuth } from "./router/RequireAuth";
import { useUiStore } from "./stores/ui";

const LoginPage = lazy(() => import("./pages/LoginPage").then((module) => ({ default: module.LoginPage })));
const DashboardPage = lazy(() => import("./pages/DashboardPage").then((module) => ({ default: module.DashboardPage })));
const ProjectListPage = lazy(() => import("./pages/ProjectListPage").then((module) => ({ default: module.ProjectListPage })));
const ProjectCreatePage = lazy(() => import("./pages/ProjectCreatePage").then((module) => ({ default: module.ProjectCreatePage })));
const ProjectDetailPage = lazy(() => import("./pages/ProjectDetailPage").then((module) => ({ default: module.ProjectDetailPage })));
const ReviewPage = lazy(() => import("./pages/ReviewPage").then((module) => ({ default: module.ReviewPage })));
const ProjectManagePage = lazy(() => import("./pages/ProjectManagePage").then((module) => ({ default: module.ProjectManagePage })));
const SuitePage = lazy(() => import("./pages/SuitePage").then((module) => ({ default: module.SuitePage })));
const DefectPage = lazy(() => import("./pages/DefectPage").then((module) => ({ default: module.DefectPage })));
const SchedulePage = lazy(() => import("./pages/SchedulePage").then((module) => ({ default: module.SchedulePage })));
const NotificationPage = lazy(() => import("./pages/NotificationPage").then((module) => ({ default: module.NotificationPage })));
const RunPage = lazy(() => import("./pages/RunPage").then((module) => ({ default: module.RunPage })));
const ReportPage = lazy(() => import("./pages/ReportPage").then((module) => ({ default: module.ReportPage })));
const AccountPage = lazy(() => import("./pages/AccountPage").then((module) => ({ default: module.AccountPage })));
const LogoutPage = lazy(() => import("./pages/LogoutPage").then((module) => ({ default: module.LogoutPage })));
const PlaceholderPage = lazy(() => import("./pages/PlaceholderPage").then((module) => ({ default: module.PlaceholderPage })));

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
        <Suspense fallback={null}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<RequireAuth />}>
            <Route element={<AdminLayout />}>
              <Route index element={<DashboardPage />} />
              <Route path="projects" element={<ProjectListPage />} />
              <Route path="projects/new" element={<ProjectCreatePage />} />
              <Route path="projects/:projectId" element={<ProjectDetailPage />} />
              <Route path="projects/:projectId/manage" element={<ProjectManagePage />} />
              <Route path="defects" element={<DefectPage />} />
              <Route path="schedules" element={<SchedulePage />} />
              <Route path="notifications" element={<NotificationPage />} />
              <Route path="reviews" element={<ReviewPage />} />
              <Route path="suites" element={<SuitePage />} />
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
        </Suspense>
      </AntApp>
    </ConfigProvider>
  );
}
