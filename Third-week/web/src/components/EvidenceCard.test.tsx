import { render, screen } from "@testing-library/react";
import { EvidenceCard } from "./EvidenceCard";

const base = {
  id: "e1", kind: "diff_divergence", span_ref: "t1/s1", event_ref: null,
  excerpt: "generated_at: 2026-08-20 → 2026-08-19",
};

describe("EvidenceCard", () => {
  it("支持证据_显示引用与摘录", () => {
    render(<EvidenceCard evidence={{ ...base, side: "support" }} />);
    expect(screen.getByText(/支持证据/)).toBeInTheDocument();
    expect(screen.getByText(/t1\/s1/)).toBeInTheDocument();
    expect(screen.getByText(/2026-08-19/)).toBeInTheDocument();
  });

  it("反证_标注为反证并带反证样式", () => {
    const { container } = render(<EvidenceCard evidence={{ ...base, side: "refute" }} />);
    expect(screen.getByText(/反证/)).toBeInTheDocument();
    expect(container.querySelector(".evidence-card--refute")).not.toBeNull();
  });
});
