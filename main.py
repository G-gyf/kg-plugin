"""
KG query API backed by Neo4j/AuraDB.

The service keeps the original entity/neighbor/path/search endpoints and adds
an explanation-oriented mechanism retrieval endpoint for Coze workflows.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader
from neo4j import GraphDatabase
from pydantic import BaseModel, Field

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="KG Query API",
    description="Knowledge graph query service with mechanism-chain retrieval for Coze workflows.",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = os.getenv("API_KEY", "your-secret-key-here")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

NEO4J_URI = os.getenv("NEO4J_URI", "neo4j+s://xxxxxxxx.databases.neo4j.io")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "your-password")
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

query_logs: List[dict] = []

FIELD_MECHANISM = "\u4f20\u5bfc\u673a\u5236"
FIELD_ROLE = "\u529f\u80fd/\u4f5c\u7528"
FIELD_DEFINITION = "\u5b9a\u4e49"
FIELD_FEATURE = "\u7279\u70b9"
FIELD_BACKGROUND = "\u80cc\u666f/\u539f\u56e0"
FIELD_FORMULA = "\u8ba1\u7b97\u516c\u5f0f"

CENTRAL_BANK = "\u4e2d\u592e\u94f6\u884c"
RESERVE_RATIO = "\u6cd5\u5b9a\u5b58\u6b3e\u51c6\u5907\u91d1\u7387"
MONEY_SUPPLY = "\u8d27\u5e01\u4f9b\u7ed9"
CREDIT_SCALE = "\u4fe1\u8d37\u89c4\u6a21"
LOANABLE_FUNDS = "\u53ef\u8d37\u8d44\u91d1"
EXCESS_RESERVE = "\u8d85\u989d\u51c6\u5907\u91d1"
DEPOSIT_RESERVE = "\u5b58\u6b3e\u51c6\u5907\u91d1"
MONEY_MULTIPLIER = "\u8d27\u5e01\u4e58\u6570"
DERIVED_DEPOSITS = "\u6d3e\u751f\u5b58\u6b3e"
CREDIT_CREATION = "\u4fe1\u7528\u521b\u9020"
OPEN_MARKET = "\u516c\u5f00\u5e02\u573a\u4e1a\u52a1"
REDISCOUNT_RATE = "\u518d\u8d34\u73b0\u7387"
BASE_MONEY = "\u57fa\u7840\u8d27\u5e01"
RESERVES = "\u51c6\u5907\u91d1"
INTEREST_RATE = "\u5229\u7387"

SUPPORT_ATTRIBUTE_KEYS = (
    FIELD_MECHANISM,
    FIELD_ROLE,
    FIELD_DEFINITION,
    FIELD_FEATURE,
    FIELD_BACKGROUND,
    FIELD_FORMULA,
)

ENTITY_ALIASES: Dict[str, List[str]] = {
    CENTRAL_BANK: ["\u592e\u884c", "\u4e2d\u56fd\u4eba\u6c11\u94f6\u884c"],
    RESERVE_RATIO: [
        "\u5b58\u6b3e\u51c6\u5907\u91d1\u7387",
        "\u6cd5\u5b9a\u5b58\u6b3e\u51c6\u5907\u91d1\u6bd4\u7387",
        "\u6cd5\u5b9a\u51c6\u5907\u91d1\u7387",
        "\u51c6\u5907\u91d1\u7387",
        "\u5b58\u51c6\u7387",
        "\u6cd5\u5b9a\u6d3b\u671f\u5b58\u6b3e\u51c6\u5907\u91d1\u7387",
    ],
    MONEY_SUPPLY: ["\u8d27\u5e01\u4f9b\u5e94\u91cf"],
    CREDIT_SCALE: ["\u653e\u8d37\u89c4\u6a21", "\u8d37\u6b3e\u89c4\u6a21", "\u8d37\u6b3e\u6295\u653e"],
    LOANABLE_FUNDS: ["\u653e\u8d37\u8d44\u91d1"],
    MONEY_MULTIPLIER: ["\u6d3e\u751f\u500d\u6570", "\u5b58\u6b3e\u6d3e\u751f\u500d\u6570"],
    DERIVED_DEPOSITS: ["\u5b58\u6b3e\u6d3e\u751f"],
    CREDIT_CREATION: ["\u8d27\u5e01\u521b\u9020", "\u5b58\u6b3e\u8d27\u5e01\u591a\u500d\u521b\u9020"],
    OPEN_MARKET: ["\u516c\u5f00\u5e02\u573a\u64cd\u4f5c"],
    REDISCOUNT_RATE: ["\u8d34\u73b0\u7387", "\u518d\u8d34\u73b0\u653f\u7b56"],
}

ENTITY_PRIORITY = [
    CENTRAL_BANK,
    RESERVE_RATIO,
    OPEN_MARKET,
    REDISCOUNT_RATE,
    MONEY_SUPPLY,
    CREDIT_SCALE,
    MONEY_MULTIPLIER,
]

BRIDGE_HINTS: Dict[str, List[str]] = {
    RESERVE_RATIO: [DEPOSIT_RESERVE, EXCESS_RESERVE, LOANABLE_FUNDS, CREDIT_SCALE, CREDIT_CREATION, MONEY_MULTIPLIER, DERIVED_DEPOSITS],
    OPEN_MARKET: [BASE_MONEY, RESERVES, EXCESS_RESERVE, MONEY_MULTIPLIER, MONEY_SUPPLY],
    REDISCOUNT_RATE: [EXCESS_RESERVE, LOANABLE_FUNDS, CREDIT_SCALE, MONEY_SUPPLY],
    MONEY_SUPPLY: [LOANABLE_FUNDS, EXCESS_RESERVE, CREDIT_SCALE, CREDIT_CREATION, MONEY_MULTIPLIER, DERIVED_DEPOSITS],
}

BANK_CONSTRAINT_ALIASES = {DEPOSIT_RESERVE, RESERVES, EXCESS_RESERVE, LOANABLE_FUNDS, CREDIT_SCALE}
TRANSMISSION_ALIASES = {CREDIT_CREATION, MONEY_MULTIPLIER, DERIVED_DEPOSITS, "\u5b58\u6b3e\u8d27\u5e01\u591a\u500d\u521b\u9020", "\u5b58\u6b3e\u6d3e\u751f\u500d\u6570", "\u6d3e\u751f\u500d\u6570"}


class QueryEntityRequest(BaseModel):
    entity_name: str = Field(..., description="Entity name.")
    fuzzy: bool = Field(False, description="Use CONTAINS matching.")


class QueryNeighborsRequest(BaseModel):
    entity_name: str = Field(..., description="Source entity name.")
    depth: int = Field(1, ge=1, le=3, description="Traversal depth.")
    rel_type: Optional[str] = Field(None, description="Optional relationship type filter.")
    limit: int = Field(20, ge=1, le=50, description="Maximum returned paths.")


class FindPathRequest(BaseModel):
    start_entity: str = Field(..., description="Start entity name.")
    end_entity: str = Field(..., description="Target entity name.")
    max_hops: int = Field(4, ge=1, le=6, description="Maximum hop count.")


class FuzzySearchRequest(BaseModel):
    keyword: str = Field(..., description="Fuzzy search keyword.")
    limit: int = Field(10, ge=1, le=20, description="Maximum candidate count.")


class ExplainMechanismRequest(BaseModel):
    question: str = Field(..., description="Original user question.")
    start_entity: Optional[str] = Field(None, description="Known start entity if already extracted.")
    target_entity: Optional[str] = Field(None, description="Known target entity if already extracted.")
    bridge_candidates: List[str] = Field(default_factory=list, description="Preferred bridge entities.")
    max_hops: int = Field(5, ge=2, le=6, description="Maximum hop count for path retrieval.")
    limit: int = Field(30, ge=5, le=50, description="Maximum evidence items returned.")


class DispatchRequest(BaseModel):
    action: str = Field(..., description="queryEntity | queryNeighbors | findPath | fuzzySearch | explainMechanism")
    entity_name: Optional[str] = Field(None, description="Entity name for queryEntity/queryNeighbors.")
    fuzzy: bool = Field(False, description="Enable fuzzy matching for queryEntity.")
    depth: int = Field(1, ge=1, le=3, description="Depth for queryNeighbors.")
    rel_type: Optional[str] = Field(None, description="Relationship type filter for queryNeighbors.")
    limit: int = Field(20, ge=1, le=50, description="Maximum result count.")
    start_entity: Optional[str] = Field(None, description="Start entity for findPath/explainMechanism.")
    end_entity: Optional[str] = Field(None, description="End entity for findPath.")
    max_hops: int = Field(4, ge=1, le=6, description="Maximum hop count for findPath/explainMechanism.")
    keyword: Optional[str] = Field(None, description="Keyword for fuzzySearch.")
    question: Optional[str] = Field(None, description="Original question for explainMechanism.")
    bridge_candidates: List[str] = Field(default_factory=list, description="Bridge candidates for explainMechanism.")


async def verify_api_key(key: str = Security(api_key_header)):
    if key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return key


def get_session():
    return driver.session()


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
    logger.info("[%s] params=%s results=%s time=%.1fms", operation, params, result_count, elapsed_ms)


def serialize_node(node) -> dict:
    return {
        "id": getattr(node, "element_id", None),
        "labels": list(getattr(node, "labels", [])),
        "properties": dict(node),
    }


def canonicalize_entity_name(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    stripped = name.strip()
    lowered = stripped.lower()
    for canonical, variants in ENTITY_ALIASES.items():
        if lowered == canonical.lower():
            return canonical
        for variant in variants:
            if lowered == variant.lower():
                return canonical
    return stripped


def expand_entity_variants(name: Optional[str]) -> List[str]:
    canonical = canonicalize_entity_name(name)
    if not canonical:
        return []
    variants = [canonical]
    variants.extend(ENTITY_ALIASES.get(canonical, []))
    if name and name.strip() not in variants:
        variants.insert(0, name.strip())
    seen: Set[str] = set()
    ordered: List[str] = []
    for item in variants:
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def unique_list(items: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    ordered: List[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def detect_entities_in_text(text: str) -> List[str]:
    positions: List[Tuple[int, int, str]] = []
    lowered = text.lower()
    for canonical, variants in ENTITY_ALIASES.items():
        all_terms = [canonical, *variants]
        hits = [lowered.find(term.lower()) for term in all_terms if lowered.find(term.lower()) >= 0]
        if hits:
            priority = ENTITY_PRIORITY.index(canonical) if canonical in ENTITY_PRIORITY else 999
            positions.append((min(hits), priority, canonical))
    positions.sort(key=lambda item: (item[0], item[1]))
    return [canonical for _, _, canonical in positions]


def choose_start_entity(question_entities: Sequence[str], provided: Optional[str]) -> Optional[str]:
    if provided:
        return canonicalize_entity_name(provided)
    priorities = [CENTRAL_BANK, OPEN_MARKET, REDISCOUNT_RATE, RESERVE_RATIO, MONEY_SUPPLY]
    for candidate in priorities:
        if candidate in question_entities:
            return candidate
    return question_entities[0] if question_entities else None


def choose_target_entity(question_entities: Sequence[str], provided: Optional[str], start_entity: Optional[str]) -> Optional[str]:
    if provided:
        return canonicalize_entity_name(provided)
    priorities = [MONEY_SUPPLY, CREDIT_SCALE, INTEREST_RATE]
    for candidate in priorities:
        if candidate in question_entities and candidate != start_entity:
            return candidate
    for candidate in reversed(question_entities):
        if candidate != start_entity:
            return candidate
    return None


def infer_bridge_candidates(question_entities: Sequence[str], provided: Sequence[str]) -> List[str]:
    bridges = [canonicalize_entity_name(item) or item for item in provided]
    for entity in question_entities:
        for hint in BRIDGE_HINTS.get(entity, []):
            bridges.append(hint)
    return unique_list(bridges)


def build_rewritten_query(start_entity: Optional[str], focus_entities: Sequence[str], bridge_candidates: Sequence[str], target_entity: Optional[str]) -> str:
    pieces: List[str] = []
    if start_entity:
        pieces.append(start_entity)
    for item in focus_entities:
        if item not in pieces and item != target_entity:
            pieces.append(item)
    for item in bridge_candidates[:4]:
        if item not in pieces and item != target_entity:
            pieces.append(item)
    if target_entity and target_entity not in pieces:
        pieces.append(target_entity)
    if len(pieces) <= 1:
        return pieces[0] if pieces else ""
    separator = "\u3001"
    return f"{pieces[0]} \u5982\u4f55\u901a\u8fc7 {separator.join(pieces[1:])}"


def serialize_path(path, mode: Optional[str] = None) -> dict:
    nodes = [serialize_node(node) for node in path.nodes]
    edges = []
    relationships = []
    for index, rel in enumerate(path.relationships):
        source = nodes[index]
        target = nodes[index + 1]
        edge = {
            "id": getattr(rel, "element_id", None),
            "type": rel.type,
            "source": source["properties"].get("name"),
            "target": target["properties"].get("name"),
            "properties": dict(rel),
        }
        edges.append(edge)
        relationships.append({"type": rel.type, "properties": dict(rel)})
    payload = {
        "hops": len(edges),
        "nodes": nodes,
        "edges": edges,
        "relationships": relationships,
        "readable": " -> ".join(node["properties"].get("name", "?") for node in nodes),
    }
    if mode:
        payload["mode"] = mode
    return payload


def triples_from_paths(paths: Sequence[dict]) -> List[dict]:
    triples: List[dict] = []
    seen: Set[Tuple[str, str, str, str]] = set()
    for path in paths:
        nodes = path["nodes"]
        for index, edge in enumerate(path["edges"]):
            start_node = nodes[index]
            end_node = nodes[index + 1]
            key = (
                start_node["properties"].get("name", ""),
                edge["type"],
                end_node["properties"].get("name", ""),
                json.dumps(edge["properties"], ensure_ascii=False, sort_keys=True),
            )
            if key in seen:
                continue
            seen.add(key)
            triples.append(
                {
                    "start": start_node,
                    "relationship": {"type": edge["type"], "properties": edge["properties"]},
                    "end": end_node,
                }
            )
    return triples


def dedupe_paths(paths: Sequence[dict]) -> List[dict]:
    seen: Set[Tuple[Tuple[str, ...], Tuple[str, ...]]] = set()
    ordered: List[dict] = []
    for path in paths:
        node_names = tuple(node["properties"].get("name", "") for node in path["nodes"])
        rel_types = tuple(edge["type"] for edge in path["edges"])
        key = (node_names, rel_types)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(path)
    return ordered


def parse_attributes(raw_value: Any) -> Dict[str, Any]:
    if isinstance(raw_value, dict):
        return raw_value
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {}
    return {}


def truncate_text(value: Any, limit: int = 160) -> str:
    text = str(value).strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}..."


def extract_supporting_facts(node_payload: dict) -> List[dict]:
    props = node_payload["properties"]
    name = props.get("name")
    facts: List[dict] = []

    description = props.get("description")
    if description:
        facts.append({"entity": name, "source": "description", "field": "description", "fact": truncate_text(description)})

    attributes = parse_attributes(props.get("attributes"))
    for key in SUPPORT_ATTRIBUTE_KEYS:
        if key in attributes and attributes[key]:
            facts.append(
                {
                    "entity": name,
                    "source": "node_attributes",
                    "field": key,
                    "fact": truncate_text(attributes[key]),
                }
            )
    return facts


def query_entity_data(session, entity_name: str, fuzzy: bool = False) -> dict:
    variants = expand_entity_variants(entity_name) if not fuzzy else [entity_name]
    nodes: List[dict] = []
    matched_entity = None

    if fuzzy:
        cypher = """
            MATCH (n)
            WHERE toLower(n.name) CONTAINS toLower($name)
            RETURN n
            LIMIT 10
        """
        result = session.run(cypher, name=entity_name)
        nodes = [serialize_node(record["n"]) for record in result]
    else:
        cypher = """
            MATCH (n {name: $name})
            RETURN n
            LIMIT 5
        """
        for variant in variants:
            result = session.run(cypher, name=variant)
            nodes = [serialize_node(record["n"]) for record in result]
            if nodes:
                matched_entity = variant
                break

    if not nodes:
        return {"found": False, "entities": [], "message": f"No entity found: {entity_name}"}

    payload = {"found": True, "entities": nodes, "count": len(nodes)}
    if matched_entity:
        payload["matched_entity"] = matched_entity
    normalized = canonicalize_entity_name(entity_name)
    if normalized and normalized != entity_name:
        payload["normalized_entity"] = normalized
    return payload


def query_neighbors_data(session, entity_name: str, depth: int, rel_type: Optional[str], limit: int) -> dict:
    variants = expand_entity_variants(entity_name)
    paths: List[dict] = []
    matched_entity = None

    for variant in variants:
        if rel_type:
            cypher = f"""
                MATCH p = (n {{name: $name}})-[:`{rel_type}`*1..{depth}]->(m)
                RETURN DISTINCT p
                LIMIT $limit
            """
        else:
            cypher = f"""
                MATCH p = (n {{name: $name}})-[*1..{depth}]->(m)
                RETURN DISTINCT p
                LIMIT $limit
            """
        result = session.run(cypher, name=variant, limit=limit)
        paths = [serialize_path(record["p"]) for record in result]
        if paths:
            matched_entity = variant
            break

    paths = dedupe_paths(paths)
    triples = triples_from_paths(paths)
    payload = {
        "found": bool(paths),
        "paths": paths,
        "path_count": len(paths),
        "triples": triples,
        "count": len(triples),
        "source_entity": entity_name,
        "depth": depth,
    }
    if matched_entity:
        payload["matched_entity"] = matched_entity
    if not paths:
        payload["message"] = f"No neighbors found for {entity_name}"
    return payload


def run_single_path_query(session, start_name: str, end_name: str, max_hops: int, directed: bool) -> List[dict]:
    if directed:
        cypher = f"""
            MATCH (a {{name: $start}}), (b {{name: $end}})
            MATCH p = shortestPath((a)-[*1..{max_hops}]->(b))
            RETURN p, length(p) AS hops
            LIMIT 3
        """
    else:
        cypher = f"""
            MATCH (a {{name: $start}}), (b {{name: $end}})
            MATCH p = shortestPath((a)-[*1..{max_hops}]-(b))
            RETURN p, length(p) AS hops
            LIMIT 3
        """
    result = session.run(cypher, start=start_name, end=end_name)
    return [serialize_path(record["p"]) for record in result]


def find_path_data(session, start_entity: str, end_entity: str, max_hops: int) -> dict:
    start_variants = expand_entity_variants(start_entity)
    end_variants = expand_entity_variants(end_entity)

    paths: List[dict] = []
    mode = "directed"
    matched_pair: Optional[Tuple[str, str]] = None

    for start_variant in start_variants:
        for end_variant in end_variants:
            directed_paths = run_single_path_query(session, start_variant, end_variant, max_hops, directed=True)
            if directed_paths:
                paths = directed_paths
                matched_pair = (start_variant, end_variant)
                break
        if paths:
            break

    if not paths:
        mode = "undirected_fallback"
        for start_variant in start_variants:
            for end_variant in end_variants:
                undirected_paths = run_single_path_query(session, start_variant, end_variant, max_hops, directed=False)
                if undirected_paths:
                    paths = undirected_paths
                    matched_pair = (start_variant, end_variant)
                    break
            if paths:
                break

    paths = dedupe_paths(paths)
    if not paths:
        return {
            "found": False,
            "paths": [],
            "count": 0,
            "message": f"No path found from {start_entity} to {end_entity} within {max_hops} hops",
        }

    payload = {"found": True, "paths": [dict(path, mode=mode) for path in paths], "count": len(paths), "mode": mode}
    if matched_pair:
        payload["matched_start_entity"] = matched_pair[0]
        payload["matched_end_entity"] = matched_pair[1]
    return payload


def fuzzy_search_single_term(session, keyword: str, limit: int) -> List[dict]:
    cypher = """
        MATCH (n)
        WITH n,
             toLower(coalesce(n.name, "")) AS name_lc,
             toLower(coalesce(n.description, "")) AS desc_lc,
             toLower($keyword) AS keyword_lc
        WITH n, name_lc, desc_lc, keyword_lc,
             CASE
                 WHEN name_lc = keyword_lc THEN 100
                 WHEN name_lc CONTAINS keyword_lc THEN 80
                 WHEN keyword_lc CONTAINS name_lc THEN 70
                 WHEN desc_lc CONTAINS keyword_lc THEN 30
                 ELSE 0
             END AS score
        WHERE score > 0
        RETURN n, score
        ORDER BY score DESC, size(coalesce(n.name, "")) ASC
        LIMIT $limit
    """
    result = session.run(cypher, keyword=keyword, limit=limit)
    return [{"node": serialize_node(record["n"]), "score": record["score"]} for record in result]


def fuzzy_search_data(session, keyword: str, limit: int) -> dict:
    search_terms = unique_list([keyword, *expand_entity_variants(keyword)])
    scored_candidates: Dict[str, dict] = {}
    for offset, term in enumerate(search_terms):
        for item in fuzzy_search_single_term(session, term, limit):
            node = item["node"]
            node_id = node["id"] or node["properties"].get("name")
            adjusted_score = item["score"] - offset
            if node_id not in scored_candidates or adjusted_score > scored_candidates[node_id]["score"]:
                scored_candidates[node_id] = {"node": node, "score": adjusted_score}

    ordered = sorted(scored_candidates.values(), key=lambda item: (-item["score"], len(item["node"]["properties"].get("name", ""))))
    candidates = [item["node"] for item in ordered[:limit]]
    payload = {"found": bool(candidates), "candidates": candidates, "count": len(candidates), "keyword": keyword}
    normalized = canonicalize_entity_name(keyword)
    if normalized and normalized != keyword:
        payload["normalized_keyword"] = normalized
    if candidates:
        payload["best_match"] = candidates[0]["properties"].get("name")
    return payload


def names_from_path_payloads(paths: Sequence[dict]) -> List[str]:
    names: List[str] = []
    for path in paths:
        for node in path["nodes"]:
            name = node["properties"].get("name")
            if name:
                names.append(name)
    return unique_list(names)


def bridge_matched(candidate: str, names: Sequence[str], facts: Sequence[dict]) -> bool:
    variants = {canonicalize_entity_name(candidate) or candidate, *expand_entity_variants(candidate)}
    normalized_names = [canonicalize_entity_name(name) or name for name in names]
    fact_entities = [canonicalize_entity_name(item.get("entity")) or item.get("entity") for item in facts if item.get("entity")]
    return any(item in variants for item in normalized_names + fact_entities)


def pick_best_anchor_nodes(question_entities: Sequence[str], bridge_candidates: Sequence[str], start_entity: Optional[str], target_entity: Optional[str]) -> List[str]:
    ordered: List[str] = []
    for item in question_entities:
        if item not in ordered and item != target_entity:
            ordered.append(item)
    for item in bridge_candidates:
        if item not in ordered and item != target_entity:
            ordered.append(item)
    if start_entity and start_entity not in ordered:
        ordered.insert(0, start_entity)
    return ordered[:6]


def mechanism_slot_coverage(core_entities: Sequence[str]) -> Tuple[bool, bool]:
    normalized_entities = {canonicalize_entity_name(item) or item for item in core_entities}
    has_bank_constraint = any(item in normalized_entities for item in BANK_CONSTRAINT_ALIASES)
    has_transmission = any(item in normalized_entities for item in TRANSMISSION_ALIASES.union({MONEY_MULTIPLIER, CREDIT_CREATION, DERIVED_DEPOSITS}))
    return has_bank_constraint, has_transmission


def score_evidence_path(path: dict, start_entity: Optional[str], target_entity: Optional[str]) -> int:
    names = [canonicalize_entity_name(node["properties"].get("name")) or node["properties"].get("name") for node in path["nodes"]]
    score = len(names)
    if start_entity and start_entity in names:
        score += 4
    if target_entity and target_entity in names:
        score += 4
    has_bank_constraint, has_transmission = mechanism_slot_coverage(names)
    if has_bank_constraint:
        score += 3
    if has_transmission:
        score += 3
    if has_bank_constraint and has_transmission:
        score += 2
    if len(names) <= 3 and not (has_bank_constraint and has_transmission):
        score -= 3
    return score


def build_answer_outline(
    start_entity: Optional[str],
    focus_entities: Sequence[str],
    core_entities: Sequence[str],
    target_entity: Optional[str],
    path_complete: bool,
) -> List[str]:
    normalized = [canonicalize_entity_name(item) or item for item in core_entities]
    outline: List[str] = []

    policy_tool = next((item for item in focus_entities if item not in {start_entity, target_entity}), None)
    bank_bridge = next((item for item in [DEPOSIT_RESERVE, EXCESS_RESERVE, LOANABLE_FUNDS, CREDIT_SCALE] if item in normalized), None)
    transmission_bridge = next((item for item in [CREDIT_CREATION, MONEY_MULTIPLIER, DERIVED_DEPOSITS] if item in normalized), None)

    if start_entity and policy_tool:
        outline.append(f"{start_entity} \u8c03\u6574 {policy_tool}")
    elif start_entity:
        outline.append(f"{start_entity} \u53d1\u8d77\u8d27\u5e01\u653f\u7b56\u8c03\u8282")

    if bank_bridge:
        outline.append(f"{bank_bridge} \u7684\u53d8\u5316\u6539\u53d8\u5546\u4e1a\u94f6\u884c\u7684\u7ea6\u675f\u6761\u4ef6\u548c\u653e\u8d37\u80fd\u529b")

    if transmission_bridge:
        outline.append(f"{transmission_bridge} \u968f\u4e4b\u53d8\u5316\uff0c\u653e\u5927\u5bf9\u8d27\u5e01\u521b\u9020\u8fc7\u7a0b\u7684\u5f71\u54cd")

    if target_entity:
        if path_complete:
            outline.append(f"\u6700\u7ec8\u5f71\u54cd {target_entity}")
        else:
            outline.append(f"\u76ee\u524d\u8bc1\u636e\u5df2\u6062\u590d\u5230\u63a5\u8fd1 {target_entity} \u7684\u4f20\u5bfc\u73af\u8282")

    return outline


def explain_mechanism_data(session, req: ExplainMechanismRequest) -> dict:
    question_entities = detect_entities_in_text(req.question)
    start_entity = choose_start_entity(question_entities, req.start_entity)
    target_entity = choose_target_entity(question_entities, req.target_entity, start_entity)
    focus_entities = unique_list(question_entities)
    bridge_candidates = infer_bridge_candidates(question_entities, req.bridge_candidates)
    retrieval_query = build_rewritten_query(start_entity, focus_entities, bridge_candidates, target_entity)

    evidence_paths: List[dict] = []
    supporting_facts: List[dict] = []

    if start_entity and target_entity:
        path_result = find_path_data(session, start_entity, target_entity, req.max_hops)
        if path_result["found"]:
            for path in path_result["paths"]:
                evidence_paths.append(dict(path, source="find_path"))

    anchor_entities = pick_best_anchor_nodes(focus_entities, bridge_candidates, start_entity, target_entity)
    for anchor in anchor_entities:
        neighbor_result = query_neighbors_data(session, anchor, min(req.max_hops, 2), None, min(req.limit, 15))
        for path in neighbor_result.get("paths", []):
            evidence_paths.append(dict(path, source="query_neighbors", anchor_entity=anchor))

        entity_result = query_entity_data(session, anchor, fuzzy=False)
        for entity in entity_result.get("entities", []):
            supporting_facts.extend(extract_supporting_facts(entity))

    evidence_paths = dedupe_paths(evidence_paths)
    evidence_paths.sort(key=lambda path: score_evidence_path(path, start_entity, target_entity), reverse=True)
    evidence_paths = evidence_paths[: req.limit]

    path_names = names_from_path_payloads(evidence_paths)
    supporting_facts = supporting_facts[: req.limit]
    core_entities = unique_list([*focus_entities, *path_names, *(fact["entity"] for fact in supporting_facts if fact.get("entity"))])
    resolved_bridges = [bridge for bridge in bridge_candidates if bridge_matched(bridge, core_entities, supporting_facts)]
    missing_bridges = [bridge for bridge in bridge_candidates if bridge not in resolved_bridges]

    has_bank_constraint, has_transmission = mechanism_slot_coverage(core_entities)
    path_complete = bool(start_entity and target_entity and has_bank_constraint and has_transmission)
    answer_outline = build_answer_outline(start_entity, focus_entities, core_entities, target_entity, path_complete)

    if not evidence_paths and not supporting_facts:
        return {
            "found": False,
            "question_type": "mechanism_chain",
            "start_entity": start_entity,
            "target_entity": target_entity,
            "focus_entities": focus_entities,
            "core_entities": [],
            "resolved_bridges": [],
            "missing_bridges": bridge_candidates,
            "path_complete": False,
            "evidence_chains": [],
            "supporting_facts": [],
            "answer_outline": [],
            "retrieval_query": retrieval_query,
            "message": "No mechanism evidence found",
        }

    current_chain = " -> ".join(answer_outline) if answer_outline else ""
    return {
        "found": True,
        "question_type": "mechanism_chain",
        "start_entity": start_entity,
        "target_entity": target_entity,
        "focus_entities": focus_entities,
        "core_entities": core_entities,
        "resolved_bridges": resolved_bridges,
        "missing_bridges": missing_bridges,
        "recommended_next_entity": missing_bridges[0] if missing_bridges else None,
        "path_complete": path_complete,
        "evidence_chains": evidence_paths,
        "supporting_facts": supporting_facts,
        "answer_outline": answer_outline,
        "retrieval_query": retrieval_query,
        "current_mechanism_chain": current_chain,
        "count": len(evidence_paths) + len(supporting_facts),
    }


@app.post("/query_entity", dependencies=[Depends(verify_api_key)])
async def query_entity(req: QueryEntityRequest):
    start = time.time()
    try:
        with get_session() as session:
            result = query_entity_data(session, req.entity_name, fuzzy=req.fuzzy)
        elapsed = (time.time() - start) * 1000
        log_query("query_entity", req.model_dump(), result.get("count", 0), elapsed)
        return result
    except Exception as exc:  # pragma: no cover
        logger.error("query_entity error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/query_neighbors", dependencies=[Depends(verify_api_key)])
async def query_neighbors(req: QueryNeighborsRequest):
    start = time.time()
    try:
        with get_session() as session:
            result = query_neighbors_data(session, req.entity_name, req.depth, req.rel_type, req.limit)
        elapsed = (time.time() - start) * 1000
        log_query("query_neighbors", req.model_dump(), result.get("count", 0), elapsed)
        return result
    except Exception as exc:  # pragma: no cover
        logger.error("query_neighbors error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/find_path", dependencies=[Depends(verify_api_key)])
async def find_path(req: FindPathRequest):
    start = time.time()
    try:
        with get_session() as session:
            result = find_path_data(session, req.start_entity, req.end_entity, req.max_hops)
        elapsed = (time.time() - start) * 1000
        log_query("find_path", req.model_dump(), result.get("count", 0), elapsed)
        return result
    except Exception as exc:  # pragma: no cover
        logger.error("find_path error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/fuzzy_search", dependencies=[Depends(verify_api_key)])
async def fuzzy_search(req: FuzzySearchRequest):
    start = time.time()
    try:
        with get_session() as session:
            result = fuzzy_search_data(session, req.keyword, req.limit)
        elapsed = (time.time() - start) * 1000
        log_query("fuzzy_search", req.model_dump(), result.get("count", 0), elapsed)
        return result
    except Exception as exc:  # pragma: no cover
        logger.error("fuzzy_search error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/explain_mechanism", dependencies=[Depends(verify_api_key)])
async def explain_mechanism(req: ExplainMechanismRequest):
    start = time.time()
    try:
        with get_session() as session:
            result = explain_mechanism_data(session, req)
        elapsed = (time.time() - start) * 1000
        log_query("explain_mechanism", req.model_dump(), result.get("count", 0), elapsed)
        return result
    except Exception as exc:  # pragma: no cover
        logger.error("explain_mechanism error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/dispatch", dependencies=[Depends(verify_api_key)])
async def dispatch(req: DispatchRequest):
    if req.action == "queryEntity":
        if not req.entity_name:
            raise HTTPException(status_code=400, detail="queryEntity requires entity_name")
        result = await query_entity(QueryEntityRequest(entity_name=req.entity_name, fuzzy=req.fuzzy))
    elif req.action == "queryNeighbors":
        if not req.entity_name:
            raise HTTPException(status_code=400, detail="queryNeighbors requires entity_name")
        result = await query_neighbors(
            QueryNeighborsRequest(entity_name=req.entity_name, depth=req.depth, rel_type=req.rel_type, limit=req.limit)
        )
    elif req.action == "findPath":
        if not req.start_entity or not req.end_entity:
            raise HTTPException(status_code=400, detail="findPath requires start_entity and end_entity")
        result = await find_path(FindPathRequest(start_entity=req.start_entity, end_entity=req.end_entity, max_hops=req.max_hops))
    elif req.action == "fuzzySearch":
        if not req.keyword:
            raise HTTPException(status_code=400, detail="fuzzySearch requires keyword")
        result = await fuzzy_search(FuzzySearchRequest(keyword=req.keyword, limit=req.limit))
    elif req.action == "explainMechanism":
        if not req.question:
            raise HTTPException(status_code=400, detail="explainMechanism requires question")
        result = await explain_mechanism(
            ExplainMechanismRequest(
                question=req.question,
                start_entity=req.start_entity,
                target_entity=req.end_entity,
                bridge_candidates=req.bridge_candidates,
                max_hops=req.max_hops if req.max_hops > 1 else 5,
                limit=req.limit if req.limit > 0 else 30,
            )
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {req.action}")

    result["result_json"] = json.dumps(result, ensure_ascii=False)
    return result


@app.get("/logs", dependencies=[Depends(verify_api_key)])
async def get_logs(limit: int = 50):
    return {"logs": query_logs[-limit:], "total": len(query_logs)}


@app.get("/coze-session-token")
def get_coze_session_token(session_name: str):
    client_id = os.environ.get("COZE_CLIENT_ID", "")
    private_key = os.environ.get("COZE_PRIVATE_KEY", "").replace("\\n", "\n")
    public_key_id = os.environ.get("COZE_PUBLIC_KEY_ID", "")
    if not all([client_id, private_key, public_key_id]):
        raise HTTPException(status_code=503, detail="Coze OAuth not configured")

    config = {
        "client_type": "jwt",
        "client_id": client_id,
        "coze_www_base": "https://www.coze.cn",
        "coze_api_base": "https://api.coze.cn",
        "private_key": private_key,
        "public_key_id": public_key_id,
    }
    try:
        from cozepy import load_oauth_app_from_config

        jwt_app = load_oauth_app_from_config(config)
        oauth_token = jwt_app.get_access_token(ttl=3600, session_name=session_name)
        logger.info("[coze-jwt] token ok, expires_in=%s", getattr(oauth_token, "expires_in", "unknown"))
        return {"token": oauth_token.access_token}
    except Exception as exc:  # pragma: no cover
        logger.error("[coze-jwt] error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/health")
async def health():
    try:
        with get_session() as session:
            session.run("RETURN 1")
        return {"status": "ok", "neo4j": "connected", "timestamp": datetime.now().isoformat()}
    except Exception as exc:  # pragma: no cover
        return {"status": "error", "neo4j": str(exc)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
