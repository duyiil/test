import { useQuery } from "@tanstack/react-query";
import { Spin } from "antd";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { currentUser } from "../api/resources";

export function RequireAuth() {
  const location = useLocation();
  const me = useQuery({
    queryKey: ["me"],
    queryFn: async () => (await currentUser()).data,
    retry: false,
  });

  if (me.isLoading) {
    return (
      <div className="center-screen">
        <Spin size="large" />
      </div>
    );
  }
  if (me.isError || !me.data) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}
