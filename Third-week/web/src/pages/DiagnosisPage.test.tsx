import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { DiagnosisPage } from "./DiagnosisPage";

const diagnosis = {
  diagnosis_id: "diag-1", status: "complete", rule_pack_version: "v1",
  model_version: "mock", failure_reason: null,
  candidates: [{
    id: "cand-1", rank: 1, cause_type: "quality_check_failed",
    summary: "步骤 fetch_payments 输出与成功基线首次显著分歧",
    evidence_grade: "diff_based", source: "diff",
    first_fault_span_id: "t1-fetch_payments", version: 0, verdict: null,
    evidence: [{ id: "e1", side: "support", kind: "diff_divergence",
                 span_ref: "t1/t1-fetch_payments", event_ref: null,
                 excerpt: "rows: 152 → 147" }],
  }],
};

let reviewCalls = 0;
const server = setupServer(
  http.get("/v1/incidents/:id/diagnosis", () => HttpResponse.json(diagnosis)),
  http.get("/v1/incidents/:id/diff", () =>
    HttpResponse.json({ available: false, reason: "no_baseline", message: "暂无可比成功基线" })),
  http.post("/v1/candidates/:id/review", () => {
    reviewCalls += 1;
    if (reviewCalls > 1) {
      return HttpResponse.json({ detail: "并发冲突" }, { status: 409 });
    }
    return HttpResponse.json({ verdict_id: "v1", candidate_version: 1, result: "confirmed" });
  }),
);

beforeAll(() => server.listen());
afterAll(() => server.close());

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/incidents/inc-1"]}>
        <Routes>
          <Route path="/incidents/:incidentId" element={<DiagnosisPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("DiagnosisPage", () => {
  it("打开事故_三秒内看到首故障点候选与证据", async () => {
    renderPage();
    const hits = await screen.findAllByText(/t1-fetch_payments/);
    expect(hits.length).toBeGreaterThan(0);
    expect(screen.getByText(/基线对照/)).toBeInTheDocument();
    expect(screen.getByText(/rows: 152 → 147/)).toBeInTheDocument();
    expect(screen.getByText(/暂无可比成功基线/)).toBeInTheDocument(); // 冷启动降级文案
  });

  it("复核确认_成功后展示回执_再次提交遇409给出冲突提示", async () => {
    renderPage();
    const user = userEvent.setup();
    const confirmBtn = await screen.findByRole("button", { name: "确认是根因" });
    await user.click(confirmBtn);
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(/复核已记录/));
    await user.click(screen.getByRole("button", { name: "确认是根因" }));
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(/并发冲突/));
  });
});
