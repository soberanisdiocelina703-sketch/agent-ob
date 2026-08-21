"""HTTP reporter + T2 annotation API stubs."""
import httpx

DEFAULT_SERVER = "http://127.0.0.1:8756"


def report(contract: dict, server: str = DEFAULT_SERVER,
           client: httpx.Client | None = None) -> dict:
    c = client or httpx.Client(timeout=10)
    try:
        resp = c.post(f"{server}/v1/traces", json=contract)
        resp.raise_for_status()
        return resp.json()
    finally:
        if client is None:
            c.close()


# ---- T2 注解 API：仅签名定义，本周无上报链路（范围裁定，不在演示中使用） ----

def log_state_write(state_key: str, value_hash: str, snapshot_version: str) -> None:
    raise NotImplementedError("T2 深接入增强：本期未实现（见提示词范围裁定）")


def log_handoff(source_step: str, target_step: str, payload: dict,
                contract_version: str) -> None:
    raise NotImplementedError("T2 深接入增强：本期未实现（见提示词范围裁定）")
