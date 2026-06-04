# 星见澄夏高级记忆/人格/资产架构 v3.2 执行计划

## 目标

把 SumikaProject 从单体 SQLite 记忆和单一 persona 配置，升级为可审计、可扩展、可降级的 QQ 角色 Agent 工程。最终交付物包括：

- 可运行的高级记忆网关和本地降级实现。
- 对 MemMachine、Graphiti、Cognee、Mem0、Letta 的上游锁定、patch 记录和 adapter 设计。
- UTF-8 正常的人格、性格、思维风格、发言风格、身份、社会关系、世界书和视觉设定。
- DeepSeek 文本资产生成流水线。
- Yunwu gpt-image-2 图像资产生成流水线。
- 精选资产入库，未精选候选归档但不提交 Git。
- 隐私过滤、API key 脱敏、测试与部署文档。

## 阶段 1：仓库卫生和编码修复

1. 修复 README、`pyproject.toml`、`config/persona.yml`、测试、代码中的 UTF-8 乱码。
2. 新增本文件，作为本地长期执行计划。
3. 新增角色资产目录 `roles/sumika/`，将角色内容从运行配置中拆出。
4. 新增 `.gitignore` 规则，忽略 `vendor/upstream/`、候选图、归档图、原始 API 记录和 secrets。

验收：

- 使用 mojibake 关键字扫描时，不再命中源码、配置、README 和测试中的乱码。
- `python -m pytest -q` 仍可运行。

## 阶段 2：上游源码锁定和 patch 工作流

拉取并锁定以下上游仓库：

| 名称 | URL | 用途 | 默认集成方式 |
| --- | --- | --- | --- |
| MemMachine | https://github.com/MemMachine/MemMachine | 主长期记忆服务 | sidecar + patch |
| Graphiti | https://github.com/getzep/graphiti | 时间感知关系图 | sidecar + patch |
| Cognee | https://github.com/topoteretes/cognee | 世界书/角色知识库 | sidecar + patch |
| Mem0 | https://github.com/mem0ai/mem0 | fallback 记忆算法和评测基线 | adapter + patch |
| Letta | https://github.com/letta-ai/letta | core memory block 和自编辑记忆范式 | schema/reference patch |

执行方式：

1. 克隆到 `vendor/upstream/{memmachine,graphiti,cognee,mem0,letta}`。
2. 每个上游仓库创建 `codex/sumika-integration` 本地分支。
3. 记录 commit SHA 到 `third_party.lock.yml`。
4. 将上游修改保存为 `patches/upstream/<repo>/sumika-integration.patch`。
5. 新增 `scripts/manage_upstreams.py`，支持 clone、status、apply-patches、verify-patches。

验收：

- `third_party.lock.yml` 包含 URL、commit、license、用途和 patch 路径。
- 每个 patch 可在对应锁定 commit 上 clean apply。

## 阶段 3：高级记忆架构

新增 `MemoryGateway`，统一隔离业务代码和具体上游框架：

- `ingest_event(event)`
- `retrieve_context(query)`
- `update_profile(user_id, patch)`
- `update_relationship(subject_id, object_id, patch)`
- `reflect_session(scope, target_id)`
- `export_user_memory(user_id)`
- `delete_user_memory(user_id)`

记忆分层：

- Core memory blocks：身份、人格、当前关系、世界观、发言风格。
- Working memory：当前会话局部状态。
- Episodic memory：完整对话和证据，不只保存摘要。
- Profile memory：每个 QQ 用户的称呼、偏好、边界和好感趋势。
- Temporal graph：用户、群、关系、承诺、邀请、事实和有效期。
- Worldbook：角色世界、职业/日常、关系、地点、道具、兴趣和触发词。

验收：

- SQLite fallback 在上游服务不可用时仍可回复。
- 隐私过滤在所有 ingestion 之前执行。
- 个人记忆、世界记忆、关系图和世界书在接口上分离。

## 阶段 4：角色资产层

新增 `roles/sumika/`：

- `identity.yml`
- `personality.yml`
- `thinking_style.yml`
- `speech_style.yml`
- `relationships.yml`
- `worldbook.yml`
- `visual_bible.yml`
- `image_plan.yml`
- `manifest.yml`

DeepSeek 生成流程：

1. 本地写入简短草稿。
2. 读取桌面 `dskeynew.txt`，只在内存中使用。
3. 并发上限 30。
4. 使用 `deepseek-v4-pro`、`thinking.type=enabled`、`reasoning_effort=max`。
5. `max_tokens` 不低于 4096，防止只输出 reasoning。
6. 输出 JSON/YAML，保存脱敏 raw call record。

验收：

- 角色资产文件可由代码加载。
- prompt 编译器能把角色资产变成 core blocks。

## 阶段 5：图像资产流水线

Yunwu gpt-image-2 流程：

1. 读取桌面 `gptimg2.txt`，只在内存中使用。
2. 并发上限 5。
3. 使用旧参考图和文字锚点作为初始参考。
4. 每阶段把精选图加入锚点池。
5. 生成 3 倍候选并 3 选 1 精选：
   - 线稿 30 -> 10
   - 服饰/物件 45 -> 15
   - 立绘 60 -> 20
   - 头像 9 -> 3
   - 表情包 30 -> 10
   - CG 45 -> 15
6. 除 CG 外必须透明背景。
7. Pillow 校验 alpha；失败候选最多重试一次。

验收：

- 最终入库 73 张精选图。
- 未精选候选归档到 ignored 路径。
- manifest 记录 prompt、参考图、模型、时间、阶段、透明校验状态。

## 阶段 6：测试、部署和提交

测试：

- `python -m ruff check .`
- `python -m pytest -q`
- patch apply/reverse 测试。
- DeepSeek/Yunwu smoke test。
- 隐私过滤测试。
- 图像 manifest 和 alpha 校验。

提交策略：

1. 阶段 1-3 完成后提交一次。
2. 阶段 4 完成后提交一次。
3. 阶段 5 完成后提交一次。
4. 所有测试通过后推送 `codex/sumika-v3-memory-assets`。

## 安全约束

- 不提交 API key、QQ token、SSH key、cookie、Authorization header。
- 原始 API 记录必须脱敏。
- QQ 好友/群审批仍由管理 GUI 控制。
- 不支持滥加群、滥加好友、批量主动消息。
- 直接被问到是否 AI/机器人时，不冒充真实人类。
