from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import web_projection  # noqa: E402


def target(record: str, path: str, node: str) -> dict[str, str]:
    return {"record_id": record, "path_id": path, "node_id": node}


class CrossReferenceResolverTests(unittest.TestCase):
    def test_existing_em_dash_resolution_is_preserved(self) -> None:
        destination = target("REC-001", "PATH-001", "NODE-001")
        index = {web_projection._canonical_target("Parent—Child"): [destination]}

        self.assertEqual(
            [destination],
            web_projection._resolved_targets(" parent – child ", index),
        )

    def test_see_under_resolves_only_the_first_colon_as_hierarchy(self) -> None:
        destination = target("REC-001", "PATH-001", "NODE-001")
        index = {
            web_projection._canonical_target(
                "Parent—Second Directory: executive supremacy and electoral control"
            ): [destination]
        }

        self.assertEqual(
            [destination],
            web_projection._resolved_targets(
                "under Parent: Second Directory: executive supremacy and electoral control",
                index,
            ),
        )

    def test_bare_colon_is_not_inferred_as_hierarchy(self) -> None:
        destination = target("REC-001", "PATH-001", "NODE-001")
        index = {web_projection._canonical_target("Parent—Child"): [destination]}

        self.assertEqual([], web_projection._resolved_targets("Parent: Child", index))

    def test_multiple_targets_preserve_target_and_record_order(self) -> None:
        first = target("REC-001", "PATH-001", "NODE-001")
        second = target("REC-002", "PATH-002", "NODE-002")
        index = {
            web_projection._canonical_target("Parent—Child"): [first],
            web_projection._canonical_target("Other"): [second],
        }

        self.assertEqual(
            [first, second],
            web_projection._resolved_targets("under Parent: Child; Other", index),
        )

    def test_records_sharing_a_node_are_all_resolved(self) -> None:
        container = target("REC-CONTAINER", "PATH-CONTAINER", "NODE-SHARED")
        cross_reference = target("REC-XREF", "PATH-XREF", "NODE-SHARED")
        index = {
            web_projection._canonical_target("Shared heading"): [
                container,
                cross_reference,
            ]
        }

        self.assertEqual(
            [container, cross_reference],
            web_projection._resolved_targets("Shared heading", index),
        )

    def test_conflicting_or_missing_destinations_remain_unresolved(self) -> None:
        index = {
            web_projection._canonical_target("Ambiguous"): [
                target("REC-001", "PATH-001", "NODE-001"),
                target("REC-002", "PATH-002", "NODE-002"),
            ],
            web_projection._canonical_target("Present"): [
                target("REC-003", "PATH-003", "NODE-003")
            ],
        }

        self.assertEqual([], web_projection._resolved_targets("Ambiguous", index))
        self.assertEqual([], web_projection._resolved_targets("Missing", index))
        self.assertEqual([], web_projection._resolved_targets("Present; Missing", index))


class IndexRecordProjectionTests(unittest.TestCase):
    def test_projection_preserves_literal_target_and_shared_record_identities(self) -> None:
        grade = {
            "score": 100,
            "rating": 5,
            "band": "excellent",
            "color_token": "grade_excellent",
            "status": "passes",
        }
        candidate = {
            "records": [
                self.record("REC-PARENT", "PATH-PARENT", ["Parent"]),
                self.record("REC-DEST-1", "PATH-DEST-1", ["Parent", "Child"]),
                self.record("REC-DEST-2", "PATH-DEST-2", ["Parent", "Child"]),
                self.record(
                    "REC-SOURCE",
                    "PATH-SOURCE",
                    ["Source"],
                    references=[{
                        "reference_id": "XREF-001",
                        "type": "see",
                        "target": "under Parent: Child",
                    }],
                ),
            ]
        }
        inventory = {
            "paths": [
                {"path_id": "PATH-PARENT", "node_ids": ["NODE-PARENT"]},
                {"path_id": "PATH-DEST-1", "node_ids": ["NODE-PARENT", "NODE-CHILD"]},
                {"path_id": "PATH-DEST-2", "node_ids": ["NODE-PARENT", "NODE-CHILD"]},
                {"path_id": "PATH-SOURCE", "node_ids": ["NODE-SOURCE"]},
            ],
            "heading_nodes": [
                {"node_id": "NODE-PARENT", "parent_node_id": None},
                {"node_id": "NODE-CHILD", "parent_node_id": "NODE-PARENT"},
                {"node_id": "NODE-SOURCE", "parent_node_id": None},
            ],
        }
        items = {
            "locator_assessments": [],
            "path_assessments": [
                {"path_id": row["path_id"], "grade": grade}
                for row in inventory["paths"]
            ],
            "heading_node_assessments": [
                {"node_id": row["node_id"], "grade": grade}
                for row in inventory["heading_nodes"]
            ],
            "cross_reference_assessments": [{"reference_id": "XREF-001", "grade": grade}],
        }

        projected = web_projection.build_index_records(candidate, inventory, items)
        reference = projected["items"][-1]["cross_references"][0]

        self.assertEqual("under Parent: Child", reference["target_display"])
        self.assertEqual("resolved", reference["resolution"]["status"])
        self.assertEqual(
            ["REC-DEST-1", "REC-DEST-2"],
            [row["record_id"] for row in reference["resolution"]["targets"]],
        )
        self.assertEqual(grade, reference["assessment"]["grade"])

    @staticmethod
    def record(
        record_id: str,
        path_id: str,
        heading_path: list[str],
        *,
        references: list[dict[str, str]] | None = None,
    ) -> dict:
        references = references or []
        return {
            "record_id": record_id,
            "record_type": "cross_reference" if references else "container",
            "path_id": path_id,
            "heading_path": heading_path,
            "original_displayed_form": heading_path[-1],
            "locator_displays": [],
            "locator_assignments": [],
            "cross_references": references,
        }


if __name__ == "__main__":
    unittest.main()
