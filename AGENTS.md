# AGENTS.md

## 项目定位

`kg_api` 是知识图谱查询与对外接入层，不负责生成图谱本身。

它的职责是：

1. 通过 FastAPI 暴露知识图谱查询接口。
2. 连接 Neo4j / AuraDB 执行 Cypher 查询。
3. 作为 Coze Plugin / Workflow 的后端服务。
4. 提供前端嵌入页与部署说明。

上游数据来源不是本仓库，而是 [`financial-knowledge-graph`](C:\Users\lenovo\Desktop\financial-knowledge-graph)，该项目负责从教材中抽取知识、构建图谱、导出 Neo4j 导入数据。

## 技术栈

- Python 3.11
- FastAPI
- Uvicorn
- Neo4j Python Driver
- Pydantic v2
- `python-dotenv`
- `httpx`
- `cozepy`
- Docker

## 目录框架

```text
kg_api/
├─ main.py                 # 唯一后端入口，定义所有 API、鉴权、Neo4j 连接、Coze token 代理
├─ openapi_schema.yaml     # Coze Plugin 导入用 OpenAPI 描述
├─ requirements.txt        # Python 依赖
├─ Dockerfile              # 容器部署入口
├─ env.example             # 运行所需环境变量示例
├─ docs/                   # GitHub Pages / 静态前端页
│  ├─ index.html           # Web 入口页，嵌入 Coze WebSDK
│  └─ assets/
│     ├─ app.js            # 前端交互、Coze SDK 初始化、会话 token 获取
│     └─ style.css         # 页面样式
├─ coze-kg-guide.html      # 完整部署与 Coze 工作流说明
└─ coze-kg-guide-first.html
```

## 后端框架

### 1. 接入层

`main.py` 中的 FastAPI app 负责：

- CORS 配置
- `X-API-Key` 鉴权
- 请求/响应模型定义
- 查询日志记录

### 2. 图查询层

同样在 `main.py` 内直接实现，当前未拆分 service/repository。

核心接口：

- `/query_entity`：按名称精确或模糊查实体
- `/query_neighbors`：按跳数查邻居子图
- `/find_path`：查最短路径
- `/fuzzy_search`：实体候选搜索
- `/dispatch`：统一分发接口，供 Coze 单插件节点调用
- `/logs`：最近查询日志
- `/health`：服务与 Neo4j 健康检查
- `/coze-session-token`：为前端或 Bot 会话签发 Coze JWT token

### 3. 数据访问层

当前是轻量实现，没有单独 DAO/Repository 文件。

模式是：

- 通过环境变量创建全局 `GraphDatabase.driver`
- 每次请求通过 `get_session()` 获取 Neo4j session
- 在接口内部直接拼接并执行 Cypher
- 将 Neo4j 节点/关系序列化为 JSON 返回

这意味着后续如需扩展，优先考虑把 `main.py` 拆为：

- `api/` 路由层
- `services/` 查询编排层
- `repositories/` Cypher 访问层
- `schemas/` 请求响应模型

## 运行依赖

关键环境变量：

- `NEO4J_URI`
- `NEO4J_USER`
- `NEO4J_PASSWORD`
- `API_KEY`
- `COZE_CLIENT_ID`
- `COZE_PRIVATE_KEY`
- `COZE_PUBLIC_KEY_ID`

其中前 4 个用于图查询服务，后 3 个用于 Coze OAuth token 代理。

## 数据流

```text
用户 / Coze Bot / Web 页面
  -> kg_api FastAPI
  -> Neo4j AuraDB
  -> 返回节点 / 三元组 / 路径
  -> Coze Workflow 或前端展示
```

如果走 Coze 工作流，推荐路径是：

```text
用户问题
  -> Coze Bot
  -> Coze Workflow
  -> kg_api /dispatch
  -> Neo4j
  -> result_json 返回给 Coze Code Node
  -> 大模型整合答案
```

`/dispatch` 的存在是为了规避 Coze 多分支与嵌套对象数组传递限制，这是本项目的关键设计点。

## 与 financial-knowledge-graph 的链接关系

两个仓库是明显的上下游关系：

1. `financial-knowledge-graph` 从教材 `.docx` 中抽取实体、关系、属性，产出章节 JSON。
2. 该项目再把 JSON 或人工校准后的 Excel 转成 Neo4j 可导入 CSV。
3. CSV 被导入 Neo4j / AuraDB。
4. `kg_api` 连接该 Neo4j 数据库，对外提供查询 API。
5. `financial-knowledge-graph/eval/eval_kg.py` 与 `eval/collect_coze_answers.py` 还会直接调用本项目接口做评测。

换句话说：

- `financial-knowledge-graph` 负责“建图”
- `kg_api` 负责“查图、对外服务、接入 Coze”

## 协作建议

在本仓库工作时，默认遵循以下判断：

1. 如果要修改查询行为，先看 `main.py` 的 Cypher 与序列化逻辑。
2. 如果要修改 Coze 插件字段，必须同时检查 `openapi_schema.yaml` 与 `main.py` 返回结构。
3. 如果要修改前端嵌入页，重点看 `docs/index.html` 和 `docs/assets/app.js`。
4. 如果查询结果异常，优先确认问题来自：
   - Neo4j 数据是否完整
   - 接口 Cypher 是否匹配数据模型
   - 上游 `financial-knowledge-graph` 导出的字段是否符合当前查询假设

## 当前架构结论

这是一个“单文件后端 + 外部图数据库 + Coze 接入”的轻量服务项目。

优点是部署简单、链路直观。
风险是 `main.py` 职责过多，后续功能增长时应优先做模块拆分。
