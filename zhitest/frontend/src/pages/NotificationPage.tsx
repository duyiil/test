import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Empty, List, Space, Typography } from "antd";
import { errorText } from "../api/client";
import { listNotifications, markAllNotificationsRead, markNotificationRead } from "../api/resources";
import { formatTime } from "../utils/format";

export function NotificationPage() {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["notifications"],
    queryFn: async () => (await listNotifications()).data,
  });
  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["notifications"] });
  };
  const readOne = useMutation({
    mutationFn: (id: string) => markNotificationRead(id),
    onSuccess: refresh,
  });
  const readAll = useMutation({
    mutationFn: () => markAllNotificationsRead(),
    onSuccess: refresh,
  });
  const items = query.data?.items ?? [];
  return (
    <div className="page-stack">
      <Space style={{ justifyContent: "space-between" }} wrap>
        <Typography.Title level={3} style={{ margin: 0 }}>
          通知
        </Typography.Title>
        <Button onClick={() => readAll.mutate()} disabled={!query.data?.unreadCount} loading={readAll.isPending}>
          全部标为已读
        </Button>
      </Space>
      {query.isError ? <Alert type="error" showIcon message={errorText(query.error)} /> : null}
      {!query.isLoading && items.length === 0 ? <Empty description="还没有通知。执行进入终态后会写一条。" /> : null}
      <List
        loading={query.isLoading}
        dataSource={items}
        renderItem={(item) => (
          <List.Item
            actions={[
              item.readAt ? (
                <Typography.Text key="read" type="secondary">
                  已读
                </Typography.Text>
              ) : (
                <Button key="mark" size="small" onClick={() => readOne.mutate(item.id)}>
                  标为已读
                </Button>
              ),
            ]}
          >
            <List.Item.Meta title={item.title} description={`${item.body} · ${formatTime(item.createdAt)}`} />
          </List.Item>
        )}
      />
    </div>
  );
}
