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
import { useQuery } from "@tanstack/react-query";
import { Avatar, Breadcrumb, Button, Dropdown, Layout, Menu, Select, Space, Switch, theme, Typography } from "antd";
import { useEffect, useMemo } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { listProjects } from "../api/resources";
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
  if (pathname.startsWith("/projects/")) return ["项目与资产", "项目详情"];
  if (pathname.startsWith("/projects")) return ["项目与资产"];
  if (pathname.startsWith("/reviews")) return ["测试用例审核"];
  if (pathname.startsWith("/suites")) return ["测试用例集"];
  if (pathname.startsWith("/runs")) return ["执行任务"];
  if (pathname.startsWith("/reports")) return ["测试报告"];
  if (pathname.startsWith("/settings")) return ["系统配置"];
  if (pathname.startsWith("/account")) return ["个人设置"];
  return ["智测"];
}

export function AdminLayout() {
  const navigate = useNavigate();
  const location = useLocation();
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
          <span>智</span>
          <Typography.Text style={{ color: "#fff" }}>智测 ZhiTest</Typography.Text>
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
              menu={{
                items: [
                  {
                    key: "empty",
                    disabled: true,
                    label: "通知中心尚未实现（Sprint5 / US-011）",
                  },
                ],
              }}
            >
              <Button aria-label="通知" icon={<BellOutlined />} />
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
