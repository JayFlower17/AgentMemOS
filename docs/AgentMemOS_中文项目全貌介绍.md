# AgentMemOS 中文项目全貌介绍

## 1. 项目定位

AgentMemOS 是一个面向 coding agent 和 multi-agent 工作流的外置记忆服务。它不是普通的聊天记录保存工具，也不是单纯的向量数据库封装，而是一个围绕“agent 记忆如何生成、保存、检索、治理、审计和复用”设计的基础设施层。

一句话概括：

```text
AgentMemOS = 给 agent 使用的可治理、可审计、可检索的长期记忆系统
```

它的目标不是替代 LLM，也不是替代 LangGraph、OpenAI Agents SDK、AutoGen、CrewAI 等 agent 框架，而是为这些框架提供一个独立的 memory service。Agent 框架负责执行任务、调用工具、编排流程；AgentMemOS 负责保存和管理跨步骤、跨任务、跨 agent 的经验。

## 2. 背景：为什么 agent 需要记忆系统

大多数 LLM 和 coding agent 默认只拥有短期上下文。它能看到当前 prompt、当前工具结果和当前对话窗口里的内容，但它并不天然知道：

- 上次项目推进到了哪一步。
- 用户曾经明确过哪些偏好。
- 某个技术选择为什么被接受或放弃。
- 某个测试、Redis、pgvector、API key 配置曾经踩过什么坑。
- 哪些旧记忆已经失效，不应该继续被 agent 使用。
- 哪些记忆只能被某个 agent 看到，哪些可以被团队共享。
- 这次检索出来的上下文为什么被选中。

如果没有记忆系统，agent 每次工作都容易变成“重新读项目、重新推理、重复犯错”。对于长周期软件工程、multi-agent 协作、研究任务、企业内部自动化流程，这种上下文丢失会显著降低可靠性。

AgentMemOS 试图解决的是：

```text
如何让 agent 的经验能够沉淀为结构化记忆，并且能被安全、准确、可解释地复用。
```

## 3. 面向的核心场景

### 3.1 Coding Agent 长期项目开发

在 coding agent 场景中，记忆系统可以保存：

- 项目目标和阶段。
- 代码库结构和架构边界。
- 用户偏好，例如“不换端口”“每一步记录到构建文档”。
- 已经完成的功能。
- 测试结果和验证路径。
- 之前出现过的错误与修复方式。
- 下次应继续推进的任务。

这类记忆不是普通聊天历史，而是 agent 下一次执行任务时可以检索、注入上下文、指导行动的工程事实。

### 3.2 Multi-Agent 协作

一个复杂项目中可能有 planner、coder、reviewer、governance agent、research agent 等角色。不同 agent 之间既需要共享部分信息，又不能完全暴露所有内部记录。

AgentMemOS 用作用域控制记忆可见性：

- `agent-local`：只属于某个 agent 的本地记忆。
- `task-local`：只在当前任务内可见。
- `team-shared`：团队角色之间共享。
- `project-global`：整个项目级别可复用。

这让记忆系统能够支持协作，而不是把所有上下文粗暴塞给所有 agent。

### 3.3 Agent RAG

RAG 的基本流程是 Retrieve + Generate：先检索相关信息，再交给 LLM 生成回答或行动。AgentMemOS 中的 retrieval 就是 agent memory 版的 RAG。

区别在于，AgentMemOS 检索的不是普通文档，而是经过抽取、分类、治理和审计的 memory。检索时不仅考虑语义相关性，也考虑作用域、角色、重要性、可信度、生命周期状态和治理关系。

### 3.4 记忆治理和审计

记忆系统越强，越需要治理。否则 agent 可能会使用过期、重复、冲突或不该看到的记忆。

AgentMemOS 支持：

- `active`：正常可用记忆。
- `superseded`：被新记忆替代，不再作为检索结果返回。
- `archived`：归档记忆，不再作为检索结果返回。
- `duplicates`：重复记忆关系。
- `conflicts_with`：冲突记忆关系。
- `supersedes`：新记忆替代旧记忆。

这些治理信息会影响检索结果，并被 trace 记录下来。

## 4. 核心概念

### 4.1 Event

Event 是 agent 运行过程中发生的事件，例如：

- agent 完成了某个任务。
- 工具调用返回了结果。
- reviewer 发现了风险。
- coder 记录了一个本地 scratch。
- 用户手动写入一条记忆。

Event 是记忆生成的原始输入。

### 4.2 Extractor

Extractor 负责判断 event 是否值得变成 memory，以及应该如何分类。它会输出：

- 是否写入 memory。
- memory 类型。
- 作用域。
- summary。
- confidence。
- importance。
- reason。
- signals。

当前项目支持两种 extractor：

- 本地规则型 extractor，默认启用，不需要外部 API。
- OpenAI-compatible LLM extractor，可接 OpenAI、DeepSeek 或其他兼容 chat completions 的第三方平台。

### 4.3 Memory

Memory 是系统真正保存和检索的结构化记忆。它不是完整聊天记录，而是被抽取后的可复用经验。

一个 memory 通常包含：

- `memory_id`
- `task_id`
- `agent_id`
- `memory_type`
- `scope`
- `content`
- `summary`
- `confidence`
- `importance`
- `status`
- `source_event_id`

### 4.4 Retrieval

Retrieval 是 agent 查询相关记忆的过程。输入通常包括：

- 当前任务 ID。
- 当前 agent ID。
- agent role。
- query。
- 允许访问的 scopes。

输出是经过权限、作用域、治理和排序后的 memory 列表。

### 4.5 Trace

Trace 记录一次检索为什么返回这些 memory，为什么过滤那些 memory。它让复杂记忆系统变得可解释。

Trace 会记录：

- selected memories。
- scored candidates。
- filtered memories。
- 每条候选记忆的分数构成。
- 被过滤原因。
- governance warning。

### 4.6 Governance

Governance 是记忆自维护能力，包括发现重复、冲突、替代关系，以及归档或 supersede 旧记忆。

它既可以由人类查看，也可以由 governance agent 或后端 job 处理。对于复杂系统而言，治理记录更多是给 agent 和系统自动化使用，人类看板只是辅助理解和调试。

## 5. 技术架构

AgentMemOS 当前采用 FastAPI + SQLite 默认本地运行，并通过抽象边界支持 Redis、pgvector、MCP、外部 LLM 和 embedding provider。

整体架构可以理解为：

```text
Agent / Agent Framework / MCP Client
        |
        v
HTTP API / SDK / MCP Tools
        |
        v
Services
        |
        v
Repositories / Job Queue / Event Bus
        |
        v
SQLite / InMemory / Redis / pgvector
```

更细的运行流程：

```text
POST /events
   |
   v
EventIngestionService
   |
   v
JobQueue: extract_memory
   |
   v
MemoryWorker
   |
   v
ExtractorProvider
   |
   v
MemoryRecord
   |
   v
JobQueue: embed_memory
   |
   v
EmbeddingProvider -> VectorStore
```

检索流程：

```text
POST /retrieve
   |
   v
结构化过滤：task / role / scope / status
   |
   v
关键词与规则打分
   |
   v
可选向量相似度打分
   |
   v
记忆治理过滤：archived / superseded / visibility
   |
   v
返回 memory context 并写入 retrieval trace
```

## 6. 主要模块

### 6.1 API Routes

FastAPI 路由负责把 HTTP 请求转换成服务调用。核心接口包括：

- `POST /events`：写入 agent event。
- `POST /memories`：手动创建 memory。
- `POST /retrieve`：检索相关 memory。
- `GET /traces/{trace_id}`：查看检索 trace。
- `GET /memory-decisions`：查看 memory 写入决策。
- `POST /governance/run`：运行治理 pass。
- `GET /memory-insights`：获取 agent-readable 治理洞察。
- `GET /queue/status`：查看队列状态。
- `GET /events/stream`：订阅 SSE 实时事件。

### 6.2 Services

Service 层负责业务编排，让 API routes 不直接操作所有底层细节。当前包括：

- `EventIngestionService`
- `MemoryLifecycleService`
- `GovernanceRelationService`

### 6.3 Repositories

Repository 层封装数据库访问，当前主要基于 SQLAlchemy + SQLite：

- `EventRepository`
- `MemoryRepository`
- `TraceRepository`
- `GovernanceRepository`

后续如果从 SQLite 扩展到 Postgres 主存储，repository boundary 可以降低替换成本。

### 6.4 Job Queue

Job queue 负责后台任务。当前支持：

- `extract_memory`
- `embed_memory`
- `governance_pass`

默认使用 `InMemoryJobQueue`，生产化路径支持 `RedisJobQueue`。

### 6.5 Worker

`MemoryWorker` 负责消费 job：

- 从 event 中抽取 memory。
- 为 memory 建立 embedding。
- 执行治理 pass。
- 发布实时事件。
- 处理 retry/backoff/dead-letter。

当前既支持 API 进程内 worker，也支持独立 worker 进程。

### 6.6 Event Bus 与 SSE

Event bus 负责向 dashboard、外部观察者或 agent runtime 发布实时事件。

本地模式下可以使用进程内 event bus。多进程模式下，Redis pub/sub 可以把 worker 进程产生的事件 fanout 到 API 进程，从而让 `/events/stream` 能看到独立 worker 的实时事件。

### 6.7 Vector 与 Embedding

AgentMemOS 的 vector 模块拆成两层：

- `EmbeddingProvider`：把文本转成向量。
- `VectorStore`：保存和检索向量。

当前 embedding provider：

- `HashingEmbeddingProvider`：本地哈希向量，默认启用，不需要 API key。
- `OpenAIEmbeddingProvider`：OpenAI-compatible `/embeddings` API，可接 OpenAI 或第三方平台。

当前 vector store：

- `InMemoryVectorStore`
- `SqliteVectorStore`
- `PgVectorStore`

## 7. 主要功能

### 7.1 事件驱动记忆写入

Agent 不需要直接决定所有长期记忆，而是先把运行事件提交给 AgentMemOS。系统通过 extractor 判断哪些事件值得写入 memory。

这样可以减少 agent 自己随意写记忆导致的噪声。

### 7.2 结构化记忆抽取

Extractor 会为 memory 赋予类型、作用域、可信度和重要性。写入时会保留 decision trace，让后续能解释“为什么这条 event 被写成这类 memory”。

### 7.3 手动记忆写入

系统也支持 `POST /memories` 手动写入 memory。适合保存用户明确指定的事实、项目规则、配置约束等。

### 7.4 作用域与角色可见性

AgentMemOS 不把所有 memory 一次性暴露给所有 agent。检索时会根据当前 agent、role、task 和 allowed scopes 过滤。

这对 multi-agent 系统非常重要，因为 reviewer 的发现、coder 的 scratch、project-global 的公共约束并不应该被同样处理。

### 7.5 记忆检索与 RAG

`POST /retrieve` 是 agent 使用记忆的核心入口。Agent 在执行任务前可以检索相关 memory，然后把返回内容注入 prompt/context。

当前检索打分综合考虑：

- importance。
- confidence。
- scope。
- role/type affinity。
- keyword overlap。
- 可选 embedding similarity。

### 7.6 向量检索增强

关键词检索适合精确匹配，但不擅长同义改写。向量检索可以按语义相似度找 memory。

例如 memory 是：

```text
Retries need bounded backoff before approval.
```

查询是：

```text
approval should wait when retry policy has no limit
```

即使关键词不完全一致，embedding similarity 仍可能找回相关记忆。

### 7.7 记忆治理

AgentMemOS 支持记忆生命周期和关系治理：

- archive 旧记忆。
- supersede 被替代的记忆。
- 标记 duplicates。
- 标记 conflicts。
- 生成 relation suggestions。
- 运行 governance pass。

治理不是装饰功能，而是防止 agent 使用过期、重复和冲突记忆的关键机制。

### 7.8 Trace 与可解释性

复杂 memory 系统必须能解释自己。Trace 面板和 API 可以回答：

- 为什么这条 memory 被选中？
- 为什么那条 memory 被过滤？
- 它的分数由哪些部分组成？
- 是关键词起作用，还是 embedding 起作用？
- 是否因为 archived / superseded 被排除？
- 是否存在冲突关系？

这对调试 agent 行为、审计系统决策、设计后续自动治理 agent 都很重要。

### 7.9 Dashboard

当前 dashboard 是开发辅助工具，用来理解 memories、events、traces、decisions 和 relations。它不是项目最终的核心产品形态。

真实使用中，AgentMemOS 更像后端 memory service，主要由 agent、SDK、MCP tools 或 worker 调用。

### 7.10 SDK 与 MCP

AgentMemOS 提供 Python SDK 和 MCP 工具层，使外部 agent 更容易接入。

Python SDK 适合 Python agent runtime 直接调用。MCP 适合被支持 MCP 的客户端或 agent runtime 当作工具服务器使用。

## 8. pgvector、向量数据库与 RAG 的关系

在 AgentMemOS 中：

```text
Embedding provider 负责生成向量
Vector store 负责保存和搜索向量
RAG 是使用这些检索结果增强 agent 上下文的流程
```

pgvector 是 PostgreSQL 的向量扩展，不是单独的数据库产品。它让 Postgres 能存储 vector 字段，并通过 cosine distance 等方式做相似度搜索。

AgentMemOS 使用 pgvector 的意义是：

- 让向量索引不只存在内存里。
- 多个 API/worker 进程可以共享同一个向量索引。
- 更接近生产环境。
- 可以与 Postgres 生态、备份、权限、运维工具结合。

本地 hashing embedding + InMemoryVectorStore 适合开发调试。OpenAI-compatible embedding + pgvector 更适合生产式语义检索。

需要注意：如果使用外部 embedding，例如 `text-embedding-3-large` 返回 3072 维，那么 `AGENTMEMOS_PGVECTOR_DIMENSIONS` 也必须设置为 3072。向量维度不匹配时，pgvector 不能正确写入或检索。

## 9. Redis 和独立 Worker 的作用

本地开发时，API 进程可以自己带一个 in-process worker。但生产环境中，API 和后台任务通常需要拆开。

Redis 在当前项目中扮演两个角色：

### 9.1 Redis Job Queue

API 收到 event 后只负责入队，独立 worker 从 Redis 队列消费任务。

好处：

- API 响应更轻。
- worker 可以独立扩容。
- 任务失败可以 retry。
- dead-letter 可以记录失败任务。
- 多进程不依赖同一个 Python 内存队列。

### 9.2 Redis Pub/Sub SSE Fanout

当 worker 独立运行时，它产生的 `memory.extracted`、`memory.embedded` 等事件不在 API 进程内。Redis pub/sub 可以把这些事件广播回 API 进程，让 dashboard 或 `/events/stream` 仍然能看到完整实时事件。

## 10. 部署方式

### 10.1 最小本地运行

最小运行只需要 Python 依赖，不需要 Redis、Postgres 或外部 API。

```powershell
python -m uvicorn agentmemos.main:app --host 127.0.0.1 --port 8014
```

默认能力：

- SQLite 主存储。
- In-memory job queue。
- API 进程内 worker。
- 本地规则 extractor。
- 本地 hashing embedding。
- 本地 in-memory vector store。

### 10.2 Redis 队列模式

启动 Redis：

```powershell
docker compose -f docker-compose.redis.yml up -d
```

API-only 模式：

```powershell
$env:AGENTMEMOS_JOB_QUEUE_BACKEND="redis"
$env:AGENTMEMOS_API_WORKER_ENABLED="false"
python -m uvicorn agentmemos.main:app --host 127.0.0.1 --port 8014
```

独立 worker：

```powershell
$env:AGENTMEMOS_JOB_QUEUE_BACKEND="redis"
python -m agentmemos.worker_app
```

### 10.3 pgvector 模式

启动 pgvector：

```powershell
docker compose -f docker-compose.pgvector.yml up -d
```

使用本地 hashing embedding 时：

```powershell
$env:AGENTMEMOS_VECTOR_STORE_BACKEND="pgvector"
$env:AGENTMEMOS_PGVECTOR_DIMENSIONS="64"
$env:AGENTMEMOS_VECTOR_RETRIEVAL_ENABLED="true"
$env:AGENTMEMOS_VECTOR_RETRIEVAL_WEIGHT="0.1"
python -m uvicorn agentmemos.main:app --host 127.0.0.1 --port 8014
```

使用外部 embedding 时，需要把 pgvector dimensions 改成 provider 返回的维度。例如当前第三方 `text-embedding-3-large` smoke 返回 3072 维：

```powershell
$env:AGENTMEMOS_EMBEDDING_PROVIDER="openai"
$env:AGENTMEMOS_OPENAI_EMBEDDING_API_KEY_FILE="$HOME\Desktop\LLM-API-KEY.txt"
$env:AGENTMEMOS_OPENAI_EMBEDDING_API_KEY_LABEL="Embedding"
$env:AGENTMEMOS_OPENAI_EMBEDDING_BASE_URL="https://api.jiekou.ai/openai"
$env:AGENTMEMOS_OPENAI_EMBEDDING_MODEL="text-embedding-3-large"
$env:AGENTMEMOS_VECTOR_STORE_BACKEND="pgvector"
$env:AGENTMEMOS_PGVECTOR_DIMENSIONS="3072"
```

### 10.4 OpenAI-compatible LLM Extractor

默认 extractor 是规则型。如果要启用 LLM extractor：

```powershell
$env:AGENTMEMOS_EXTRACTOR_BACKEND="openai"
$env:AGENTMEMOS_OPENAI_API_KEY_FILE="$HOME\Desktop\LLM-API-KEY.txt"
$env:AGENTMEMOS_OPENAI_API_KEY_LABEL="DeepSeek"
$env:AGENTMEMOS_OPENAI_BASE_URL="https://api.deepseek.com/v1"
$env:AGENTMEMOS_OPENAI_EXTRACTOR_MODEL="deepseek-chat"
```

项目不会提交 API key。上线时应通过环境变量、密钥管理服务或部署平台 secret 注入。

### 10.5 OpenAI-compatible Embedding Provider

启用外部 embedding：

```powershell
$env:AGENTMEMOS_EMBEDDING_PROVIDER="openai"
$env:AGENTMEMOS_OPENAI_EMBEDDING_API_KEY_FILE="$HOME\Desktop\LLM-API-KEY.txt"
$env:AGENTMEMOS_OPENAI_EMBEDDING_API_KEY_LABEL="Embedding"
$env:AGENTMEMOS_OPENAI_EMBEDDING_BASE_URL="https://api.jiekou.ai/openai"
$env:AGENTMEMOS_OPENAI_EMBEDDING_MODEL="text-embedding-3-large"
```

本地 smoke：

```powershell
python examples/openai_embedding_smoke.py
```

## 11. 如何适配其他 agent 框架

AgentMemOS 的接入方式可以分为四层。

### 11.1 直接 HTTP API

任何语言、任何 agent 框架都可以直接调用 HTTP API。

典型接入方式：

```text
agent 开始任务前 -> POST /retrieve
agent 执行过程中 -> POST /events
agent 需要显式保存事实 -> POST /memories
agent 需要治理 -> POST /governance/run
```

这是最通用的方式。

### 11.2 Python SDK

Python agent 可以使用 `AgentMemOSClient`。它封装了 HTTP 调用，适合快速接入。

典型模式：

```python
from agentmemos import AgentMemOSClient

memory = AgentMemOSClient("http://127.0.0.1:8014")

context = memory.retrieve(
    task_id="task_123",
    agent_id="coder_1",
    agent_role="coder",
    query="Implement retry logic safely",
)

memory.emit_event(
    event_type="task.completed",
    task_id="task_123",
    agent_id="coder_1",
    agent_role="coder",
    content="Retries require bounded backoff before approval.",
)
```

### 11.3 Adapter

Adapter 是对某个 agent 框架生命周期的包装。

AgentMemOS 已有：

- 通用 step adapter。
- LangGraph-style adapter。

它们的模式是：

```text
before_node / before_step -> retrieve memory
node / step 执行
after_node / after_step -> emit event
```

如果适配 AutoGen、CrewAI、OpenAI Agents SDK 等，也可以用类似方式做 adapter。重点不是替换框架，而是把框架的“执行前后”接到 AgentMemOS 的 retrieve 和 event ingestion。

### 11.4 MCP Tools

MCP 是更通用的工具协议。AgentMemOS 提供 MCP-ready tools 和官方 FastMCP runtime。

当前工具包括：

- `agentmemos_emit_event`
- `agentmemos_retrieve`
- `agentmemos_create_memory`
- `agentmemos_list_memories`
- `agentmemos_list_insights`
- `agentmemos_run_governance`

支持 MCP 的 agent client 可以把 AgentMemOS 当作工具服务器来调用。

## 12. 与 LangGraph、LangSmith、MCP 的关系

### 12.1 与 LangGraph

LangGraph 是 agent workflow 编排框架。它关心节点、状态、边、循环和工具调用。

AgentMemOS 是记忆服务。它可以被 LangGraph 节点调用，也可以通过 adapter 在节点执行前后自动检索和写入记忆。

关系是：

```text
LangGraph 负责任务流程编排
AgentMemOS 负责长期记忆管理
```

### 12.2 与 LangSmith

LangSmith 主要用于 tracing、debugging、evaluation 和 observability。它记录 agent run 的执行轨迹。

AgentMemOS 关注的是可复用 memory 的生命周期。

关系是：

```text
LangSmith 记录 agent 运行过程
AgentMemOS 沉淀可复用记忆
```

两者可以互补：LangSmith 里的运行轨迹可以成为 event 来源；AgentMemOS 的 memory 使用情况也可以作为 agent 行为的一部分被观测。

### 12.3 与 MCP

MCP 是工具协议。AgentMemOS 通过 MCP 把记忆能力暴露给支持 MCP 的 agent runtime。

关系是：

```text
MCP 是调用 AgentMemOS 的一种协议入口
AgentMemOS 是 MCP tool 背后的记忆服务
```

## 13. 当前完成度

AgentMemOS 当前已经完成一个可运行的 MVP+ 工程原型。它已经具备：

- Event ingestion。
- Worker-based extraction。
- Memory storage。
- Role-aware scoped retrieval。
- Retrieval trace。
- Write decision trace。
- Memory governance。
- Governance suggestions。
- Governance pass。
- Redis queue。
- Independent worker。
- Retry/backoff/dead-letter。
- Redis SSE fanout。
- SQLite vector store。
- pgvector adapter。
- OpenAI-compatible LLM extractor。
- OpenAI-compatible embedding provider。
- Python SDK。
- LangGraph-style adapter。
- MCP JSON-RPC runtime。
- Official FastMCP runtime。
- GitHub Actions CI。
- 本地 dashboard。

因此它已经不是“设计阶段项目”，而是可以被运行、测试、接入和演示的基础设施雏形。

## 14. 仍然需要补齐的生产化能力

虽然基本实现已经完成，但如果要作为生产服务长期运行，还需要继续补齐：

- 认证与鉴权。
- 多租户隔离。
- Postgres 主存储迁移，而不仅是 SQLite。
- 数据库 migration 管理。
- pgvector + 外部 embedding 的完整 E2E 验证。
- 更系统的 extractor 评测。
- 运行监控、日志、metrics、告警。
- 部署文档。
- MCP 在具体外部客户端中的实测。
- 更严格的数据保留、删除和隐私策略。

这些不是 MVP 是否成立的前置条件，而是从工程原型走向生产系统的后续路线。

## 15. 推荐理解路径

如果第一次理解 AgentMemOS，可以按下面顺序看：

1. 先把它理解成 agent 的外置长期记忆服务。
2. 再理解 event -> extractor -> memory -> retrieval 的闭环。
3. 然后理解 scope、role、status、relation 为什么是治理所必需。
4. 再看 trace 如何解释检索结果。
5. 最后看 Redis、pgvector、MCP、SDK 如何把它从本地 MVP 推向真实 agent 基础设施。

一句话总结：

```text
AgentMemOS 的核心价值不是“把文本存起来”，而是让 agent 的经验以可控、可检索、可治理、可审计的方式长期存在。
```

