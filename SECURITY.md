# Security Policy

LLM_Race 是一个开发者工具项目。安全重点主要包括凭据处理、第三方数据源与依赖供应链。

## 不应提交到仓库的内容

- API key、access token、refresh token
- `.env` 或真实 secret 配置
- SSH / TLS 私钥
- 云厂商、GitHub、模型提供商凭据
- 本机 secret-store、密码管理器导出文件
- 私人数据、客户数据或其他未授权数据

仓库中的 `.env.example` 只能包含空值或明显的占位符。

## 本地与 CI 凭据

通过进程环境变量、CI secret store 或受信任的外部 secret manager 注入凭据。不要在代码、文档、日志或命令示例中写入真实值。

代码不得记录 Authorization header 或完整 token。

## 发现泄露怎么办

如果真实 secret 曾经进入 Git 历史，仅在最新版本删除它并不够。应：

1. 立即在对应服务端撤销 / 轮换凭据；
2. 清理 Git 历史或重新发布干净历史；
3. 再次执行 secret scan；
4. 检查 CI、release、artifact 与日志是否存在副本。

## 报告安全问题

优先使用 GitHub 的 [私密漏洞报告](https://github.com/XINsai/llm-race/security/advisories/new)。
仅当前 0.1.x 开发线接受安全修复；这不构成生产环境安全保证。

如果问题涉及真实凭据或个人信息，请不要把敏感值直接发布在公开 issue 中。可以先创建不包含 secret 的最小描述，并通过仓库维护者提供的私密渠道补充必要信息。
