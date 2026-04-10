import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))

import main as kg_main


class FakeNode(dict):
    def __init__(self, element_id, labels, **properties):
        super().__init__(properties)
        self.element_id = element_id
        self.labels = set(labels)


class FakeRelationship(dict):
    def __init__(self, element_id, rel_type, **properties):
        super().__init__(properties)
        self.element_id = element_id
        self.type = rel_type


class FakePath:
    def __init__(self, nodes, relationships):
        self.nodes = nodes
        self.relationships = relationships


class FakeSession:
    def __init__(self):
        self.central_bank = FakeNode("n1", ["Entity"], name=kg_main.CENTRAL_BANK, description="policy actor")
        self.reserve_ratio = FakeNode("n2", ["Entity"], name=kg_main.RESERVE_RATIO, description="reserve tool")
        self.deposit_reserve = FakeNode("n3", ["Entity"], name=kg_main.DEPOSIT_RESERVE, description="required reserves")
        self.derived_deposits = FakeNode("n4", ["Entity"], name=kg_main.DERIVED_DEPOSITS, description="derived deposits")
        self.credit_scale = FakeNode("n5", ["Entity"], name=kg_main.CREDIT_SCALE, description="lending scale")
        self.money_multiplier = FakeNode("n6", ["Entity"], name=kg_main.MONEY_MULTIPLIER, description="money multiplier")
        self.money_supply = FakeNode("n7", ["Entity"], name=kg_main.MONEY_SUPPLY, description="money supply")
        self.excess_reserve = FakeNode(
            "n8",
            ["Entity"],
            name=kg_main.EXCESS_RESERVE,
            description="extra reserves",
            attributes='{"\\u529f\\u80fd/\\u4f5c\\u7528": "\\u5f71\\u54cd\\u53ef\\u8d37\\u8d44\\u91d1"}',
        )

    def run(self, cypher, **params):
        if "RETURN 1" in cypher:
            return [{"value": 1}]

        if "RETURN n, score" in cypher:
            keyword = params["keyword"]
            if keyword in (kg_main.RESERVE_RATIO, "\u5b58\u6b3e\u51c6\u5907\u91d1\u7387"):
                return [{"n": self.reserve_ratio, "score": 100}]
            return []

        if "MATCH (n {name: $name})" in cypher and "RETURN n" in cypher:
            entity_map = {
                kg_main.CENTRAL_BANK: [self.central_bank],
                kg_main.RESERVE_RATIO: [self.reserve_ratio],
                kg_main.CREDIT_SCALE: [self.credit_scale],
                kg_main.EXCESS_RESERVE: [self.excess_reserve],
                kg_main.MONEY_MULTIPLIER: [self.money_multiplier],
                kg_main.MONEY_SUPPLY: [self.money_supply],
            }
            return [{"n": node} for node in entity_map.get(params["name"], [])]

        if "shortestPath((a)-[*1..4]->(b))" in cypher:
            return []

        if "shortestPath((a)-[*1..4]-(b))" in cypher:
            path = FakePath(
                [self.central_bank, self.reserve_ratio, self.money_supply],
                [
                    FakeRelationship("r1", "EXECUTES"),
                    FakeRelationship("r2", "INFLUENCES"),
                ],
            )
            return [{"p": path, "hops": 2}]

        if "shortestPath((a)-[*1..5]->(b))" in cypher:
            if params["start"] == kg_main.CENTRAL_BANK and params["end"] == kg_main.MONEY_SUPPLY:
                path = FakePath(
                    [self.central_bank, self.reserve_ratio, self.money_multiplier, self.money_supply],
                    [
                        FakeRelationship("r10", "EXECUTES"),
                        FakeRelationship("r11", "INFLUENCES"),
                        FakeRelationship("r12", "INFLUENCES"),
                    ],
                )
                return [{"p": path, "hops": 3}]
            return []

        if "shortestPath((a)-[*1..5]-(b))" in cypher:
            return []

        if "MATCH p = (n {name: $name})-[*1..3]->(m)" in cypher:
            if params["name"] == "A":
                path = FakePath(
                    [
                        FakeNode("a1", ["Entity"], name="A"),
                        FakeNode("a2", ["Entity"], name="B"),
                        FakeNode("a3", ["Entity"], name="C"),
                        FakeNode("a4", ["Entity"], name="D"),
                    ],
                    [
                        FakeRelationship("ra", "R1"),
                        FakeRelationship("rb", "R2"),
                        FakeRelationship("rc", "R3"),
                    ],
                )
                return [{"p": path}]
            return []

        if "MATCH p = (n {name: $name})-[*1..2]->(m)" in cypher:
            if params["name"] == kg_main.RESERVE_RATIO:
                path = FakePath(
                    [self.reserve_ratio, self.deposit_reserve, self.credit_scale],
                    [
                        FakeRelationship("r20", "INFLUENCES"),
                        FakeRelationship("r21", "INFLUENCES"),
                    ],
                )
                return [{"p": path}]
            if params["name"] == kg_main.CREDIT_SCALE:
                path = FakePath(
                    [self.credit_scale, self.money_supply],
                    [FakeRelationship("r22", "INFLUENCES")],
                )
                return [{"p": path}]
            if params["name"] == kg_main.EXCESS_RESERVE:
                path = FakePath(
                    [self.excess_reserve, self.credit_scale],
                    [FakeRelationship("r23", "INFLUENCES")],
                )
                return [{"p": path}]
            return []

        return []


class FakeSessionManager:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, exc_type, exc, tb):
        return False


class MechanismApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._original_get_session = kg_main.get_session
        cls.fake_session = FakeSession()
        kg_main.get_session = lambda: FakeSessionManager(cls.fake_session)
        cls.client = TestClient(kg_main.app)
        cls.headers = {"X-API-Key": kg_main.API_KEY}

    @classmethod
    def tearDownClass(cls):
        kg_main.get_session = cls._original_get_session

    def test_query_neighbors_returns_true_multi_hop_edges(self):
        response = self.client.post(
            "/query_neighbors",
            headers=self.headers,
            json={"entity_name": "A", "depth": 3, "limit": 10},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["found"])
        self.assertEqual(data["path_count"], 1)
        self.assertEqual(len(data["triples"]), 3)
        self.assertEqual(data["triples"][0]["start"]["properties"]["name"], "A")
        self.assertEqual(data["triples"][0]["end"]["properties"]["name"], "B")
        self.assertEqual(data["triples"][1]["start"]["properties"]["name"], "B")
        self.assertEqual(data["triples"][1]["end"]["properties"]["name"], "C")
        self.assertEqual(data["triples"][2]["start"]["properties"]["name"], "C")
        self.assertEqual(data["triples"][2]["end"]["properties"]["name"], "D")

    def test_find_path_falls_back_to_undirected(self):
        response = self.client.post(
            "/find_path",
            headers=self.headers,
            json={"start_entity": "A", "end_entity": "D", "max_hops": 4},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["found"])
        self.assertEqual(data["mode"], "undirected_fallback")
        self.assertEqual(data["paths"][0]["readable"], f"{kg_main.CENTRAL_BANK} -> {kg_main.RESERVE_RATIO} -> {kg_main.MONEY_SUPPLY}")

    def test_dispatch_explain_mechanism_returns_bridges(self):
        response = self.client.post(
            "/dispatch",
            headers=self.headers,
            json={
                "action": "explainMechanism",
                "question": "\u4e2d\u592e\u94f6\u884c\u4e3a\u4ec0\u4e48\u80fd\u901a\u8fc7\u5b58\u6b3e\u51c6\u5907\u91d1\u7387\u5f71\u54cd\u8d27\u5e01\u4f9b\u7ed9\uff1f",
                "start_entity": kg_main.CENTRAL_BANK,
                "end_entity": kg_main.MONEY_SUPPLY,
                "bridge_candidates": [
                    kg_main.LOANABLE_FUNDS,
                    kg_main.EXCESS_RESERVE,
                    kg_main.CREDIT_SCALE,
                    kg_main.CREDIT_CREATION,
                    kg_main.MONEY_MULTIPLIER,
                ],
                "max_hops": 5,
                "limit": 20,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["question_type"], "mechanism_chain")
        self.assertIn(kg_main.CREDIT_SCALE, data["resolved_bridges"])
        self.assertIn(kg_main.MONEY_MULTIPLIER, data["resolved_bridges"])
        self.assertGreaterEqual(len(data["answer_outline"]), 3)
        self.assertIn("result_json", data)


if __name__ == "__main__":
    unittest.main()
