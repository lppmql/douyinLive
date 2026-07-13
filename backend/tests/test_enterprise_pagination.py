import unittest

from app.services.collector.manual_collect import _fetch_enterprise_rows


class FakePage:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def evaluate(self, _script, args):
        page_no = args["payload"]["pageNum"]
        self.calls.append(page_no)
        return self.responses.get(page_no, self.responses.get("default", {"data": {}}))


class EnterprisePaginationTest(unittest.IsolatedAsyncioTestCase):
    async def test_collects_all_pages_using_total(self):
        page = FakePage({
            1: {"data": {"employeeList": [{"iesUid": "1"}, {"iesUid": "2"}], "total": 3, "self": {"iesUid": "0"}}},
            2: {"data": {"employeeList": [{"iesUid": "3"}], "total": 3}},
        })

        rows, own = await _fetch_enterprise_rows(
            page, "/accounts", {}, "", ("employeeList",)
        )

        self.assertEqual([row["iesUid"] for row in rows], ["1", "2", "3"])
        self.assertEqual(own["iesUid"], "0")
        self.assertEqual(page.calls, [1, 2])

    async def test_stops_when_endpoint_ignores_pagination(self):
        page = FakePage({
            "default": {"data": {"roomLists": [{"roomId": "same-room"}]}}
        })

        rows, _ = await _fetch_enterprise_rows(
            page, "/rooms", {}, "", ("roomLists",)
        )

        self.assertEqual(rows, [{"roomId": "same-room"}])
        self.assertEqual(page.calls, [1, 2])

    async def test_merges_employee_and_enterprise_lists(self):
        page = FakePage({
            "default": {
                "data": {
                    "employeeList": [{"iesUid": "employee"}],
                    "enterpiseList": [{"iesUid": "enterprise"}],
                }
            }
        })

        rows, _ = await _fetch_enterprise_rows(
            page,
            "/accounts",
            {},
            "",
            ("employeeList", "enterpiseList"),
        )

        self.assertEqual(
            [row["iesUid"] for row in rows],
            ["employee", "enterprise"],
        )


if __name__ == "__main__":
    unittest.main()
