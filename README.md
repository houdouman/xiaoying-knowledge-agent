# 企业知识问答 Agent（题目三）

基于 **Python + LangGraph + DeepSeek**，帮助员工查询企业制度。模型根据工具结果选择检索、读取原文、补充查证、追问或结束，最终输出答案、引用、资料缺口、任务状态和执行记录。

## 1. 环境与运行

要求Python 3.10+，实际验证环境为Windows、PowerShell、Python 3.12.10。所有命令在仓库根目录执行。

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
# 按已验证环境快照安装时，改用 requirements-lock.txt

# 离线运行：无需密钥
.venv\Scripts\python -m src.main --input examples/conflict.input.json
# 自动化测试：不调用真实模型
.venv\Scripts\python -m unittest discover -s tests -v
```

真实模型模式在根目录创建 `.env`：

```dotenv
LLM_PROVIDER=deepseek
OPENAI_API_KEY=填写自己的密钥
OPENAI_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
LLM_TIMEOUT_SECONDS=30
```

| 配置 | 实现行为 |
|---|---|
| OPENAI_API_KEY | 真实模式必需 |
| OPENAI_BASE_URL | OpenAI兼容地址，由ChatOpenAI读取 |
| LLM_MODEL | 优先模型名 |
| OPENAI_MODEL | LLM_MODEL未设置时使用 |
| LLM_TIMEOUT_SECONDS | SDK请求超时，默认30秒 |
| LLM_PROVIDER | 说明性配置，当前不据此切换适配器 |

只有真实模式自动加载 `.env`，已有环境变量优先。`.env` 已被Git忽略，禁止提交真实密钥。视觉、Embedding及数据库配置当前不参与执行。

```powershell
# 单例真实运行
.venv\Scripts\python -m src.main --mode live --input examples/conflict.input.json
# 九类真实验收：产生模型API费用，更新结果目录
.venv\Scripts\python -m src.evaluate --mode live
```

默认offline模式采用确定性测试替身，只验证流程与校验器；它包含固定场景逻辑，不代表真实模型决策能力，也不保证通过需要语义理解的全部验收。

## 2. 目录与模块职责

```text
.
├── README.md                         # 架构、实现、运行、评审入口
├── requirements.txt                  # 直接依赖范围
├── requirements-lock.txt             # 已验证环境依赖快照
├── .env.example                      # 无真实密钥的配置示例
├── .gitignore
├── data/documents.json               # 默认合成制度
├── src/
│   ├── __init__.py
│   ├── main.py                       # CLI、文件输入、JSON输出、退出码
│   ├── agent.py                      # 状态图、模型协议、工具、引用校验
│   ├── knowledge.py                  # 分块、词项提取、检索评分与排序
│   └── evaluate.py                   # 九类验收、对照语料、输出及指标
├── tests/
│   ├── test_agent.py                 # 基础流程、异常、预算、引用
│   └── test_knowledge.py             # 分片、来源定位、修正、协议
├── examples/
│   ├── *.input.json / *.output.json  # CLI样例及早期离线输出
│   ├── test-results.txt              # 最近一次自动化测试记录
│   ├── acceptance-live/              # 最新九类真实验收
│   │   ├── summary.json              # 通过情况及性能指标
│   │   └── <case>.json               # 输入、完整语料、结果、Trace、检查
│   ├── live/                         # 早期六类真实结果
│   └── 其他历史目录与协议诊断文件    # 包含失败，不作为最新结果
└── docs/
    ├── 01-requirements.md             # 用户、目标、范围、成功标准
    ├── 02-solution.md                 # 流程、动态决策、技术取舍
    ├── 03-evaluation.md               # 实测、失败与验证边界
    ├── 04-ai-usage.md                 # AI辅助及个人贡献待补充项
    └── 05-retrospective.md            # 复盘、限制、下一步
```

## 3. 总体架构与调用链

```mermaid
flowchart TD
    A[CLI读取JSON] --> B[输入校验与加载文档]
    B --> C[切片并保留原文位置]
    C --> D[START]
    D --> E[agent 模型选择动作]
    E -->|search| F[tools 词法检索]
    E -->|read| G[tools 读取片段]
    F --> H[保存观察与Trace]
    G --> H
    H --> E
    E -->|finish| I[结果及引用校验]
    I -->|通过| J[END 输出JSON]
    I -->|首次失败且live| K[反馈错误请求修正]
    K --> E
    I -->|再次失败或offline| L[END invalid_evidence]
    E -->|预算耗尽| M[END incomplete]
    E -->|调用或解析失败| N[END model_error]
```

调用从 `src/main.py:main` 进入 `src/agent.py:run`：校验请求、加载文档、生成片段、选择决策器、构建并编译StateGraph、执行图、返回结果和指标。评估入口直接调用同一run函数，通过documents参数注入对照语料。

图只有agent和tools两个节点。agent的条件边根据动作选择tools、END或反馈修正的agent自身；tools执行后总是返回agent。图提供执行骨架，真实模式中查询内容、读取对象、追问与终止由模型决定。

### 状态设计

| 字段 | 用途 |
|---|---|
| messages | 初始请求、工具动作和观察、可选校验反馈；每轮提供给决策器 |
| action | 当前动作及参数；内部repair仅用于反馈路由 |
| trace | 执行步骤、工具参数、简短依据、返回内容、可选校验错误 |
| steps | 已接收决策次数，用于预算 |
| reads | 以chunk_id索引的已读取原文，作为引用校验依据 |
| result | 最终业务结果或系统失败状态 |

节点返回部分状态；列表通过构造新列表显式追加。每次run创建独立图和状态，无跨请求持久化记忆。历史追问由调用方显式传入history。

## 4. 知识数据、分块与检索

### 4.1 数据格式

`data/documents.json` 为文档数组：

```json
{
  "id": "D01",
  "version_date": "2026-01-01",
  "title": "费用报销制度",
  "text": "员工应在费用发生后30天内提交报销申请。",
  "keywords": ["报销", "费用"]
}
```

默认D01规定30天，D02规定15天，二者故意不提供适用范围和优先级；D03为年假申请规则。D04废止说明仅在resolved验收案例注入，不属于默认资料。

新增资料可编辑JSON，或通过Python调用run时传documents。文档ID应唯一，更新正文应同步更新版本。当前只接收整理好的文本JSON，未实现PDF、Word或图片解析。

### 4.2 分块算法：split_documents

1. 默认按最多240字符切片，从原文位置0依次前进。
2. 原文超过当前块时，优先选择候选区间后半段的最后一个中文句号或换行作为终点。
3. 无适合边界时硬切至240字符；下一块从当前终点继续，无重叠。
4. 保留文档字段，添加doc_id、chunk_id、start、end；片段text严格等于原文[start:end]。

chunk_id形式为 `D01:0-20`。位置是Python Unicode字符索引，左闭右开，不是字节或UTF-16偏移。各块可按序拼接恢复原文。默认三份资料很短，各只有一块；长文切分由自动化测试专门验证。

### 4.3 词法检索：terms与search

去空白并转小写后提取英文数字词和连续中文双字词。每个片段评分为：

```text
theme   = keywords中作为子串出现在query中的关键词个数
lexical = query词项与“片段正文+标题”词项交集的大小
score   = 4 * theme + lexical
```

命中至少一个主题关键词，或lexical至少为2，才进入结果。按分数降序、chunk_id排序，返回文档ID、版本、片段ID、位置、评分、标题和最多80字符摘要。

小语料返回全部命中，避免Top-1隐藏冲突证据。这不是BM25或向量检索；改写理解主要依靠模型生成合适查询。没有Top-K、分页、持久索引或大规模上下文预算。

### 4.4 原文读取：read

ids为字符串数组，优先传搜索返回的chunk_id；也支持文档ID，一次读取其全部片段。输出documents及missing_ids，命中内容写入reads。搜索摘要即使恰好包含完整短文，也不能作为“已读取原文”的依据。

## 5. 模型决策协议与冲突处理

真实模式通过langchain_openai.ChatOpenAI访问兼容接口，temperature为0，启用JSON对象输出模式。每轮发送系统提示和序列化的请求、历史工具观察，没有使用服务商专属函数调用协议。

```json
{"action":"search","query":"报销制度 适用范围 优先级","reason":"查证效力关系"}
```

```json
{"action":"read","ids":["D01:0-20","D02:0-20"],"reason":"核实双方原文"}
```

```json
{
  "action": "finish",
  "reason": "资料不足，需要补充信息",
  "result": {
    "status": "needs_input",
    "answer": "请提供相关制度或适用条件。",
    "citations": [],
    "gaps": ["缺少适用条件"]
  }
}
```

reason仅记录简短、可核验的依据，不要求模型内部思维过程。模型按观察调整行为：

- 有相关资料：读取原文，再回答或继续查证。
- 无命中：改写或补充查询；仍无依据则明确资料缺口。
- 出现冲突：额外检索适用范围、优先级、替代关系；不能仅凭发布日期决定。
- 有明确废止说明：读取并引用说明，结合原制度消解冲突。
- 仍缺适用依据：保留双方冲突并请求用户确认。
- 工具持续失败：有限重试后报告工具错误，不编造答案。

追问通过finish结果返回，不在进程中阻塞等待用户。调用方将新信息放入下一次请求的history；历史只帮助理解语境，不是制度事实来源。

真实路径包括正常 `search→read→finish`、冲突 `search→read→search→finish`、失败 `search→search→finish`。最终以实际Trace为准，修正可能增加步骤。

### 协议容错

模型内容先剥离可选Markdown代码围栏，再由parse_action解析。多个连续合法工具JSON只执行第一个，其他提议丢弃，待工具返回后重新决策；多对象中含finish则拒绝，避免提前采纳没有实际执行工具的结论。

格式失败反馈给模型，最多一次额外生成，再失败返回model_error。原始异常响应记录于protocol_errors，仅供诊断，不代表已执行的动作。

### 执行限制

| 机制 | 实际控制 |
|---|---|
| 决策预算 | max_steps默认10，范围1至30；耗尽返回incomplete |
| 图递归保护 | recursion_limit = 2 * max_steps + 5 |
| 请求超时 | 默认30秒，可配置；不是整个任务的硬超时 |
| SDK重试 | max_retries=1，可能增加实际网络请求 |
| 格式修复 | 每次决策最多一次额外生成 |
| 引用反馈 | 每个真实任务最多一次，消耗决策预算 |
| 不重复调用、无命中最多两次改写、失败最多一次重试 | 提示词要求，非独立硬计数；由总步数兜底 |

steps包括被引用校验拒绝的结束动作；格式修复增加模型调用，不单独增加steps。模型调用异常时不新增成功决策Trace。

## 6. 引用校验

finish首先检查基本结果类型和允许状态，再对每条引用验证：

1. doc_id来自本次已读取片段；如果提供chunk_id，也必须一致。
2. version_date与来源匹配。
3. quote是非空字符串，且完整包含在同一个已读片段中。
4. completed和conflict至少有一条引用。

通过后程序补齐可信chunk_id及quote的start/end，覆盖模型自行填写的位置。同一片段重复出现相同引文时定位首个匹配。

真实模式首次校验失败会反馈“必须先read再引用”，允许模型修正一次，再次失败返回invalid_evidence；离线模式直接返回该状态。

该机制证明引用真实性及可定位性，不能证明答案全部事实在语义上被原文支持，也没有程序强制要求每个冲突答案同时引用双方；这些通过模型提示、验收检查和人工审阅共同评估。

## 7. 输入输出契约

输入示例：

```json
{
  "question": "需要提前多久？",
  "history": ["我想申请年假"],
  "max_steps": 10,
  "simulate_tool_failure": false
}
```

question必须是非空字符串；history可省略，提供时必须是数组；max_steps必须为1至30整数，布尔值不接受。simulate_tool_failure为验收开关，启用后本次所有检索、读取均模拟失败。

| 输出字段 | 含义 |
|---|---|
| status | 业务或系统状态 |
| answer | 答案、追问、冲突或失败说明 |
| citations | 每项含doc_id、version_date、quote、chunk_id、start、end |
| gaps | 缺少资料、待确认条件或错误摘要 |
| mode / verification | 区分live真实运行与offline替身 |
| trace | step、action、parameters、reason、observation及可选validation_error |
| protocol_errors | 异常模型原始响应 |
| metrics | 耗时、决策数、工具数、模型返回数、Token |

| status | 含义 |
|---|---|
| completed | 已给出有引用的答案 |
| conflict | 存在无法消解的资料冲突 |
| needs_input | 需要用户补充信息 |
| insufficient_evidence | 资料不足 |
| tool_error | 工具失败，无法核实 |
| incomplete | 执行预算耗尽 |
| model_error | 模型调用或解析失败 |
| invalid_evidence | 结果未通过格式或引用校验 |
| invalid_input | CLI输入读取、JSON或初始化配置校验失败 |

CLI输出业务JSON时返回退出码0，包括业务失败状态；捕获到ValueError或OSError时输出invalid_input并返回2。评估入口则全部检查通过返回0，否则返回1。

## 8. 性能指标和取舍

| 指标 | 统计口径 |
|---|---|
| elapsed_seconds | run总耗时，含工具、图执行及模型等待 |
| decision_steps | 成功接收的决策数，含引用拒绝后的修正步骤 |
| tool_calls | Trace中search/read次数，包括失败调用 |
| model_responses | SDK成功返回的响应数，含格式修复，不含内部传输重试 |
| total_tokens | usage_metadata.total_tokens累计值，未提供时按0计 |

正常问题读取后直接结束，冲突增加必要查证，引用失败有限修复。没有额外Embedding、重排序API或数据库部署成本。

每轮仍发送累积观察；检索扫描片段并重算词项，没有缓存、压缩和持久索引。当前优化针对题目可靠性与小语料调用效率，不代表大规模吞吐优化。

## 9. 测试与真实验收结果

### 自动化测试

最近16项测试全部通过，见 [test-results.txt](examples/test-results.txt)。覆盖正常/冲突/资料外/改写/历史/失败、预算、替换文档、伪造引用、分片重建、正文检索、未读片段拦截、引用位置、反馈修正和多动作解析。使用离线或注入策略，不发起真实模型请求；live反馈单测也使用注入策略。

### 真实模型验收

2026-11-10最新完整运行，DeepSeek deepseek-chat：9/9项自动检查通过，平均约4.02秒。

| 案例 | 状态 | 关键行为 | 耗时/秒 |
|---|---|---|---:|
| normal | completed | 引用D03，提前3个工作日 | 4.453 |
| conflict | conflict | 30天/15天双方引用，追加查证并追问 | 4.953 |
| missing | insufficient_evidence | 资料外问题补充检索后停止 | 3.235 |
| paraphrase | conflict | 理解“垫付的钱找公司结算” | 7.438 |
| context | completed | 根据历史理解年假追问 | 3.250 |
| tool-failure | tool_error | 工具失败后有限重试 | 2.969 |
| single-source | completed | 只有D01时回答30天 | 3.360 |
| replacement | completed | 原文改45天，答案随之改变 | 3.203 |
| resolved | completed | D04明确废止D02，引用依据适用30天 | 3.312 |

[最新汇总](examples/acceptance-live/summary.json)；同目录每例JSON保存请求、完整语料、实际输出、Trace和检查结果。重跑会覆盖对应文件，需要保留对照时先复制结果目录。

自动检查覆盖状态、来源ID、关键事实、冲突双方数值、追问、冲突后检索及替换后不出现旧期限。人工复核了冲突、替换及废止说明三类答案与引用。它不是完整语义蕴含评估，9/9不代表长期正确率或生产SLA。

### 失败与修复证据

历史失败见examples/live-first-run/、acceptance-live-before-repair/、acceptance-live-protocol-failure/及protocol-check.json，均在examples下。包括跳过read、返回多个动作等问题，后续分别增加引用反馈和只执行首个工具动作的解析机制。

最新改写案例仍触发协议/引用修正，共6个模型响应、6257 Token，因此耗时更高。历史调试结果保留，不把多次运行拼成一次稳定通过率。早期结果可能缺少后来新增字段。

## 10. 题目验收与提交导航

| 要求 | 入口 |
|---|---|
| 用户、目标、范围、成功标准 | [需求](docs/01-requirements.md) |
| 架构、调用流程、取舍 | 本README及[方案](docs/02-solution.md) |
| 六类必验场景与替换对照 | src/evaluate.py及examples/acceptance-live/ |
| 测试预期、实测、失败限制 | [评估](docs/03-evaluation.md) |
| AI使用和个人修改验证 | [AI记录](docs/04-ai-usage.md) |
| 学习、复盘、下一步 | [复盘](docs/05-retrospective.md) |

## 11. 个人贡献、方案特点与AI协作

本项目由本人主导技术选型、目标与范围把控、验证要求和交付推进，AI辅助完成代码实现和测试验证。以下分别介绍个人贡献、项目设计特点和协作分工。

### 12.1 本人的方案主导与技术取舍

- **确定技术路线**：我选择Python和LangGraph实现企业知识问答Agent，要求围绕题目完成可运行、可解释的模型决策闭环。
- **以验收要求约束方案**：我要求先理解考核规范和参考项目的交付结构，再进行实现；重点关注可靠答案、引用、冲突处理和可复现证据。
- **控制技术范围**：在讨论文档切割与Embedding后，我明确要求按题目完善效果，而不是盲目增加Embedding、向量库等组件。因此当前保留小语料词法检索，把改进重点放在片段读取、冲突查证、引用和测试上。
- **推动真实验证**：我提供模型接入配置，要求运行真实模型查看效果，推动项目从离线流程演示进入真实模型验收。
- **检查实现机制**：我进一步追问工具如何实现、Prompt如何描述工具和入参，关注Agent如何选择动作、执行工具和接收观察，而不只看最终输出。
- **组织交付**：我要求补齐README架构和实现说明、整理GitHub提交范围，并完成GitHub认证及代码推送。

在推进过程中，我把“能否用证据回答问题”作为方案取舍标准，要求先验证题目场景，再决定是否增加组件。具体设计在人机讨论中细化，AI辅助将这些要求落实为可运行代码和可复现测试。

### 12.2 项目设计思路与实现特点

以下是项目围绕本题形成的设计特点，不主张这些通用技术本身具有原创性。

| 设计目标 | 采用的方法 | 作用与取舍 |
|---|---|---|
| 让模型按实际证据调整行动 | LangGraph组织search、read、finish循环 | 让模型决定下一步，图负责执行、状态及预算 |
| 让答案可以定位到原文 | 片段携带文档ID、版本及字符位置，引用必须来自已读片段 | 区分检索摘要与已核实原文，便于评审追溯 |
| 避免制度冲突时擅自裁决 | 追加适用范围、优先级、替代关系检索 | 有明确依据才消解冲突，否则保留双方并追问 |
| 控制模型输出不稳定带来的影响 | 有限格式修复、引用反馈、首个工具动作执行后重新观察 | 容错有预算，不能无限重试或执行未经观察的整串计划 |
| 检查答案是否真正随证据变化 | 单一来源、45天替换、明确废止三类语料对照 | 同时检查答案、引用和动作，避免只看表面流畅度 |
| 让小规模实现易运行、易核验 | 本地词法检索及CLI交付 | 当前无需Embedding和数据库，后续按召回及性能数据调整 |

### 12.3 执行中的问题与解决

在真实运行中，项目通过“观察失败—分析原因—修复实现—回归验证”进行迭代。本人负责推动真实验证及题目效果优先的要求，AI辅助修复编码和测试执行。

主要问题、处理方法和证据如下：

| 问题与现象 | 解决思路及实现 | 验证方式 |
|---|---|---|
| 早期检索词过宽，“天”“多久”等让资料外问题误命中，干扰历史追问 | 收紧主题词，随后结合正文双字词匹配评分；让模型根据问题生成检索表述 | 资料外、历史追问及正文检索测试 |
| 模型发现30天和15天冲突后可能直接结束，查证过程不足 | 在决策提示中明确要求查找适用范围、优先级和替代关系；缺乏依据时保留双方并追问 | conflict检查读取后的追加检索；resolved加入废止说明验证答案变化 |
| 模型跳过read，直接引用搜索摘要 | 只接受本次已读片段中的引文，失败时反馈原因并允许一次有限修正 | 未读片段引用拦截及反馈修正回归测试 |
| 模型一次返回多个JSON动作，导致解析失败或可能提前执行后续计划 | 多个工具提议只执行第一个，获得实际观察后重新决策；混有最终答案的多对象输出拒绝并请求修正 | 多动作解析回归测试和真实改写用例 |
| 原文引用难以精确定位，且可能引用尚未读取的部分 | 分块保留文档ID、版本和字符偏移，读取按片段执行，校验后由程序计算引文位置 | 原文重建、偏移及跨未读片段引用测试 |
| 只看最终答案无法判断是否真正依赖资料 | 增加工具Trace、调用数和Token指标，并以单一来源、45天替换、明确废止三类语料对照 | 保存每例实际语料和结果，检查答案与动作随证据变化 |

### 12.4 AI辅助范围

| 工作 | AI参与内容 |
|---|---|
| 方案讨论 | 辅助拆分状态、工具、引用规则和验收案例，讨论具体实现及取舍 |
| 代码实现 | 编写LangGraph编排、模型接入、分块、检索、读取、校验及容错代码 |
| 测试验证 | 编写并执行回归测试及真实验收，保存输出、Trace、调用数和Token |
| 文档整理 | 辅助整理运行说明、架构、方案、评估和复盘 |

