import { Alert, Typography } from "antd";

export function PlaceholderPage({ title, note }: { title: string; note: string }) {
  return (
    <div className="page-stack">
      <Typography.Title level={3} style={{ margin: 0 }}>
        {title}
      </Typography.Title>
      <Alert type="warning" showIcon message="本阶段未实现" description={note} />
    </div>
  );
}
