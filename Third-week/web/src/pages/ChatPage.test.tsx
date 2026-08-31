import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { ChatPage } from "./ChatPage";

let jobPolls = 0;
let failMode = false;

const server = setupServer(
  http.post("/v1/chat/messages", () => {
    jobPolls = 0;
    return HttpResponse.json({ job_id: "chat-job1" }, { status: 202 });
  }),
  http.get("/v1/chat/messages/:id", () => {
    jobPolls += 1;
    if (jobPolls === 1) {
      return HttpResponse.json({
        job_id: "chat-job1", status: "running", question: "对账平吗",
        answer: null, trace_id: null, span_count: null,
        incident_id: null, error: null, duration_ms: null, claude_session_id: null,
      });
    }
    if (failMode) {
      return HttpResponse.json({
        job_id: "chat-job1", status: "error", question: "对账平吗",
        answer: null, trace_id: null, span_count: null, incident_id: null,
        error: "claude 执行失败（exit 2）：找不到命令 claude", duration_ms: 120,
        claude_session_id: null,
      });
    }
    return HttpResponse.json({
      job_id: "chat-job1", status: "done", question: "对账平吗",
      answer: "两侧一致，差异 0 笔", trace_id: "chat-t1", span_count: 5,
      incident_id: null, error: null, duration_ms: 12345,
      claude_session_id: "aaaabbbb-cccc-dddd",
    });
  }),
);

beforeAll(() => server.listen());
afterEach(() => {
  failMode = false;
  server.resetHandlers();
});
afterAll(() => server.close());

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ChatPage />
    </QueryClientProvider>,
  );
}

async function sendQuestion() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("问题输入"), "对账平吗");
  await user.click(screen.getByRole("button", { name: "发送" }));
  return user;
}

describe("ChatPage", () => {
  it("发送问题_显示执行中随后收到回答与Trace链接", async () => {
    renderPage();
    await sendQuestion();

    expect(screen.getByText("对账平吗")).toBeInTheDocument(); // 用户气泡
    expect(await screen.findByText(/真实执行中/)).toBeInTheDocument(); // 加载态

    expect(await screen.findByText("两侧一致，差异 0 笔", undefined, { timeout: 4000 }))
      .toBeInTheDocument();
    expect(screen.getByText("chat-t1")).toBeInTheDocument(); // trace 链接
    expect(screen.getByText("5 步骤")).toBeInTheDocument();
    expect(screen.getByText("未触发事故")).toBeInTheDocument();
    expect(screen.getByLabelText("问题输入")).not.toBeDisabled(); // 结束后可继续提问
  });

  it("CLI缺失_显示错误气泡不阻塞后续输入", async () => {
    failMode = true;
    renderPage();
    await sendQuestion();

    expect(await screen.findByText(/找不到命令 claude/, undefined, { timeout: 4000 }))
      .toBeInTheDocument();
    expect(screen.getByLabelText("问题输入")).not.toBeDisabled();
  });

  it("多轮对话_第二问携带上一轮session_第一问不带_新对话后重置", async () => {
    const bodies: Array<{ question: string; session_id?: string }> = [];
    let jobs = 0;
    server.use(
      http.post("/v1/chat/messages", async ({ request }) => {
        bodies.push((await request.json()) as { question: string; session_id?: string });
        jobs += 1;
        return HttpResponse.json({ job_id: `chat-job${jobs}` }, { status: 202 });
      }),
      http.get("/v1/chat/messages/:id", ({ params }) =>
        HttpResponse.json({
          job_id: params.id as string, status: "done", question: "q",
          answer: `回答 ${params.id}`, trace_id: `t-${params.id}`, span_count: 2,
          incident_id: null, error: null, duration_ms: 100,
          claude_session_id: "aaaabbbb-cccc-dddd",
        })),
    );
    renderPage();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("问题输入"), "我叫小明");
    await user.click(screen.getByRole("button", { name: "发送" }));
    await screen.findByText("回答 chat-job1", undefined, { timeout: 4000 });
    expect(await screen.findByText(/多轮会话 aaaabbbb/)).toBeInTheDocument();

    await user.type(screen.getByLabelText("问题输入"), "我叫什么");
    await user.click(screen.getByRole("button", { name: "发送" }));
    await screen.findByText("回答 chat-job2", undefined, { timeout: 4000 });

    expect(bodies[0].session_id).toBeUndefined(); // 首问：新会话
    expect(bodies[1].session_id).toBe("aaaabbbb-cccc-dddd"); // 次问：续接

    await user.click(screen.getByRole("button", { name: "新对话" }));
    expect(screen.getByText("新会话")).toBeInTheDocument();
    await user.type(screen.getByLabelText("问题输入"), "重新开始");
    await user.click(screen.getByRole("button", { name: "发送" }));
    await screen.findByText("回答 chat-job3", undefined, { timeout: 4000 });
    expect(bodies[2].session_id).toBeUndefined(); // 重置后：不续接
  });
});
