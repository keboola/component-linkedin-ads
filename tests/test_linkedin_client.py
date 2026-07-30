import unittest
from unittest import mock

import requests
from keboola.component.exceptions import UserException

from linkedin_client import AccountsClient, LinkedInAdsClient


class TestLinkedInClientErrorSurfacing(unittest.TestCase):
    """The 'Load Accounts' path must surface the real cause as a UserException.

    Both cases below used to escape as a non-UserException and killed the job with
    an opaque exit-code-2 "internal error" (see SUPPORT-16765 / CFTL-712).
    """

    def _accounts_client(self) -> AccountsClient:
        return AccountsClient(LinkedInAdsClient(access_token="dummy-token"))

    def test_network_error_raises_user_exception(self):
        """A requests network failure on the accounts call is surfaced, not masked."""
        accounts = self._accounts_client()
        with mock.patch.object(
            accounts._client._session,
            "get",
            side_effect=requests.exceptions.ConnectionError("Connection reset by peer"),
        ):
            with self.assertRaises(UserException) as ctx:
                list(accounts.list_all_accounts())
        self.assertIn("Could not reach the LinkedIn API", str(ctx.exception))
        self.assertIn("Connection reset by peer", str(ctx.exception))

    def test_non_json_2xx_response_raises_user_exception(self):
        """A 2xx response with a non-JSON body is surfaced with the real body."""
        accounts = self._accounts_client()
        response = mock.Mock(spec=requests.Response)
        response.status_code = 200
        response.ok = True
        response.text = "<html><body>503 Service Unavailable</body></html>"
        response.json.side_effect = requests.exceptions.JSONDecodeError("Expecting value", response.text, 0)
        with mock.patch.object(accounts._client._session, "get", return_value=response):
            with self.assertRaises(UserException) as ctx:
                list(accounts.list_all_accounts())
        self.assertIn("non-JSON response", str(ctx.exception))
        self.assertIn("503 Service Unavailable", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
