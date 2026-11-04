import axios, { AxiosError } from "axios";

export interface Envelope<T> {
  code: string;
  message: string;
  details: unknown;
  requestId: string;
  data: T;
}

export class ApiClientError extends Error {
  status: number;
  code: string;
  details: unknown;
  requestId: string;

  constructor(status: number, code: string, message: string, details: unknown, requestId: string) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

export const http = axios.create({
  baseURL: "/api/v1",
  withCredentials: true,
  timeout: 20000,
});

http.interceptors.response.use(
  (response) => response,
  (error: AxiosError<Partial<Envelope<unknown>>>) => {
    const status = error.response?.status ?? 0;
    const body = error.response?.data;
    const url = error.config?.url ?? "";
    if (status === 401 && !url.includes("/auth/login") && !url.includes("/auth/me")) {
      window.dispatchEvent(new CustomEvent("zhitest:unauthorized"));
    }
    if (body && typeof body.message === "string") {
      throw new ApiClientError(status, body.code ?? "HTTP_ERROR", body.message, body.details ?? null, body.requestId ?? "");
    }
    throw new ApiClientError(status, "NETWORK_ERROR", "网络异常，请稍后重试", null, "");
  },
);

export async function unwrap<T>(promise: Promise<{ data: Envelope<T> }>): Promise<Envelope<T>> {
  const response = await promise;
  return response.data;
}

export function errorText(error: unknown): string {
  if (error instanceof ApiClientError) {
    if (Array.isArray(error.details)) {
      const first = error.details[0] as { msg?: string } | undefined;
      if (first?.msg) {
        return `${first.msg}${error.requestId ? `（请求 ${error.requestId}）` : ""}`;
      }
    }
    return `${error.message}${error.requestId ? `（请求 ${error.requestId}）` : ""}`;
  }
  return "请求失败";
}
