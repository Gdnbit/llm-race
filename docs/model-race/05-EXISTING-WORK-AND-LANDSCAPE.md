# 05 · 已有代码资产、相近项目与优先复用的能力

> 调研快照：2026-10-24。链接与功能均以原项目官方文档/仓库为线索；需要在实际接入前复查维护状态、许可证、数据条款、功能版本和适用范围。**以下是设计对标，不是声称已完成集成，也不声称 Model Race 独创此领域。**

## 1. 本仓库现状（从 main 源码/设计文档核对）

仓库：[Gdnbit/llm-race](https://github.com/Gdnbit/llm-race)；当前默认分支 `main`，设计文档 [DESIGN.md](../../DESIGN.md)。

| 实际路径 | 当前已有资产 | 对新方向的可能复用 |
| --- | --- | --- |
| `data-pipeline/src/build.py` | OpenRouter anchor / LMArena enrichment、合并、生成 JSON | 候选元信息导入逻辑、来源状态/缓存思路 |
| `data-pipeline/src/sources/` | OpenRouter、LMArena 接口 | 按许可复用为来源发现/对照适配器 |
| `data-pipeline/src/alignment/` | 别名、归一化与跨源匹配 | 模型身份与版本对齐的参考 |
| `data-pipeline/src/models.py` | 以 LLM token 价格为主的数据 schema | 仅历史 schema；跨模态必须重构任务/endpoint/计价单位 |
| `mcp-server/src/tools/` | `list_models`、`get_model`、`recommend_for_pipeline_step` | 可选 MCP 入口与启发式筛选，不能充当实测 Eval |
| `web/`、`dataset/` | 文档/本地构建产物空间 | 不代表已部署 Web、全量数据库或在线 API |
| `README.md`、`README_EN.md` | 如实描述当前实现 | 未来转型方向放在新文档，不改写事实 |

**当前明确不存在的能力**：通用 Model Race Skill、项目自动节点扫描、跨模态真实调用测评、Benchmark 自动匹配、跨节点组合搜索、生产长期成本预测、后台持久任务和自动部署。旧数据结构的 `Price` 以每百万输入/输出 token 计价，不能直接正确表示每张图片、每秒视频或语音的所有计价方式。

## 2. “元数据/模型目录”赛道已有成熟同类

| 对标/链接 | 核心参考点 | 与我们的边界 |
| --- | --- | --- |
| [Models.dev](https://github.com/anomalyco/models.dev) | 开放数据库、规格/价格/能力、模型身份与服务端点区分、API | **不重建一个小型 Models.dev**；按许可使用数据源 |
| [LiteLLM model cost map](https://models.litellm.ai/) | 机器可读多模型费用/能力数据与成本计算 | 可作价格发现入口，但最终价格核对 Provider 官方规则 |
| [Hugging Face Hub](https://huggingface.co/models) | 多任务分类、开放权重元信息、许可证和模型卡 | 不是全部商业 API 的独立质量验证平台 |
| [Artificial Analysis](https://artificialanalysis.ai/) | 语言、图像、视频、语音等评测与模型质量/价格/速度情报 | 第三方评测是线索；数据 API 再分发许可须确认 |
| [Replicate](https://replicate.com/explore) | 可实际调用的多模态模型和任务分类 | 与全部模型厂商不同；用于发现和测试候选 |
| [fal.ai](https://fal.ai/models) | 图像、视频、音频模型端点和非 Token 计价 | 需要核对模型具体版本/计量单位 |
| [openviglet/model-catalog](https://github.com/openviglet/model-catalog) | 公开维护多任务模型目录、结构化数据及更新 | 与“维护目录”相近，反证重复造库的必要性 |
| [LMArena](https://lmarena.ai/) | 人类偏好比赛/排行榜 | 主要是特定平台/评测方法，不能当用户业务准确率 |

**结论**：源数据资源可利用成熟生态；维护“数据源的数据源”作为 Skill 内置 reference / 搜索配方，而非商业壁垒。

## 3. “自动评测、现有项目理解与多节点优化”领域

| 项目 | 地址 | 可以借鉴/复用 | 需要警惕 |
| --- | --- | --- | --- |
| **AgentOpt** | https://github.com/AgentOptimizer/agentopt | 多步 LLM Agent 模型组合搜索、质量/成本/延迟、调用追踪、在线路由 | 与我们的多节点优化非常接近；异构 OCR/ASR 以及业务合同仍需验证 |
| **One-Eval** | https://github.com/OpenDCAI/One-Eval | 自然语言需求→Benchmark→数据→模型推理→评判→报告；可作为 Skill 调用 | 其主定位是 LLM 评测，不能直接宣称跨模态节点扫描已全部支持 |
| **AWS Agent-EvalKit** | https://github.com/awslabs/Agent-EvalKit | 分析现有 Agent 与需求、规划评测、生成测试、收集 Trace、报告 | 面向 Agent 质量评测，不天然是整个应用所有模型的部署/成本优化器 |
| **EvalScope** | https://github.com/modelscope/evalscope | 多模态与 Agent Benchmark、性能压测、报告、丰富指标目录 | 适配各任务需确认运行资源与数据集许可证 |
| **Inspect AI** | https://github.com/UKGovernmentBEIS/inspect_ai | 可编排的评测任务、模型适配、评分器和日志 | 不是自动理解陌生代码仓库的完整 Skill |
| **Promptfoo** | https://github.com/promptfoo/promptfoo | 模型/Prompt 对照测试、断言、测试集、CI、部分多模态与安全测试 | 测试设计与业务指标仍需 Agent/人工判断 |
| **Pydantic Evals** | https://ai.pydantic.dev/evals/ | Python 数据集、评分器、实验追踪、适合应用接入 | 用户案例准备/跨节点成本优化并非开箱即成 |
| **DeepEval** | https://github.com/confident-ai/deepeval | LLM/Agent 评测、丰富指标 | 自定义模态和业务真值的兼容性应实测 |
| **MLflow evaluation** | https://mlflow.org/docs/latest/genai/eval-monitor/ | 实验/评测记录、监测与生命周期 | 非项目级自动选型一站式工具 |
| **LangWatch** | https://github.com/langwatch/langwatch | 场景测试、监控、改进闭环，研究其 Coding Agent/Skill 工作流 | SaaS 与开源功能、数据治理、SDK 许可需区分 |
| **Langfuse** | https://github.com/langfuse/langfuse | Trace、数据集、离线实验、线上反馈回流 | 运行痕迹可能敏感，不能默认外传 |
| **LangSmith** | https://docs.smith.langchain.com/ | Agent/LLM 实验、追踪和对比 | 与具体平台和授权有关 |
| **Not Diamond** | https://www.notdiamond.ai/ | 动态模型选择/路由与目标优化 | 多模态支持和 API 能力随版本变化，不能假定覆盖全部 |
| **Model Selection Skill** | https://github.com/tkellogg/model-selection | Agent Skill 形态的模型比较与依据展示 | 更偏模型资料/选型，不等价于全项目端到端实测 |

**最贴近核心 idea 的重合点**：

- AgentOpt 已在多节点 LLM Agent 组合搜索方面提供实质能力，不能宣称“世界上第一次自动多节点选型”。
- One-Eval 已有 Skill 形态的自动评测规划/执行范式。
- Agent-EvalKit 已有阅读现有 Agent 项目并生成评测的工作流。
- EvalScope/Inspect AI/Promptfoo 等已是成熟执行底座。
- Langfuse/LangWatch 等已将开发实验与生产 Trace/监控联系起来。

**尚值得验证的整合假设**：对“任意已有多模态 AI 应用”，Coding Agent 在无需先手工搭建评测的前提下，自动发现异构节点、复用已授权的真实业务案例，动态建立节点专属指标，在开发/生产两个经济情境下完成跨节点组合实验，并形成多套实证支持的落地方案。**本次只是调研假设，不是确认市场空白或已有客户需求。**

## 4. 如何避免再次重复造轮子

外部项目采用四步判定：

1. **任务匹配**：对我们的两个真实项目的具体节点能否测，而不仅仅列一堆功能名。
2. **接口/运行条件**：是否支持本地/CI、不同 Provider、跨模态输入、结构化输出、任意评估器和可导出报告。
3. **许可与成本**：软件开源许可证、公开 Benchmark 使用条款、私有数据处理、计费与版本支持。
4. **工程边际收益**：用薄适配器连接比重新实现更便宜吗？能不能替代多个独立组件？

建议先从小组合起步：**Coding Agent + 项目检测脚本 + 一个评测框架 + 可复现报告**；仅在真实场景证明必要时引入 AgentOpt 的优化、Langfuse 的追踪或复杂调度。

## 5. 未来研究应维护的差异表

定期记录每个对标的：项目/功能版本、文档链接、评测日期、可运行的本地例子、是否支持 Python/TS、OCR/ASR/图像/音频/视频任务覆盖、是否能自动理解陌生 repo、能否使用私有测试集、有无实际节点级和整条工作流组合实验、是否能做 dev/prod 成本、是否有 Skill、License、API 价格/资源要求、限制、接入结论。

不要用 GitHub Star 当功能成熟度，更不要把对标项目宣称的节约倍数当 Model Race 的保证收益。

## 6. 研究引用与时间管理

上述外部链接是原始项目入口。第三方研究结果不断变化，特别是新模型基准、官方价格和发布功能；将**候选来源 → 官方资料 → 实测证据**分级写入报告，链接附采集时间，真实实现前复查最新资料。本文只记录与这次方案设计有关的对标，不代表在当前仓库安装、克隆或通过这些项目的测试。
