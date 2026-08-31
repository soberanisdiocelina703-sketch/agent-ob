/** React Query hooks（组件通过 hooks 取数，不直连 API 层之下） */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { xunjiApi } from "../api/xunjiApi";

export function useTraces(filters?: Record<string, string>) {
  return useQuery({
    queryKey: ["traces", filters],
    queryFn: () => xunjiApi.listTraces(filters),
    refetchInterval: 5000,
  });
}

export function useTraceDetail(traceId: string | null) {
  return useQuery({
    queryKey: ["trace", traceId],
    queryFn: () => xunjiApi.traceDetail(traceId!),
    enabled: !!traceId,
  });
}

export function useIncidents() {
  return useQuery({
    queryKey: ["incidents"],
    queryFn: xunjiApi.listIncidents,
    refetchInterval: 5000,
  });
}

/** 诊断快照：规则结果先渲染，模型阶段未完时持续轮询（SSE 的降级路径，spec 决策） */
export function useDiagnosis(incidentId: string | null) {
  return useQuery({
    queryKey: ["diagnosis", incidentId],
    queryFn: () => xunjiApi.diagnosis(incidentId!),
    enabled: !!incidentId,
    refetchInterval: (query) =>
      query.state.data && ["complete", "failed"].includes(query.state.data.status)
        ? false
        : 1000,
  });
}

export function useDiff(incidentId: string | null) {
  return useQuery({
    queryKey: ["diff", incidentId],
    queryFn: () => xunjiApi.diff(incidentId!),
    enabled: !!incidentId,
  });
}

export function useReview(incidentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (p: { candidateId: string; version: number; result: string; reason?: string }) =>
      xunjiApi.review(p.candidateId, p.version, p.result, p.reason),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["diagnosis", incidentId] });
      qc.invalidateQueries({ queryKey: ["incidents"] });
    },
  });
}

export function useToRegression(incidentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (suiteName: string) => xunjiApi.toRegression(incidentId, suiteName),
    onSettled: () => qc.invalidateQueries({ queryKey: ["suites"] }),
  });
}

export function useSuites() {
  return useQuery({ queryKey: ["suites"], queryFn: xunjiApi.listSuites });
}

export function useGateRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (p: { suiteId: string; release: string; mode: string }) =>
      xunjiApi.gateRun(p.suiteId, p.release, p.mode),
    onSettled: () => qc.invalidateQueries({ queryKey: ["suites"] }),
  });
}

export function useChatAsk() {
  return useMutation({
    mutationFn: (p: { question: string; sessionId: string | null }) =>
      xunjiApi.chatAsk(p.question, p.sessionId),
  });
}

/** 对话任务：running 期间每秒轮询，终态（done/error）后停止并刷新运行列表 */
export function useChatJob(jobId: string | null) {
  const qc = useQueryClient();
  return useQuery({
    queryKey: ["chat-job", jobId],
    queryFn: async () => {
      const job = await xunjiApi.chatJob(jobId!);
      if (job.status !== "running") {
        qc.invalidateQueries({ queryKey: ["traces"] });
      }
      return job;
    },
    enabled: !!jobId,
    refetchInterval: (query) =>
      query.state.data && query.state.data.status !== "running" ? false : 1000,
  });
}
