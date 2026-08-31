import { useEffect, useRef, useState } from "react";
import { useChatAsk, useChatJob } from "../hooks/useXunji";
import { Icon } from "../components/Icon";
import type { ChatJob } from "../api/types";

interface AssistantMeta {
  traceId: string | null;
  spanCount: number | null;
  incidentId: string | null;
  durationMs: number | null;
}

interface ChatMessage {
  role: "user" | "assistant" | "error";
  text: string;
  meta?: AssistantMeta;
}

interface ChatMessageItemProps {
  message: ChatMessage;
}

function ChatMessageItem({ message }: ChatMessageItemProps) {
  const cls =
    message.role === "user" ? "chatmsg user" : message.role === "error" ? "chatmsg err" : "chatmsg";
  return (
    <div className={cls}>
      <div className="bubble">{message.text}</div>
      {message.meta && (
        <div className="chatmeta small">
          {message.meta.traceId && (
            <a href="#/runs" title="在运行记录页查看该 Trace">
              <span className="tag t-brand mono">{message.meta.traceId}</span>
            </a>
          )}
          {message.meta.spanCount != null && (
            <span className="tag t-gray">{message.meta.spanCount} 步骤</span>
          )}
          {message.meta.incidentId ? (
            <a href={`#/incidents/${message.meta.incidentId}`}>
              <span className="tag t-bad">事故 {message.meta.incidentId} → 诊断</span>
            </a>
          ) : (
            <span className="muted tiny">未触发事故</span>
          )}
          {message.meta.durationMs != null && (
            <span className="muted tiny mono">{(message.meta.durationMs / 1000).toFixed(1)}s</span>
          )}
        </div>
      )}
    </div>
  );
}

/** 对话演示：手动输入问题 → 后端 `xunji run` 包装 claude -p 真实执行并旁路采集 Trace。
 * 多轮：每轮回答带回 claude_session_id，下一问用 --resume 续接同一会话。 */
export function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const handledJobs = useRef(new Set<string>());
  const listRef = useRef<HTMLDivElement>(null);

  const ask = useChatAsk();
  const { data: job } = useChatJob(jobId);

  useEffect(() => {
    if (!job || job.status === "running" || handledJobs.current.has(job.job_id)) return;
    handledJobs.current.add(job.job_id);
    setJobId(null);
    if (job.status === "done" && job.claude_session_id) {
      setSessionId(job.claude_session_id); // --resume 会 fork 新 ID，永远用最新值
    }
    setMessages((prev) => [...prev, toMessage(job)]);
  }, [job]);

  useEffect(() => {
    listRef.current?.scrollTo?.({ top: listRef.current.scrollHeight });
  }, [messages, jobId]);

  const busy = !!jobId || ask.isPending;

  const send = async () => {
    const question = input.trim();
    if (!question || busy) return;
    setMessages((prev) => [...prev, { role: "user", text: question }]);
    setInput("");
    try {
      const { job_id } = await ask.mutateAsync({ question, sessionId });
      setJobId(job_id);
    } catch (e: unknown) {
      const text = e instanceof Error ? e.message : "请求失败";
      setMessages((prev) => [...prev, { role: "error", text: `提交失败：${text}` }]);
    }
  };

  const resetConversation = () => {
    if (busy) return;
    setMessages([]);
    setSessionId(null);
  };

  return (
    <div className="page-in">
      <div className="card">
        <div className="hd">
          <b>对话演示</b>
          <span className="tag t-brand">xunji run 包装</span>
          {sessionId ? (
            <span className="tag t-model mono" title={sessionId}>
              多轮会话 {sessionId.slice(0, 8)}…
            </span>
          ) : (
            <span className="tag t-gray">新会话</span>
          )}
          <span className="sp">
            <button
              type="button"
              className="btn sm"
              onClick={resetConversation}
              disabled={busy || (!messages.length && !sessionId)}
            >
              <Icon name="plus" />新对话
            </button>
          </span>
        </div>
        <div className="taxonomy-note">
          <b>接入即追踪：</b>每个问题真实执行一次 claude -p（多轮自动续接同一会话），
          执行链路旁路入库——回答与 Trace 同时产生，可跳转「运行记录」查看步骤明细。
        </div>
        <div className="bd">
          <div className="chatlist" ref={listRef} aria-label="对话消息">
            {!messages.length && !busy && (
              <div className="empty">
                <Icon name="chat" className="lg" />
                输入问题开始对话 — 回答与执行链路（Trace）同时产生。
                <span className="tiny">需本机已安装并登录 Claude Code CLI。</span>
              </div>
            )}
            {messages.map((m, i) => (
              <ChatMessageItem key={i} message={m} />
            ))}
            {busy && (
              <div className="chatmsg">
                <div className="bubble pending">真实执行中：claude -p（旁路采集 Trace）…</div>
              </div>
            )}
          </div>
          <form
            className="chatform"
            onSubmit={(e) => {
              e.preventDefault();
              void send();
            }}
          >
            <input
              aria-label="问题输入"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={busy ? "执行中，请稍候…" : "输入问题，如：读取 data/billing.json 汇总一下总金额"}
              disabled={busy}
            />
            <button type="submit" className="btn pri" disabled={busy || !input.trim()}>
              <Icon name="send" />发送
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

function toMessage(job: ChatJob): ChatMessage {
  if (job.status === "error") {
    return { role: "error", text: `执行失败：${job.error ?? "未知原因"}` };
  }
  return {
    role: "assistant",
    text: job.answer ?? "（无回答文本）",
    meta: {
      traceId: job.trace_id,
      spanCount: job.span_count,
      incidentId: job.incident_id,
      durationMs: job.duration_ms,
    },
  };
}
