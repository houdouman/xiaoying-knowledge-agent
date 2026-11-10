# 评估

自动化测试及实际执行结果见 examples/test-results.txt。实际离线输入/输出位于 examples/，同名文件对应。

|验收点|输入/测试|预期|
|---|---|---|
|明确答案|normal|completed，引用D03|
|冲突|conflict|conflict，引用D01及D02，追问|
|资料不足|missing|补充搜索后insufficient_evidence|
|改写|paraphrase|费用问法仍发现冲突|
|历史追问|context|引用年假制度|
|工具失败|tool-failure|tool_error|
|预算耗尽|limit|incomplete|
|替换文档|test_replaced_documents|变为45天，只读取D01，completed|
|伪造引用|test_fabricated_quote|invalid_evidence|

Trace路径：normal为search→read→finish；missing为search→search→finish；tool-failure为search→finish。均为实际离线执行，不能证明真实模型的检索改进或冲突处理能力。

真实模型测试尚未运行：需要用户设置模型及密钥。应将上述输入使用--mode live运行并保存真实输出，人工逐项核对答案与原文，尤其是两条不同决策路径、文档替换、提示注入和冲突查证。当前不宣称真实模型验收达标。

## DeepSeek真实模型实测（2026-11-10）

已配置deepseek-chat并实际调用。examples/live/保存六类输出及summary.json：明确答案completed、冲突conflict、资料外insufficient_evidence、改写conflict、上下文completed、工具失败tool_error。首轮协议失败记录保留于examples/live-first-run/；后续增加JSON模式、动作示例及最多一次协议修复。修复调用不执行工具，每个决策最多两次生成。

已人工检查冲突答案引用D01的30天和D02的15天，明确请求确认适用制度。不同路径包括search→read→finish及工具失败后的search→search→finish。资料外问题补充检索后停止。以上为小规模单次样例，不代表稳定通过率；文档替换目前仅有离线测试证据。

## 本轮验收（覆盖以上历史状态）

新增可复现评估入口src/evaluate.py，九类真实运行详见examples/acceptance-live/summary.json及同目录每例JSON：六个题目验收场景，外加单一来源、45天替换文档、补充D04明确废止D02。每例保存实际使用的语料，支持核验替换引发的行为变化。

新增四项测试验证分片原文重建、正文检索、未读片段引用拦截、引用偏移。自动检查覆盖状态、来源ID、关键事实、冲突双方数值及追问、冲突后的查证动作、替换后无旧数值；不等同于完整语义蕴含评估。语义仍须人工审阅实际答案。

复测曾发现改写用例跳过read及多JSON动作导致失败，历史证据保留于examples/acceptance-live-before-repair/、examples/acceptance-live-protocol-failure/和examples/protocol-check.json。分别增加一次引用反馈修正和“只执行首个工具动作再观察”的协议解析，新增对应回归测试。最新结果以examples/acceptance-live/为准，禁止把多次调试运行合并视为一次稳定通过率。

最新完整运行：9/9项自动验收通过；15项基础/引用回归测试之后新增多动作解析测试，当前共16项全部通过。九例平均耗时4.02秒（单次样本，包含网络及服务延迟）。改写案例出现格式/引用修正时会增加模型调用，具体调用和Token见summary.json。人工复核了冲突、45天替换和明确废止说明的回答及引用，均与本次合成原文一致。
