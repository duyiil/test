import {
  AuditOutlined,
  BellOutlined,
  DashboardOutlined,
  FileSearchOutlined,
  FolderOpenOutlined,
  LogoutOutlined,
  PlayCircleOutlined,
  ProjectOutlined,
  SettingOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Avatar, Badge, Breadcrumb, Button, Dropdown, Layout, List, Menu, Select, Space, Switch, theme } from "antd";
import { useEffect, useMemo } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { listNotifications, listProjects, markNotificationRead } from "../api/resources";
import { formatTime } from "../utils/format";
import { useUiStore } from "../stores/ui";
import { useCurrentUser } from "./current-user";

const { Header, Sider, Content } = Layout;

const MENU = [
  { key: "/", icon: <DashboardOutlined />, label: "工作台" },
  { key: "/projects", icon: <ProjectOutlined />, label: "项目与资产" },
  { key: "/reviews", icon: <AuditOutlined />, label: "测试用例审核" },
  { key: "/suites", icon: <FolderOpenOutlined />, label: "测试用例集" },
  { key: "/runs", icon: <PlayCircleOutlined />, label: "执行任务" },
  { key: "/reports", icon: <FileSearchOutlined />, label: "测试报告" },
  { key: "/defects", icon: <FileSearchOutlined />, label: "候选缺陷" },
  { key: "/schedules", icon: <PlayCircleOutlined />, label: "定时执行" },
  { key: "/settings", icon: <SettingOutlined />, label: "系统配置" },
];

function selectedKey(pathname: string): string {
  if (pathname === "/") return "/";
  const match = MENU.find((item) => item.key !== "/" && (pathname === item.key || pathname.startsWith(`${item.key}/`)));
  return match?.key ?? "/";
}

function crumb(pathname: string): string[] {
  if (pathname === "/") return ["工作台"];
  if (pathname.startsWith("/projects/new")) return ["项目与资产", "新建项目"];
  if (pathname.endsWith("/manage")) return ["项目与资产", "项目设置"];
  if (pathname.startsWith("/projects/")) return ["项目与资产", "项目详情"];
  if (pathname.startsWith("/projects")) return ["项目与资产"];
  if (pathname.startsWith("/reviews")) return ["测试用例审核"];
  if (pathname.startsWith("/suites")) return ["测试用例集"];
  if (pathname.startsWith("/runs")) return ["执行任务"];
  if (pathname.startsWith("/reports")) return ["测试报告"];
  if (pathname.startsWith("/defects")) return ["候选缺陷"];
  if (pathname.startsWith("/schedules")) return ["定时执行"];
  if (pathname.startsWith("/notifications")) return ["通知"];
  if (pathname.startsWith("/settings")) return ["系统配置"];
  if (pathname.startsWith("/account")) return ["个人设置"];
  return ["智测"];
}

export function AdminLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const { token } = theme.useToken();
  const user = useCurrentUser();
  const themeMode = useUiStore((state) => state.theme);
  const setTheme = useUiStore((state) => state.setTheme);
  const selectedProjectId = useUiStore((state) => state.selectedProjectId);
  const setSelectedProjectId = useUiStore((state) => state.setSelectedProjectId);
  const projects = useQuery({
    queryKey: ["projects", "switcher"],
    queryFn: async () => (await listProjects({ page: 1, pageSize: 100 })).data,
  });
  const notifications = useQuery({
    queryKey: ["notifications"],
    queryFn: async () => (await listNotifications()).data,
    refetchInterval: 20000,
  });

  useEffect(() => {
    document.title = `${crumb(location.pathname).slice(-1)[0]} · 智测 ZhiTest`;
  }, [location.pathname]);

  const items = useMemo(
    () =>
      (projects.data?.items ?? []).map((project) => ({
        value: project.id,
        label: project.name,
      })),
    [projects.data],
  );

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider breakpoint="lg" collapsedWidth={64} width={232} theme="dark">
        <div className="sider-logo">
          <span className="sider-mark">智</span>
          <span className="sider-title">智测 ZhiTest</span>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey(location.pathname)]}
          items={MENU}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: token.colorBgContainer,
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "0 20px",
            gap: 16,
          }}
        >
          <Breadcrumb items={crumb(location.pathname).map((title) => ({ title }))} />
          <Space wrap size="middle">
            <Select
              allowClear
              placeholder="当前项目"
              style={{ minWidth: 180 }}
              value={selectedProjectId ?? undefined}
              options={items}
              onChange={(value) => {
                setSelectedProjectId(value ?? null);
                if (value) navigate(`/projects/${value}`);
              }}
            />
            <Switch
              checked={themeMode === "dark"}
              checkedChildren="暗"
              unCheckedChildren="亮"
              onChange={(checked) => setTheme(checked ? "dark" : "light")}
            />
            <Dropdown
              dropdownRender={() => (
                <div style={{ width: 320, background: token.colorBgElevated, borderRadius: 8, boxShadow: token.boxShadowSecondary, padding: 8 }}>
                  {(notifications.data?.items ?? []).length === 0 ? (
                    <div style={{ padding: 12 }}>还没有通知</div>
                  ) : (
                    <List
                      size="small"
                      dataSource={(notifications.data?.items ?? []).slice(0, 5)}
                      renderItem={(item) => (
                        <List.Item
                          style={{ cursor: "pointer" }}
                          onClick={async () => {
                            if (!item.readAt) {
                              await markNotificationRead(item.id);
                              await queryClient.invalidateQueries({ queryKey: ["notifications"] });
                            }
                            navigate("/notifications");
                          }}
                        >
                          <List.Item.Meta title={item.readAt ? item.title : `未读 · ${item.title}`} description={`${item.body} · ${formatTime(item.createdAt)}`} />
                        </List.Item>
                      )}
                    />
                  )}
                  <Button type="link" onClick={() => navigate("/notifications")}>
                    查看全部
                  </Button>
                </div>
              )}
            >
              <Badge count={notifications.data?.unreadCount ?? 0} size="small">
                <Button aria-label="通知" icon={<BellOutlined />} />
              </Badge>
            </Dropdown>
            <Dropdown
              menu={{
                items: [
                  { key: "account", icon: <UserOutlined />, label: "个人设置" },
                  { key: "logout", icon: <LogoutOutlined />, label: "退出登录" },
                ],
                onClick: ({ key }) => {
                  if (key === "account") navigate("/account");
                  if (key === "logout") navigate("/logout");
                },
              }}
            >
              <Space style={{ cursor: "pointer" }}>
                <Avatar icon={<UserOutlined />} />
                <span>{user?.displayName ?? user?.username}</span>
              </Space>
            </Dropdown>
          </Space>
        </Header>
        <Content style={{ padding: 24, background: token.colorBgLayout }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
