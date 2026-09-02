"""proto 业务前端：data.js 生成器契约 + 静态托管。

原型（proto/prototype.html，逐字节复制自 midterm/）消费十个全局常量；
本测试用真实录制 fixtures 回放后生成 data.js，逐项校验原型渲染层
实际读取的字段都存在且类型正确——原型代码一处不改，契约由后端保证。
"""
import json
import subprocess
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from xunji import db as dbmod
from xunji.api import app
from xunji.protodata import render_data_js

FIXTURES = Path(__file__).parents[2] / "fixtures"


def load(mode: str) -> dict:
    return json.loads((FIXTURES / f"{mode}.contract.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    import os

    os.environ["XUNJI_DB"] = str(tmp_path_factory.mktemp("proto") / "proto.db")
    dbmod.reset_conn()
    with TestClient(app) as c:
        # 灌入真实录制数据并走完闭环（复核→转用例→门禁），让每个板块都有数据
        c.post("/v1/traces", json=load("normal"))
        c.post("/v1/traces", json=load("stale-source"))
        import time

        for _ in range(50):
            incs = c.get("/v1/projects/recon-demo/incidents").json()["incidents"]
            if incs:
                snap = c.get(f"/v1/incidents/{incs[0]['id']}/diagnosis").json()
                if snap["status"] in ("complete", "failed"):
                    break
            time.sleep(0.1)
        inc = c.get("/v1/projects/recon-demo/incidents").json()["incidents"][0]
        top = c.get(f"/v1/incidents/{inc['id']}/diagnosis").json()["candidates"][0]
        c.post(f"/v1/candidates/{top['id']}/review",
               json={"result": "confirmed", "reason_code": "test"},
               headers={"If-Match": str(top["version"])})
        c.post(f"/v1/incidents/{inc['id']}/regression-case", json={"suite_name": "对账回归集"})
        suite = c.get("/v1/suites").json()["suites"][0]
        c.post(f"/v1/suites/{suite['id']}/gate-run", json={"release": "1.0.0", "mode": "warn"})
        yield c
    dbmod.reset_conn()
    os.environ.pop("XUNJI_DB", None)


def parse_consts(js: str) -> dict:
    """把生成的 data.js 解析回 Python（每个 const 都是单行 JSON）。"""
    out = {}
    for line in js.splitlines():
        if line.startswith("const "):
            name, _, rest = line[6:].partition(" = ")
            out[name] = json.loads(rest.rstrip(";"))
    return out


class TestRenderDataJs:
    def test_十个常量齐全且非空(self, client):
        data = parse_consts(render_data_js(dbmod.get_conn()))
        for name in ("FAILURE_TYPES", "TRACES", "INCIDENTS", "SPANS", "DIAGNOSES",
                     "DIFFS", "SUITES", "GATE_RUNS", "CASE_PRESETS", "CHECKUP", "STATS"):
            assert name in data, f"缺少常量 {name}"
        assert data["TRACES"] and data["INCIDENTS"] and data["SUITES"]
        assert data["GATE_RUNS"], "renderGate 无条件读 GATE_RUNS[0]"

    def test_trace字段契约与原型渲染层一致(self, client):
        t = parse_consts(render_data_js(dbmod.get_conn()))["TRACES"][0]
        for k in ("id", "exec", "quality", "run", "ver", "at", "steps", "dur",
                  "incident", "judge"):
            assert k in t
        assert t["exec"] in ("success", "failed")
        assert t["quality"] in ("pass", "fail", "unknown")

    def test_事故与诊断字段契约(self, client):
        data = parse_consts(render_data_js(dbmod.get_conn()))
        i = data["INCIDENTS"][0]
        for k in ("id", "fm", "at", "run", "trace", "symptom", "symptomStep",
                  "faultStep", "faultType", "faultName", "evidence", "review",
                  "sessions", "age", "hero"):
            assert k in i
        assert i["evidence"] in ("sufficient", "partial", "insufficient")
        d = data["DIAGNOSES"][i["id"]]
        for k in ("rulePack", "model", "faultStep", "symptomStep", "gap",
                  "causal", "candidates", "gaps"):
            assert k in d
        c = d["candidates"][0]
        assert c["support"], "候选必须有支持证据（证据强制引用）"
        assert {"id", "kind", "from", "span", "text"} <= set(c["support"][0])

    def test_span编号S1起且标注首故障与症状(self, client):
        data = parse_consts(render_data_js(dbmod.get_conn()))
        inc = data["INCIDENTS"][0]
        spans = data["SPANS"][inc["trace"]]
        assert spans[0]["id"] == "S1"
        sts = {s["st"] for s in spans}
        assert "fault" in sts and "symptom" in sts
        # 诊断的 faultStep 必须指向实际存在的 span 编号
        assert data["DIAGNOSES"][inc["id"]]["faultStep"] in {s["id"] for s in spans}

    def test_diff维度与门禁明细(self, client):
        data = parse_consts(render_data_js(dbmod.get_conn()))
        diffs = data["DIFFS"]
        assert diffs, "有基线的事故必须产出 Diff"
        d = next(iter(diffs.values()))
        assert {"baseline", "failed", "firstDiv", "dims"} <= set(d)
        assert any(not dim["same"] for dim in d["dims"]), "stale-source 必有分歧维度"
        run = data["GATE_RUNS"][0]
        assert run["result"] in ("pass", "warn", "block")
        assert run["total"] == run["passed"] + run["failed"]

    def test_生成的JS通过node语法检查(self, client, tmp_path):
        node = shutil.which("node")
        if not node:
            pytest.skip("node 不可用")
        f = tmp_path / "data.js"
        f.write_text(render_data_js(dbmod.get_conn()), encoding="utf-8")
        proc = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr


class TestProtoStatic:
    def test_入口重定向与三件套可访问(self, client):
        r = client.get("/proto", follow_redirects=False)
        assert r.status_code == 307 and r.headers["location"] == "/proto/prototype.html"
        root = client.get("/", follow_redirects=False)
        assert root.status_code == 307 and root.headers["location"] == "/proto/prototype.html"
        assert client.get("/proto/prototype.html").status_code == 200
        assert client.get("/proto/css/prototype.css").status_code == 200
        assert client.get("/proto/js/prototype.js").status_code == 200

    def test_对话演示独立前端可访问(self, client):
        r = client.get("/chat")
        assert r.status_code == 200
        assert "对话演示" in r.text and "/v1/chat/messages" in r.text
        assert "/proto/css/prototype.css" in r.text  # 复用原型设计系统

    def test_data_js动态生成且禁用缓存(self, client):
        r = client.get("/proto/data.js")
        assert r.status_code == 200
        assert "no-store" in r.headers["cache-control"]
        assert "const TRACES" in r.text and "真实库" in r.text

    def test_路径穿越被拒(self, client):
        assert client.get("/proto/../server/xunji/api.py").status_code in (404, 403)

    def test_proto三件套与midterm逐字节一致(self, client):
        proto = Path(__file__).parents[2] / "proto"
        midterm = Path(__file__).parents[3] / "midterm"
        pairs = [("prototype.html", "prototype.html"),
                 ("css/prototype.css", "css/prototype.css"),
                 ("js/prototype.js", "js/prototype.js")]
        for a, b in pairs:
            assert (proto / a).read_bytes() == (midterm / b).read_bytes(), \
                f"proto/{a} 与 midterm/{b} 不一致——「不改原型」承诺被打破"
