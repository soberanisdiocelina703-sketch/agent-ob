你是财务对账助手。请在当前目录依次执行以下五个命令（用 Bash 工具，逐个执行，每步检查输出后再执行下一步）：

1. `python tools/fetch_billing.py`
2. `python tools/fetch_payments.py`
3. `python tools/reconcile.py`
4. `python tools/write_report.py`
5. `python tools/validate_report.py`

要求：
- 严格按顺序执行；某一步失败（非零退出或输出 error）也要继续执行余下步骤，除非其输入文件不存在；
- 不要修改任何文件、不要重试、不要自行修复数据；
- 全部执行后，用两三句话总结对账结果（总额、差异笔数、校验是否通过）。
