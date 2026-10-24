# 07 · 用户体验示例、数据契约与交付报告模板

> 本文全是**建议结构和合成示例**；项目尚无这些正式接口/命令，样例模型名、性能、费用均不构成实测或 API 可用性承诺。

## 1. 交互：不要求用户预先给每个节点选模型

**用户在 Coding Agent 中的自然语言请求：**

> 分析当前项目所有实际用到模型的节点。基于业务目标、已有案例、部署环境和成本预算，自动调研可能的 OCR/视觉/LLM/语音等方案。优先复用已有测试和成熟 Benchmark，在授权预算内小样本对照评测；分别考虑开发期和正式上线后的成本、质量、速度、稳定性、隐私和部署。生成至少几种有真实依据、取舍不同的系统方案，并说明各方案的适用范围、失败案例以及后续回归事项。不要直接替换生产模型。

Agent 的预期回应应先自动扫描，并在确需用户提供信息时**只问关键约束**：是否允许向外部 API 发送测试数据、最大真实评测预算、上线地域/自托管强制性、请求规模等。可自主从项目读出的信息不要重复问。

**示例场景**：合同处理应用 `PDF/image → 文本解析/OCR → 字段提取 → 规则判断 → 报告生成`；为了展示，不假定用户真的在仓库中拥有该应用。

## 2. Stage-aware 工作顺序

### 2.1 Research-only

Skill 报告项目扫描发现、缺失证据、目标与关键约束，查询可靠的候选模型/公开测试资源，给出待执行评测计划。**此阶段无真实 API 测试分数**，第三方基准需明确来源。

### 2.2 Budgeted real evaluation

预算/敏感数据许可通过后，Agent：

1. 对每个节点保留现状作为基线；
2. 选择多个**不同的实现路线**（如 PDF 文本层、传统 OCR、OCR+VLM 等）；
3. 在小规模、分层、可标注样本上执行；对表现合格的候选增加测试；
4. 严格区分节点级正确率与链路最终业务任务成功率；
5. 留下可复现调用/参数/版本、每步成本和失败案例；
6. 如果输入不代表真实生产场景，说明缺口并避免确定性结论。

### 2.3 Deployment decision

输出开发测试期最经济的可行方案、上线准备的性能/风险工作、生产低中高流量下的最优组合候选；区分静态配置和动态回退/路由。允许保留当前模型。

## 3. 建议机器可读契约（概念草案，不是代码已实现）

### 3.1 项目扫描 `project_profile.json`

```json
{
  "schema_version": "proposed-0.1",
  "project_id": "example-contract-workflow",
  "scan_status": "partial",
  "development_stage": "working_mvp",
  "runtime": ["python", "docker"],
  "deployment": {
    "region": "unspecified",
    "privacy_boundary": "must_confirm",
    "hardware": null
  },
  "workload": {
    "monthly_tasks": null,
    "peak_concurrency": null,
    "input_profile_status": "insufficient"
  },
  "discovered_nodes": ["document_parse", "field_extract", "report_draft"],
  "unknowns": [
    "No verified production traffic forecast",
    "External API data-transfer authorization not provided"
  ],
  "scan_evidence": [
    {"kind": "code", "path": "src/workflow.py", "line_hint": null}
  ]
}
```

`scan_status=partial` 表示**并不声称已经发现全部动态节点**；没有依据时 node 和 evidence 字段不能乱填。该 JSON 仅合成示例。

### 3.2 节点契约 `node_manifest.json`

```json
{
  "nodes": [
    {
      "node_id": "document_parse",
      "task": "document_text_and_layout",
      "status": "detected",
      "modalities_in": ["application/pdf", "image/png"],
      "modalities_out": ["structured_text"],
      "current_approach": "existing_parser",
      "required_quality": ["key_field_accuracy"],
      "hard_constraints": [
        "no_external_data_transfer_without_approval"
      ],
      "upstream": [],
      "downstream": ["field_extract"],
      "evidence": [{"path": "src/workflow.py", "kind": "code"}],
      "uncertainty": ["low-quality scanned samples underrepresented"]
    },
    {
      "node_id": "field_extract",
      "task": "structured_extraction",
      "status": "detected",
      "modalities_in": ["text"],
      "modalities_out": ["json"],
      "current_approach": "configured_llm",
      "required_quality": ["contract_schema_validity", "field_accuracy"],
      "hard_constraints": ["human_review_on_uncertain_results"],
      "upstream": ["document_parse"],
      "downstream": ["report_draft"],
      "evidence": [{"path": "src/workflow.py", "kind": "code"}],
      "uncertainty": []
    }
  ]
}
```

### 3.3 实验计划 `evaluation_plan.yaml`

```yaml
schema_version: proposed-0.1
run_id: example-run-001
mode: budgeted_eval
target_project: example-contract-workflow
approval:
  private_data_external_transfer: false
  paid_provider_calls: false       # 初始安全默认；需用户授权后才可改
  production_mutations: false
  max_estimated_spend_usd: 0
  max_calls: 0
baselines:
  document_parse: existing_parser
  field_extract: configured_llm
candidate_discovery:
  verify_official_prices: true
  check_model_and_dataset_licenses: true
  retain_original_sources: true
datasets:
  prefer_project_labeled_cases: true
  split_strategy: by_document_and_template
  exclude_sensitive_raw_samples_from_reports: true
evaluation:
  node_metrics:
    document_parse: [key_field_accuracy, p95_latency, total_cost]
    field_extract: [schema_validity, field_accuracy, serious_error_rate]
  workflow_metrics:
    - accepted_business_task_rate
    - p95_end_to_end_latency
    - cost_per_accepted_task
  require_baseline: true
  estimate_uncertainty: true
  stop_if_no_valid_ground_truth: true
execution:
  sandbox: true
  max_parallel_jobs: 1
  cache_scope: project_private
  dry_run: true
outputs:
  - report.md
  - result.json
  - proposed_changes.md
```

**上述计划故意默认零付费、零外传**。真正工作流应基于用户批准的项目、安全策略与环境生成具体预算/路由配置；仅把 YAML 示例放在公开仓库不代表存在相应 CLI。

### 3.4 实测结果 `experiment_result.json`

```json
{
  "run_id": "example-run-001",
  "status": "not_executed",
  "execution_timestamp": null,
  "node_id": "field_extract",
  "candidate_id": "unresolved-model-endpoint",
  "dataset": {
    "source": "user_project",
    "version": "unverified",
    "license_checked": false,
    "cases": 0,
    "ground_truth_status": "not_checked"
  },
  "metrics": [],
  "provider_cost": null,
  "latency_ms": null,
  "failed_cases": [],
  "evidence_level": "INFERRED",
  "limitations": ["Only a design proposal; no real model runs."]
}
```

**禁止**将 `not_executed` 结果写成模型质量分。真实 `completed` 结果至少提供样本数、单位、版本、协议、费用和来源。

## 4. 方案报告的标准内容

建议 `report.md` 包含以下固定章节：

1. **执行摘要**：项目、评测范围、未覆盖节点、是否实际调用、费用消耗、最终推荐的可信程度。
2. **项目背景**：业务目标、使用者、开发阶段、运行环境、输入质量分布、隐私和权限边界。
3. **节点地图**：每个节点的业务目标/输入/输出/调用证据/上下游/当前模型或方法。
4. **关键要求**：节点动态定制的硬约束/质量指标，量化理由和不确定事项。
5. **候选与数据来源**：模型身份、部署方式、服务商、价格单位、官方规格与公开 Benchmark 来源。
6. **实验设计**：业务/公开/合成数据比例、真值/标注方法、分层和 train/dev/test 隔离、评判器、样本量/置信度。
7. **节点级真实结果**：baseline、候选、质量、严重错误、P95、吞吐、费用/资源、失败样本；区分未测。
8. **工作流级真实结果**：多节点组合的业务任务成功率、错误传播、总体费用和回退情况。
9. **多方案矩阵**：质量优先 / 性价比优先 / 速度优先 / 私有部署或开放权重 / 混合方案，保证确实不同且有实测；说明 Pareto 关系。
10. **研发与生产成本**：研发评测总预算及已用费用；生产低/中/高流量场景、月度 TCO 区间、交叉点与敏感性。
11. **安全与部署审查**：外部数据传输许可、商业许可证、依赖、硬件、稳定性、回滚、生产上线未过门禁。
12. **决策、实施和再评测**：现状/首选/备选、差距、可审查配置变更、回归测试、下一次重评触发器。
13. **可复现附录**：时间、数据集/代码/Prompt/端点版本、命令、工具版本、日志/哈希与隐藏数据处理方式。

## 5. 示例方案矩阵（完全虚构，不能宣称真实测试）

下表仅示意格式、**没有任何真实质量/价格/延迟数字**：

| 方案 | 文档节点 | 字段提取 | 报告节点 | 开发期评价 | 生产期评价 |
| --- | --- | --- | --- | --- | --- |
| 保留现状 | 现有 Parser | 现有 LLM | 现有 LLM | 迁移最少、维持基线 | 需验证高流量与失败重试 |
| 低成本候选 | 原生 PDF 提取 + 本地 OCR 兜底 | 轻量模型 | 中小模型 | 评测成本低/结构化风险待验证 | API 成本低但需要监控人工修正 |
| 质量候选 | 文档专用模型 | 强推理模型 | 高质量模型 | 测试预算较高 | 复杂输入质量可能更高但需证明 |
| 私有部署候选 | 本地 OCR | 本地模型 | 本地模型 | 需要 GPU/资源管理 | 数据流可控但需测量总拥有成本 |
| 混合路由候选 | 按输入质量选解析/OCR/VLM | 按难度选模型 | 结构化复核 | 实验组合多、成本受限 | 应单独测试分类器错误与 fallback |

不得为这张示意表自行填入模型名、百分比、每次美元数并当作已经完成真实测试。

## 6. 正式开发期 vs 生产期：不以 API 单价代替总成本

建议报告给出的成本表：

| 成本构成 | 开发测试期 | 生产期 |
| --- | --- | --- |
| API/模型执行费 | 测试样本/模型对照/评审器，设预算上限 | 实际业务量 × 输入分布 × 单位费 |
| 本地/云算力 | 实验机器/一次性部署调试 | 稳定服务器折旧或租用、空闲与峰值 |
| 标注/复核 | 形成可信真值、失败案例审查 | 每次人工纠错/高风险复核 |
| 失败重试 | SDK 适配失败、错误样本重试 | 线上失败/降级/备用 API |
| 维护 | 实验脚本、依赖与接入工时 | 监控、价格变化、升级、日志、灾备 |
| 合规/迁移 | 测试数据授权、模拟环境 | 地域/数据/服务条款、线上切换与回滚 |

生产量未知时输出敏感性分析和假设；绝不把“便宜的测试 API”直接说成“最省钱的生产部署”。

## 7. 用户选择方案后的可操作交付

用户选择方案后，Agent 可以生成：

- `config.patch` 或配置文件差异（仅开发分支）；
- Provider 凭据名称清单，但**不能在报告中写真实密钥**；
- 模型/接口/Prompt 变化对下游契约的影响与迁移步骤；
- 最低限度回归测试和回滚检查清单；
- 生产上线前需用户签字/批准的剩余门禁。

未经授权不能执行更改；对不存在或不支持的 SDK/CLI 不应凭空提供“已成功修改”。

## 8. 边界情况下正确的报告内容

- **没有模型节点**：报告为“未发现有证据的模型节点”，给出扫描范围，不制造建议。
- **只有计划节点**：输出候选与评测需求清单，不说完成实测。
- **没有可靠测试真值**：输出收集/标注策略与不确定排序，不能给确定成功率。
- **全部候选不满足硬约束**：输出无可行方案、约束冲突及可能需要用户调整的条件。
- **费用或授权不足**：终止付费评测，只做 research-only 报告。
- **评测方案没有显著收益**：建议保留现状，说明成本、样本与不确定性。
- **评测运行被中断**：输出 partial、已完成实验与恢复点，不伪造全量结果。
- **测试数据隐私敏感**：只报告合规的数据摘要/指标，不暴露原始记录与用户身份。
