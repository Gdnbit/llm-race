# data-pipeline

LLM_Race 的数据采集模块。它从公开或可配置的数据源拉取大模型信息，完成归一化、跨源对齐与合并，并产出 `dataset/dataset.json`。

## 当前数据源

| Adapter | 数据源 | 当前用途 |
|---|---|---|
| `sources/openrouter.py` | OpenRouter API | 模型 ID、价格、上下文、模态、可用性 |
| `sources/lmarena.py` | LMArena leaderboard | 人类偏好 Elo / 排名 |

设计中还预留 Artificial Analysis、Hugging Face、Vectara HHEM、SWE-Bench Verified、LiveCodeBench 等 enrichment source；以当前源码中的 adapter registry 为准。

## 处理流程

```text
anchor sources
    ↓
canonical models
    ↓
enrichment sources ──→ model-name alignment
    ↓                         ↓
    └──────────────→ merge / tier
                         ↓
                dataset/dataset.json
```

## 本地运行

### 安装依赖

```bash
uv sync
```

也可以使用：

```bash
pip install -e ".[dev]"
```

### 配置环境变量

OpenRouter 当前的模型列表接口可以无 key 使用。需要可选凭据时，可通过 shell、CI secret 或任意你信任的 secret manager 注入环境变量。

也可以从模板开始：

```bash
cp .env.example .env
```

按需填写 `.env`；不要提交真实密钥。项目的 `.gitignore` 已忽略 `.env` 和常见密钥文件。

支持的变量见 [`.env.example`](./.env.example)。常用变量包括：

- `OPENROUTER_API_KEY`
- `ARTIFICIAL_ANALYSIS_API_KEY`
- `ANTHROPIC_API_KEY`
- `HUGGINGFACE_TOKEN`
- `GITHUB_TOKEN`
- `DATASET_OUTPUT_PATH`
- `LOG_LEVEL`
- `PIPELINE_MODE`

### 运行 pipeline

```bash
uv run python -m src.build
```

只抓取和合并、不写文件：

```bash
uv run python -m src.build --dry-run
```

输出格式化 JSON：

```bash
uv run python -m src.build --pretty
```

运行测试：

```bash
uv run python -m unittest discover -s tests -v
```

## 添加新的 enrichment source

当前只有基础离线回归测试；HTTP、重试和更广的对齐覆盖仍需补充。
`PIPELINE_MODE` 目前仅记录到日志，`quick` 不会跳过适配器。
Artificial Analysis、Anthropic、Hugging Face 的配置项为规划预留，当前不调用这些服务。
空的 `DATASET_OUTPUT_PATH` 使用仓库内 `dataset/dataset.json` 默认路径。
抓取失败时 CLI 仍可能返回成功；使用结果前须检查 `sources` 状态和模型数量。

1. 实现 `EnrichmentAdapter`，参考 `src/sources/lmarena.py`。
2. 将 adapter 加入 `src/build.py` 的 `_enrichment_adapters()`。
3. 为字段映射、模型名对齐与异常输入补测试。
4. 确保单个数据源失败不会让其他数据源的结果丢失。

## 目录结构

```text
data-pipeline/
├── pyproject.toml
├── README.md
├── .env.example
├── src/
│   ├── build.py
│   ├── config.py
│   ├── models.py
│   ├── merger.py
│   ├── alignment/
│   ├── data/
│   └── sources/
└── uv.lock
```

## 安全说明

- 不要把真实 API key、token、`.env`、私钥或本机 secret-store 文件提交到仓库。
- CI 中使用平台提供的 secret store，并只向需要它的步骤暴露变量。
- 日志中不要打印 Authorization header 或完整凭据。
- 发布前应对当前树和 Git 历史执行 secret scan。
