# Contributing to LLM_Race

感谢你参与 LLM_Race。

## 推荐协作方式

协作流向：`main ← PR ← feature/<name>`。
一个功能一个 branch，一个功能一个 PR；不要直接 push main。
维护者审核通过后优先使用 squash merge。

1. 从最新 `main` 创建 feature branch。
2. 一个 PR 尽量只解决一个明确问题。
3. 在 PR 中写清：问题、方案、验证方式、已知限制。
4. 不提交真实 API key、token、`.env`、私钥、本机 secret-store 文件或私人数据。
5. 修改模型评分、数据归一化或 ID 对齐逻辑时，尽量附上可重复的输入/输出样例或测试。

## 开发入口

### Data pipeline

```bash
cd data-pipeline
uv sync
uv run python -m unittest discover -s tests -v
```

### MCP Server

```bash
cd mcp-server
npm ci
npm run typecheck
npm run build
npm test
```

## Pull Request 建议

PR 描述至少回答：

- 为什么要改？
- 改了什么？
- 如何验证？
- 是否影响数据 schema、评分、缓存或兼容性？
- 是否新增外部数据源、许可证或凭据需求？

## 数据源贡献

新增 enrichment source 时：

- 优先复用公开、可引用的数据源；
- 记录来源 URL、更新时间和字段含义；
- 对缺失值、过期值和映射失败保持显式；
- 不把第三方数据重新包装成未经授权的完整镜像；
- 说明数据源的许可证、服务条款或再分发限制（如果存在）。

## Commit

推荐使用清晰、简短的 commit message，例如：

```text
feat(pipeline): add benchmark source adapter
fix(mcp): handle missing price fields
docs: clarify scoring limitations
```

## Security

发现可能的密钥、隐私或供应链问题时，不要把真实 secret 贴进 issue。请先阅读 [`SECURITY.md`](./SECURITY.md)。

## CI 策略：文档快检与工程全检

修改现有 `README.md`、`DESIGN.md`、`CONTRIBUTING.md` 或模块 README 时，CI 只运行必需的公开文件隐私检查、Markdown 链接校验、固定版本 Gitleaks 对当前文件及完整可访问 Git 历史的扫描、和范围分类回归测试，不再安装 Python/Node 全部依赖。

修改数据管线、MCP、配置、锁定依赖、CI、安全说明、测试代码，或新增/删除任何文件及混合变更时，额外运行原有的 **Pipeline 离线测试**和 **MCP 类型检查、构建与烟测**。变更范围无法证明时也默认全检。PR 与 `main` 的 CI 各运行一次，无重复功能分支 Push 构建。

这套 CI 是工程与发布前的辅助校验，不自动发布数据集或部署，也不代表对外部来源许可、真实评测质量或生产安全的批准。
