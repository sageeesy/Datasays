import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.conversation_service import (
    create_conversation,
    delete_conversation,
    get_conversation,
    list_analysis_runs,
    list_conversations,
    save_analysis_exchange,
    save_message,
    update_conversation,
)


class ConversationServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.directory.name) / "datasays.db"
        self.environment = patch.dict(os.environ, {"DATASAYS_DB_PATH": str(self.database_path)})
        self.environment.start()

    def tearDown(self) -> None:
        self.environment.stop()
        self.directory.cleanup()

    def test_conversation_round_trip_and_file_updates(self) -> None:
        created = create_conversation("糖尿病分析", ["file-a", "file-b", "file-a"])

        self.assertEqual(created["title"], "糖尿病分析")
        self.assertEqual(created["activeFileIds"], ["file-a", "file-b"])
        self.assertEqual(created["messages"], [])

        updated = update_conversation(created["id"], "糖尿病 EDA", ["file-b"])
        self.assertEqual(updated["title"], "糖尿病 EDA")
        self.assertEqual(updated["activeFileIds"], ["file-b"])
        self.assertEqual(list_conversations()[0]["id"], created["id"])

    def test_messages_and_verified_analysis_runs_survive_reload(self) -> None:
        conversation = create_conversation("Analysis", ["file-a"])
        user_message_id = save_message(
            conversation_id=conversation["id"],
            role="user",
            content="Compare outcomes",
            message_id="user-1",
            file_names=["diabetes.csv"],
        )
        success_response = {
            "success": True,
            "llmResponse": {"content": "Verified", "status": "success"},
            "sandboxResponse": {
                "content": "Verified",
                "status": "success",
                "metadata": {
                    "analysis_result": {
                        "answer_type": "table",
                        "summary": "Grouped result",
                        "rows": [{"Outcome": 0, "mean": 10.25}],
                        "columns_used": ["Outcome"],
                        "assumptions": [],
                        "datasets": [],
                        "visualizations": [],
                    }
                },
            },
        }
        saved = save_analysis_exchange(
            conversation_id=conversation["id"],
            user_message_id=user_message_id,
            question="Compare outcomes",
            file_names=["diabetes.csv"],
            model="test-model",
            prompt_style="zero",
            response=success_response,
        )

        restored = get_conversation(conversation["id"])
        self.assertEqual(restored["messageCount"], 2)
        self.assertEqual(restored["messages"][0]["id"], "user-1")
        self.assertEqual(restored["messages"][1]["sandboxResponse"]["status"], "success")
        self.assertEqual(restored["messages"][1]["sandboxResponse"]["metadata"]["analysis_result"]["rows"][0]["mean"], 10.25)

        runs = list_analysis_runs(conversation["id"], verified_only=True)
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["id"], saved["runId"])
        self.assertEqual(runs[0]["response"]["sandboxResponse"]["status"], "success")

    def test_delete_cascades_messages_and_runs(self) -> None:
        conversation = create_conversation("Disposable")
        save_analysis_exchange(
            conversation_id=conversation["id"],
            user_message_id="user-delete",
            question="Test",
            file_names=[],
            model=None,
            prompt_style="zero",
            response={
                "success": True,
                "llmResponse": {"content": "Failed", "status": "error"},
                "sandboxResponse": {"content": "Failed", "status": "error"},
            },
        )

        self.assertEqual(len(list_analysis_runs(conversation["id"])), 1)
        self.assertEqual(list_analysis_runs(conversation["id"], verified_only=True), [])
        self.assertTrue(delete_conversation(conversation["id"]))
        self.assertIsNone(get_conversation(conversation["id"]))
        self.assertFalse(delete_conversation(conversation["id"]))


if __name__ == "__main__":
    unittest.main()
