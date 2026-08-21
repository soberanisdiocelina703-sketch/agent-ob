/** 统一 axios 实例（web/standards.md：集中 baseURL/超时/拦截器；组件禁止直连 API） */
import axios from "axios";

export const client = axios.create({ baseURL: "/", timeout: 15000 });

client.interceptors.response.use(
  (resp) => resp,
  (error) => {
    // 本期无鉴权（不做项）；409 冲突由调用方处理，其余统一透出 message
    const detail = error.response?.data?.detail;
    if (detail && error.response?.status !== 409) {
      error.message = String(detail);
    }
    return Promise.reject(error);
  },
);
