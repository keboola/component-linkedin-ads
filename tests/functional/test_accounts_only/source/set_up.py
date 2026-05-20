"""Mock LinkedIn API HTTP calls for the test_accounts_only functional test case."""

from unittest import mock


def run(test_context):
    mock_response = mock.MagicMock()
    mock_response.status_code = 200
    mock_response.ok = True
    mock_response.json.return_value = {
        "id": 123456,
        "name": "Test Account",
        "status": "ACTIVE",
        "currency": "USD",
        "type": "BUSINESS",
        "changeAuditStamps": {"created": {"time": 1600000000000}},
    }
    patcher = mock.patch("requests.Session.get", return_value=mock_response)
    patcher.start()
    test_context._http_patcher = patcher
