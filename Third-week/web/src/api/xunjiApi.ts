/** API 层：路径与 docs/08 §8.2 逐字一致 */
import { client } from "./client";
import type {
  ChatJob, Diagnosis, DiffView, Incident, Suite, TraceDetail, TraceSummary,
} from "./types";

export const PROJECT = "recon-demo";

export const xunjiApi = {
  listTraces: async (params?: Record<string, string>) =>
    (await client.get<{ traces: TraceSummary[] }>(
      `/v1/projects/${PROJECT}/traces`, { params })).data.traces,

  traceDetail: async (traceId: string) =>
    (await client.get<TraceDetail>(`/v1/traces/${traceId}`)).data,

  listIncidents: async () =>
    (await client.get<{ incidents: Incident[] }>(
      `/v1/projects/${PROJECT}/incidents`)).data.incidents,

  diagnosis: async (incidentId: string) =>
    (await client.get<Diagnosis>(`/v1/incidents/${incidentId}/diagnosis`)).data,

  diff: async (incidentId: string, baseline?: string) =>
    (await client.get<DiffView>(`/v1/incidents/${incidentId}/diff`,
      { params: baseline ? { baseline } : {} })).data,

  review: async (candidateId: string, version: number, result: string, reason?: string) =>
    (await client.post(`/v1/candidates/${candidateId}/review`,
      { result, reason_code: reason ?? null },
      { headers: { "If-Match": String(version) } })).data,

  toRegression: async (incidentId: string, suiteName: string) =>
    (await client.post(`/v1/incidents/${incidentId}/regression-case`,
      { suite_name: suiteName })).data,

  listSuites: async () =>
    (await client.get<{ suites: Suite[] }>("/v1/suites")).data.suites,

  gateRun: async (suiteId: string, release: string, mode: string) =>
    (await client.post(`/v1/suites/${suiteId}/gate-run`, { release, mode })).data,

  chatAsk: async (question: string, sessionId: string | null) =>
    (await client.post<{ job_id: string }>("/v1/chat/messages",
      { question, session_id: sessionId ?? undefined })).data,

  chatJob: async (jobId: string) =>
    (await client.get<ChatJob>(`/v1/chat/messages/${jobId}`)).data,
};
