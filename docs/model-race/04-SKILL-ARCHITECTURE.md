# 04 · Skill-first 技术架构、自动执行与治理

> **架构提案：现有仓库尚未创建下述通用 Skill、Eval Harness 或作业引擎。**

## 1. 为什么是 Skill，而非另一个平台

用户使用 Codex、Claude Code 等 Coding Agent 开发项目，Agent 已具备读仓库、写适配代码、查阅在线文档和调用命令的能力。Model Race 的独特贡献是**让 Agent 知道该如何系统、可信地做项目级评测与技术选型**。因此：

- **SKILL.md**：引导用户意图识别、任务规划、证据核查、策略决策、审批门禁和报告；
- **references/（资源）**：数据源的源、任务分类、指标规则、评测框架适配、质量/预算/隐私政策；
- **scripts/ + 第三方框架**：把评测真正执行、记录、重试和对比；不是仅一段提示词；
- **artifacts/（运行产物）**：一次任务的项目节点图、方案、测试数据引用、实验日志、可复现决策，不作为公开代码自动提交。

必须注意：**不是每个 Coding Agent 都能在用户关闭会话后继续运行。** 后台执行需要宿主提供持久终端/任务管理、CI runner、队列或者独立执行环境；Skill 自身不能无条件承诺后台自动运行。

## 2. 推荐总体架构

```text
User request in existing project
           |
  Coding Agent + Model Race SKILL.md
           |
 [Read-only project discovery]
           |-- code/config/API/prompts/workflow DAG
           |-- requirements/tests/fixtures/trace/real cases
           |-- current deployment/volume/budget/policies
           v
 [Node & dependency manifest] + unknowns
           v
 [Per-node requirements / failure-cost model]
           v
 [Dynamic source/benchmark/implementation discovery]
           |-- small verified source registry (sources of sources)
           |-- original provider specs & license validation
           |-- available eval engines and user datasets
           v
 [Candidate plans & approval boundary]
           v
 [Eval Harness: budgeted, sandboxed and resumable]
           |-- node-level runs
           |-- workflow-level runs
           |-- dev, pre-prod and production scenarios
           |-- provenance/telemetry/result cache
           v
 [Portfolio selector / Pareto & sensitivity analysis]
           v
 [Reproducible report + opt-in config patches]
```

## 3. Skill 层职责（不把确定性工作都交给语言模型）

Agent 适合：从陌生代码解释业务、提出候选、选择评价维度、生成实验配方和解读失败案例。

确定性程序适合：输入验证、费用计数、样本哈希、任务隔离、跑分、结构化指标统计、条件硬筛选、Pareto 关系计算、配置差异、实验复现。**报告不得由语言模型自由生成虚构分数；所有展示的数字应读取执行产物或有标识的第三方数据。**

### 3.1 设计中的模块

| 模块 | 输入 → 输出 | 失效时的正确行为 |
| --- | --- | --- |
| ProjectScanner | repo/document/trace → `project_profile.json` | 标记未发现的节点与权限缺口 |
| NodeMapper | code evidence → `node_manifest.json` / DAG | 不凭空猜测动态调用 |
| RequirementProfiler | node + business contract → requirements | 未知硬约束待确认；不可隐式放宽 |
| SourceDiscoverer | task + freshness → provenance-rich candidates | 无可靠来源则给发现失败和下一步 |
| DatasetCurator | licensed samples → dataset manifest/splits | 无可靠真值不给伪准确率 |
| EvalPlanner | candidates + budget → eval plan | 成本、权限不足只输出计划 |
| HarnessAdapter | plan → framework-specific jobs | 明确 unsupported / dependency missing |
| MetricsAggregator | immutable run records → structured metrics | 不兼容指标不可统一排序 |
| PortfolioOptimizer | node/run metrics + workflow results → Pareto sets | 数据不足输出 provisional |
| ReportBuilder | validated facts → human/Machine report | 缺证据明确标缺失 |
| PatchPlanner | approved portfolio → dev-branch config patch | 不碰生产环境，无授权不执行 |

## 4. 最小目录（未来建议，不是已建目录）

```text
model-race/
  SKILL.md
  agents/                          # 可选的分工模板
    project-inspector.md
    benchmark-researcher.md
    eval-planner.md
  references/
    source-discovery.md
    task-taxonomy.md
    evaluation-recipes.md
    evidence-policy.md
    deployment-cost-model.md
    safety-and-permissions.md
  scripts/
    discover_nodes.py
    discover_sources.py
    build_eval_plan.py
    run_experiments.py
    compare_portfolios.py
    validate_report.py
  schemas/
    project-profile.schema.json
    node-manifest.schema.json
    evaluation-plan.schema.json
    experiment-result.schema.json
    portfolio-report.schema.json
  templates/
    evaluation-plan.yaml
    report.md
  tests/
    fixtures/                       # 仅公开、安全的合成项目
```

仓库原来的 `data-pipeline/`、`mcp-server/` 不必立刻移动/重命名；如复用，只保留必要的元数据发现或 MCP 包装功能，避免与新 Skill 入口产生双份独立权威数据。

## 5. Harness 应提供的执行原语

- **可复现**：评测 case ID、输入或合法哈希、版本、配置、Prompt/上下文、解析器、数据集和 Judge 版本，保存机器可读结果。
- **执行环境**：安全的 sandbox / mock / 无副作用模式，防止评测时发真实消息、改变生产数据和外部写操作。
- **任务调度**：不同模型并行但受 rate-limit/concurrency/budget 约束；对昂贵模型分层采样；可暂停/恢复和终止。
- **成本防线**：开始前估计上界，授权总预算、单节点预算、样本上限、失败次数阈值；真实请求量与费用 ledger 对账；无法可靠计价时保守停机。
- **缓存**：对完全一致的请求/模型版本/参数/测试版本缓存；避免误把变化后结果当最新实测；缓存可能包含敏感数据，默认本地权限隔离。
- **容错**：网络超时、供应商 429/5xx、降级、请求失败、重复计费；区分“模型答错”和“基础设施失败”，并在报告中给出率。
- **可观测性**：作业状态、进度、当前消耗、已完成/跳过、失败原因、产物位置；不要要求用户一直盯着对话。
- **验收 gate**：以统计与事实规则验证产物完整，避免 Agent 直接以自我描述宣布实验成功。

## 6. 多 Agent 并行应适度

可能分工：项目扫描、候选研究、数据集质量检查、各模态评测执行、成本计算、结果审计。但是**单一工件契约**必须保证不同 Agent 对同一节点、数据集版本和单位计价的理解一致。

并行不是免费：可能产生重复研究、相同 API 调用、输出互相覆盖、错误传播。先采用能复现的顺序主工作流，确认瓶颈后再引入并行任务和去重锁。

## 7. 支持多种运行模式

| 模式 | 行为 | 最低安全要求 |
| --- | --- | --- |
| Research-only | 仅读项目、找候选/Benchmark、算理论成本 | 不调用付费推理；区分未实测 |
| Budgeted Eval | 候选小样本 → 强候选放大 → 结果对比 | 已批准预算、数据合法、隔离与日志 |
| Deep Portfolio | 搜索有限的节点组合、做端到端验证与 TCO 估计 | 明确资源/时间预算，支持中止和恢复 |
| Incremental Regression | 仅重评模型/Prompt/SDK/数据/部署有变化的节点及相关下游 | 版本差异记录、回归基线与兼容检查 |

第一次使用全项目发现；第二次只测新 OCR 节点；Prompt 更改就测受影响环节；成本目标改变则复用合法且兼容的历史结果筛选新方案。**没有可证明相容的缓存，必须重新实测。**

## 8. 自动发现差异、重测触发器

监听或比对：模型 ID/版本与 Provider、Prompt 和结构化输出 schema、工作流 DAG、输入数据分布、定价/限额、硬件/区域、服务条款、质量回归和生产反馈。任何一项变化可能使已有选型建议失效。

静态检测只是线索；运行时动态 Provider、远程 LangGraph/低代码流程、工作区外脚本、闭源服务无法完全自动发现，须报告 `not_observed` 或 `requires_confirmation`，而非“已扫描全部”。

## 9. 成熟工具的可复用位置

- **模型/价格发现**：Models.dev、LiteLLM cost data、提供商官方 API、Hugging Face、OpenRouter 等。
- **自然语言驱动的评测自动化参考**：One-Eval Skill、AWS Agent-EvalKit。
- **通用测试执行**：Promptfoo、Pydantic Evals、Inspect AI、EvalScope、DeepEval、MLflow 相关框架（需要逐个验证适配和许可证）。
- **多节点组合优化**：AgentOpt（尤其 LLM Agent 工作流）。
- **案例与在线 Trace**：Langfuse、LangWatch、LangSmith 等（可选；须有授权和隐私审查）。
- **生产路由方向**：Not Diamond 和类似路由器（只作为可能的后续能力，并非 MVP）。

架构原则：**以能力适配为界面，而不是将所有工具硬依赖装入一个 Skill**。设计统一 adapter 契约，少量工作流优先跑通。

## 10. 权限策略与外部副作用

最小权限：代码只读 -> 查看项目已有测试数据 -> 下载许可公开数据 -> 本地/沙盒运行 -> 发送非敏感数据到付费外部 API -> 提交开发分支修改 -> 生产发布。每一层分别授权；后一层不自动继承前一层。

- 评测 Agent 可能接触系统 Prompt、内部域名、API Key、用户业务数据：日志、报告、PR 和公共工件都应去敏。
- 测试不得依赖真实生产写操作（邮件/转账/审批/学生记录更新）；使用 mock 和显式测试账户。
- 改动采用 dry-run / 可审查 patch，执行前确认回滚方案。线上路由自动更改是独立的高风险产品，不包含在 MVP。
- 生产效果与隐私许可是场景要求，不以通用 Skill 自动给合规结论。

## 11. 机器可读中间产物与可恢复性

每个运行生成独立 `run_id`，将项目扫描、输入授权、数据集描述、候选与筛选原因、费用预算、逐节点实测、工作流实测、错误、选型报告写入非仓库默认忽略的私有工作目录（如 `.model-race/runs/<run_id>/`）。

原始敏感样本是否留存由用户选择；即便不持久化原文，也应保留可安全记录的标识和版本哈希。结果缓存应按测试套件/模型/endpoint/参数/隐私边界隔离，支持到期和删除。记录`job_state`（planned/running/paused/failed/completed/cancelled）使宿主可提供恢复。

## 12. 质量门禁

实现阶段至少验证：任务识别准确性、结论引用完整性、跨单位计费准确性、总预算不超出授权、敏感数据不会无意外传、危险生产工具被 mock、相同种子条件下结果稳定、失败可恢复、公开示例不含秘密；以及不支持某模态/无现成 Benchmark/无可信真值时**能合理拒绝给确定排名**。
