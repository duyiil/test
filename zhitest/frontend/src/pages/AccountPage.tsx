import { useQuery } from "@tanstack/react-query";
import { Alert, Card, Descriptions, List, Typography } from "antd";
import { errorText } from "../api/client";
import { myAudit } from "../api/resources";
import { useCurrentUser } from "../layouts/current-user";
import { actionLabel, formatTime } from "../utils/format";

export function AccountPage() {
  const user = useCurrentUser();
  const audit = useQuery({
    queryKey: ["audit", "me"],
    queryFn: async () => (await myAudit()).data,
  });

  return (
    <div className="page-stack">
      <Typography.Title level={3} style={{ margin: 0 }}>
        个人设置
      </Typography.Title>
      <Card>
        <Descriptions column={1}>
          <Descriptions.Item label="用户名">{user?.username}</Descriptions.Item>
          <Descriptions.Item label="显示名">{user?.displayName}</Descriptions.Item>
          <Descriptions.Item label="角色">{user?.role === "admin" ? "管理员" : "成员"}</Descriptions.Item>
        </Descriptions>
      </Card>
      <Alert type="info" showIcon message="会话保存在 HttpOnly Cookie 中，前端不长期保存令牌或密码。空闲超过 2 小时需要重新登录。" />
      <Card title="我的最近操作">
        {audit.isError ? <Alert type="error" showIcon message={errorText(audit.error)} /> : null}
        <List
          loading={audit.isLoading}
          dataSource={audit.data?.items ?? []}
          locale={{ emptyText: "暂无操作记录" }}
          renderItem={(item) => (
            <List.Item>
              <List.Item.Meta
                title={actionLabel(item.action)}
                description={`${formatTime(item.createdAt)}${item.requestId ? ` · 请求 ${item.requestId}` : ""}`}
              />
            </List.Item>
          )}
        />
      </Card>
    </div>
  );
}
