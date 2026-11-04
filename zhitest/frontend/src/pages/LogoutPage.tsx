import { useQueryClient } from "@tanstack/react-query";
import { Spin } from "antd";
import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { logout } from "../api/resources";

export function LogoutPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    logout()
      .catch(() => undefined)
      .finally(() => {
        queryClient.clear();
        navigate("/login", { replace: true });
      });
  }, [navigate, queryClient]);

  return (
    <div className="center-screen">
      <Spin />
    </div>
  );
}
