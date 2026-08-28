import unittest
from unittest.mock import AsyncMock, patch

from app.routes import query


class QueryRouteTest(unittest.IsolatedAsyncioTestCase):
    async def test_process_query_forwards_optional_project_id(self) -> None:
        request = query.QueryRequest(
            question="Summarize the Olist metrics",
            fileIds=["file-1"],
            project_id="olist",
        )
        prepared = {
            "file_names": ["orders.csv"],
            "user_message_id": None,
            "conversation_context": None,
            "prompt_style": "zero",
            "model": None,
        }
        run_agent = AsyncMock(return_value={"content": "done", "status": "success"})

        with patch.object(query, "_prepare_query", AsyncMock(return_value=prepared)), patch.object(
            query, "run_data_analysis_agent", run_agent
        ):
            response = await query.process_query(request)

        self.assertTrue(response.success)
        run_agent.assert_awaited_once_with(
            request.question,
            request.fileIds,
            "zero",
            None,
            conversation_context=None,
            project_id="olist",
        )

    def test_project_id_remains_optional(self) -> None:
        request = query.QueryRequest(question="Summarize this file", fileIds=["file-1"])
        self.assertIsNone(request.project_id)


if __name__ == "__main__":
    unittest.main()
