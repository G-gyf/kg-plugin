"""
知识图谱问答智能体 - FastAPI 后端服务
连接方式: Neo4j Bolt 协议
作者: 知识图谱项目
"""

from fastapi import FastAPI, HTTPException, Security, Depends
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from neo4j import GraphDatabase
from typing import Optional, List, Any
import os
import logging
import time
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────
# 日志配置
# ─────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────
# FastAPI 初始化
# ─────────────────────────────────────────
app = FastAPI(
    title="KG Query API",
    description="知识图谱查询服务 - 供 Coze 插件调用",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────
# API Key 鉴权
# ─────────────────────────────────────────
API_KEY = os.getenv("API_KEY", "your-secret-key-here")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(key: str = Security(api_key_header)):
    if key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return key

# ─────────────────────────────────────────
# Neo4j 连接（Bolt 协议）
# ─────────────────────────────────────────
NEO4J_URI      = os.getenv("NEO4J_URI",      "neo4j+s://xxxxxxxx.databases.neo4j.io")  # AuraDB bolt+s URI
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "your-password")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

def get_session():
    return driver.session()

# ─────────────────────────────────────────
# 查询日志（内存存储，可替换为数据库）
# ─────────────────────────────────────────
query_logs: List[dict] = []

def log_query(operation: str, params: dict, result_count: int, elapsed_ms: float):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "operation": operation,
        "params": params,
        "result_count": result_count,
        "elapsed_ms": round(elapsed_ms, 2),
    }
    query_logs.append(entry)
    if len(query_logs) > 1000:
        query_logs.pop(0)
    logger.info(f"[{operation}] params={params} results={result_count} time={elapsed_ms:.1f}ms")

# ─────────────────────────────────────────
# Pydantic 请求模型
# ─────────────────────────────────────────

class QueryEntityRequest(BaseModel):
    entity_name: str = Field(..., description="实体名称，如 '深度学习'")
    fuzzy: bool = Field(False, description="是否开启模糊匹配")

class QueryNeighborsRequest(BaseModel):
    entity_name: str = Field(..., description="起始实体名称")
    depth: int = Field(1, ge=1, le=3, description="查询深度，1~3")
    rel_type: Optional[str] = Field(None, description="关系类型过滤，如 '包含'，不填则查所有")
    limit: int = Field(20, ge=1, le=50, description="返回结果上限")

class FindPathRequest(BaseModel):
    start_entity: str = Field(..., description="起始实体名称")
    end_entity: str = Field(..., description="目标实体名称")
    max_hops: int = Field(4, ge=1, le=6, description="最大跳数")

class FuzzySearchRequest(BaseModel):
    keyword: str = Field(..., description="模糊搜索关键词")
    limit: int = Field(10, ge=1, le=20, description="返回候选数量")

class DispatchRequest(BaseModel):
    action: str = Field(..., description="操作名称：queryEntity | queryNeighbors | findPath | fuzzySearch")
    entity_name: Optional[str] = Field(None, description="实体名称")
    fuzzy: bool = Field(False, description="是否模糊匹配")
    depth: int = Field(1, ge=1, le=3, description="查询深度")
    rel_type: Optional[str] = Field(None, description="关系类型过滤")
    limit: int = Field(20, ge=1, le=50, description="返回结果上限")
    start_entity: Optional[str] = Field(None, description="findPath 起始实体")
    end_entity: Optional[str] = Field(None, description="findPath 目标实体")
    max_hops: int = Field(4, ge=1, le=6, description="findPath 最大跳数")
    keyword: Optional[str] = Field(None, description="fuzzySearch 关键词")

# ─────────────────────────────────────────
# 工具函数：序列化 Neo4j 结果
# ─────────────────────────────────────────

def serialize_node(node) -> dict:
    return {
        "id": node.element_id,
        "labels": list(node.labels),
        "properties": dict(node),
    }

def serialize_relationship(rel) -> dict:
    return {
        "id": rel.element_id,
        "type": rel.type,
        "start_node_id": rel.start_node.element_id if rel.start_node else None,
        "end_node_id": rel.end_node.element_id if rel.end_node else None,
        "properties": dict(rel),
    }

# ─────────────────────────────────────────
# ① 接口：查询实体
# ─────────────────────────────────────────

@app.post("/query_entity", dependencies=[Depends(verify_api_key)])
async def query_entity(req: QueryEntityRequest):
    """
    按名称查询实体节点及其全部属性。
    fuzzy=true 时进行 CONTAINS 模糊匹配。
    """
    start = time.time()
    try:
        with get_session() as session:
            if req.fuzzy:
                cypher = """
                    MATCH (n)
                    WHERE toLower(n.name) CONTAINS toLower($name)
                    RETURN n LIMIT 10
                """
            else:
                cypher = """
                    MATCH (n {name: $name})
                    RETURN n LIMIT 5
                """
            result = session.run(cypher, name=req.entity_name)
            nodes = [serialize_node(record["n"]) for record in result]

        elapsed = (time.time() - start) * 1000
        log_query("query_entity", req.model_dump(), len(nodes), elapsed)

        if not nodes:
            return {"found": False, "entities": [], "message": f"未找到实体：{req.entity_name}"}
        return {"found": True, "entities": nodes, "count": len(nodes)}

    except Exception as e:
        logger.error(f"query_entity error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────
# ② 接口：查询 N 跳邻居
# ─────────────────────────────────────────

@app.post("/query_neighbors", dependencies=[Depends(verify_api_key)])
async def query_neighbors(req: QueryNeighborsRequest):
    """
    查询指定实体的 N 跳邻居节点和关系。
    支持按关系类型过滤。
    """
    start = time.time()
    try:
        with get_session() as session:
            if req.rel_type:
                cypher = f"""
                    MATCH (n {{name: $name}})-[r:`{req.rel_type}`*1..{req.depth}]->(m)
                    RETURN DISTINCT n, r, m LIMIT $limit
                """
            else:
                cypher = f"""
                    MATCH (n {{name: $name}})-[r*1..{req.depth}]->(m)
                    RETURN DISTINCT n, r, m LIMIT $limit
                """
            result = session.run(cypher, name=req.entity_name, limit=req.limit)

            triples = []
            for record in result:
                # r 是关系列表（多跳时）
                rel_list = record["r"]
                for rel in (rel_list if isinstance(rel_list, list) else [rel_list]):
                    triples.append({
                        "start": serialize_node(record["n"]),
                        "relationship": {"type": rel.type, "properties": dict(rel)},
                        "end": serialize_node(record["m"]),
                    })

        elapsed = (time.time() - start) * 1000
        log_query("query_neighbors", req.model_dump(), len(triples), elapsed)

        return {
            "found": len(triples) > 0,
            "triples": triples,
            "count": len(triples),
            "source_entity": req.entity_name,
            "depth": req.depth,
        }

    except Exception as e:
        logger.error(f"query_neighbors error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────
# ③ 接口：最短路径
# ─────────────────────────────────────────

@app.post("/find_path", dependencies=[Depends(verify_api_key)])
async def find_path(req: FindPathRequest):
    """
    查找两个实体之间的最短路径，用于多跳推理链路展示。
    """
    start = time.time()
    try:
        with get_session() as session:
            cypher = f"""
                MATCH (a {{name: $start}}), (b {{name: $end}})
                MATCH p = shortestPath((a)-[*1..{req.max_hops}]-(b))
                RETURN p, length(p) AS hops
                LIMIT 3
            """
            result = session.run(cypher, start=req.start_entity, end=req.end_entity)

            paths = []
            for record in result:
                path = record["p"]
                path_nodes = [serialize_node(n) for n in path.nodes]
                path_rels  = [{"type": r.type, "properties": dict(r)} for r in path.relationships]
                paths.append({
                    "hops": record["hops"],
                    "nodes": path_nodes,
                    "relationships": path_rels,
                    "readable": " → ".join(n["properties"].get("name", "?") for n in path_nodes),
                })

        elapsed = (time.time() - start) * 1000
        log_query("find_path", req.model_dump(), len(paths), elapsed)

        if not paths:
            return {"found": False, "paths": [], "message": f"未找到 {req.start_entity} 到 {req.end_entity} 的路径（{req.max_hops}跳内）"}
        return {"found": True, "paths": paths, "count": len(paths)}

    except Exception as e:
        logger.error(f"find_path error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────
# ④ 接口：模糊搜索
# ─────────────────────────────────────────

@app.post("/fuzzy_search", dependencies=[Depends(verify_api_key)])
async def fuzzy_search(req: FuzzySearchRequest):
    """
    实体名称模糊搜索，用于实体消歧和名称不精确时的候选匹配。
    """
    start = time.time()
    try:
        with get_session() as session:
            cypher = """
                MATCH (n)
                WHERE toLower(n.name) CONTAINS toLower($keyword)
                RETURN n.name AS name, labels(n) AS labels, n.definition AS definition
                LIMIT $limit
            """
            result = session.run(cypher, keyword=req.keyword, limit=req.limit)
            candidates = [
                {
                    "name": record["name"],
                    "labels": record["labels"],
                    "definition": record["definition"],
                }
                for record in result
            ]

        elapsed = (time.time() - start) * 1000
        log_query("fuzzy_search", req.model_dump(), len(candidates), elapsed)

        return {
            "found": len(candidates) > 0,
            "candidates": candidates,
            "count": len(candidates),
            "keyword": req.keyword,
        }

    except Exception as e:
        logger.error(f"fuzzy_search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────
# ⑤ 接口：统一分发（规避 Coze 并发分支限制）
# ─────────────────────────────────────────

@app.post("/dispatch", dependencies=[Depends(verify_api_key)])
async def dispatch(req: DispatchRequest):
    """
    统一分发接口：Coze Workflow 用单个 Plugin Node 调此接口，
    由后端按 action 字段路由，避免 Coze 并发分支嵌套限制。
    额外返回 result_json 字段（整个结果的 JSON 字符串），
    供 Coze Code Node 直接使用，绕过 Coze 不能正确传递嵌套对象数组的问题。
    """
    if req.action == "queryEntity":
        if not req.entity_name:
            raise HTTPException(status_code=400, detail="queryEntity 需要 entity_name")
        result = await query_entity(QueryEntityRequest(entity_name=req.entity_name, fuzzy=req.fuzzy))

    elif req.action == "queryNeighbors":
        if not req.entity_name:
            raise HTTPException(status_code=400, detail="queryNeighbors 需要 entity_name")
        result = await query_neighbors(QueryNeighborsRequest(
            entity_name=req.entity_name, depth=req.depth,
            rel_type=req.rel_type, limit=req.limit,
        ))

    elif req.action == "findPath":
        if not req.start_entity or not req.end_entity:
            raise HTTPException(status_code=400, detail="findPath 需要 start_entity 和 end_entity")
        result = await find_path(FindPathRequest(
            start_entity=req.start_entity, end_entity=req.end_entity, max_hops=req.max_hops,
        ))

    elif req.action == "fuzzySearch":
        if not req.keyword:
            raise HTTPException(status_code=400, detail="fuzzySearch 需要 keyword")
        result = await fuzzy_search(FuzzySearchRequest(keyword=req.keyword, limit=req.limit))

    else:
        raise HTTPException(status_code=400, detail=f"未知 action: {req.action}")

    result["result_json"] = json.dumps(result, ensure_ascii=False)
    return result


# ─────────────────────────────────────────
# ⑥ 接口：查询日志（演示用）
# ─────────────────────────────────────────

@app.get("/logs", dependencies=[Depends(verify_api_key)])
async def get_logs(limit: int = 50):
    """获取最近的查询日志，用于演示多跳推理路径。"""
    return {"logs": query_logs[-limit:], "total": len(query_logs)}


# ─────────────────────────────────────────
# 健康检查（无需鉴权）
# ─────────────────────────────────────────

@app.get("/health")
async def health():
    try:
        with get_session() as session:
            session.run("RETURN 1")
        return {"status": "ok", "neo4j": "connected", "timestamp": datetime.now().isoformat()}
    except Exception as e:
        return {"status": "error", "neo4j": str(e)}


# ─────────────────────────────────────────
# 启动
# ─────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
