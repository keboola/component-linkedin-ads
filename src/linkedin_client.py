"""LinkedIn Ads API client."""

import logging
import random
import time
import urllib.parse
from collections.abc import Iterator
from datetime import date, datetime, timezone
from typing import Literal

import requests
from keboola.component.exceptions import UserException

BASE_URL = "https://api.linkedin.com/rest"
LINKEDIN_VERSION = "202603"


class LinkedInAdsClient:
    """Base HTTP client for LinkedIn Ads REST API."""

    def __init__(self, access_token: str) -> None:
        self._access_token = access_token
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {access_token}",
                "LinkedIn-Version": LINKEDIN_VERSION,
                "X-Restli-Protocol-Version": "2.0.0",
            }
        )

    def get(self, path: str, params: dict | None = None) -> dict:
        """Execute authenticated GET, raises on non-2xx."""
        url = f"{BASE_URL}{path}"
        response = self._request_with_retry(url, params or {})
        return response.json()

    def _paginate_cursor(self, path: str, params: dict) -> Iterator[dict]:
        """Yield all elements using cursor-based pagination (pageSize/pageToken), required by search APIs since version 202401."""
        page_params = {**params, "pageSize": 100}
        while True:
            data = self.get(path, page_params)
            elements = data.get("elements", [])
            for element in elements:
                yield element
            next_token = data.get("metadata", {}).get("nextPageToken")
            if not next_token or not elements:
                break
            page_params["pageToken"] = next_token

    def _request_with_retry(self, url: str, params: dict) -> requests.Response:
        """Execute HTTP GET with retry logic for 429 and 5xx responses."""
        # Build query string keeping Rest.li structural characters unencoded.
        # The requests library would encode ( ) , : as %28 %29 %2C %3A, which
        # breaks LinkedIn's Rest.li 2.0 parenthetical syntax.
        if params:
            qs = "&".join(
                f"{urllib.parse.quote(str(k), safe='')}={urllib.parse.quote(str(v), safe='(),:%')}"
                for k, v in params.items()
            )
            full_url = f"{url}?{qs}"
        else:
            full_url = url

        # HTTP 429: exponential backoff with jitter, max 5 retries
        max_429_retries = 5
        # HTTP 5xx: fixed 5s delay, max 3 retries
        max_5xx_retries = 3

        attempt_429 = 0
        attempt_5xx = 0

        while True:
            response = self._session.get(full_url)

            if response.status_code in (401, 403):
                raise UserException(
                    f"Authentication failed (HTTP {response.status_code}). "
                    "Re-authorize the component via Keboola OAuth."
                )

            if response.status_code == 429:
                if attempt_429 >= max_429_retries:
                    raise UserException(f"Rate limit exceeded after {max_429_retries} retries.")
                wait = (2**attempt_429) + random.uniform(0, 1)
                logging.warning(f"Rate limited (429), retrying in {wait:.1f}s (attempt {attempt_429 + 1})")
                time.sleep(wait)
                attempt_429 += 1
                continue

            if response.status_code >= 500:
                if attempt_5xx >= max_5xx_retries:
                    raise UserException(
                        f"LinkedIn API server error ({response.status_code}) after {max_5xx_retries} retries. "
                        "Try again later."
                    )
                logging.warning(f"Server error ({response.status_code}), retrying in 5s (attempt {attempt_5xx + 1})")
                time.sleep(5)
                attempt_5xx += 1
                continue

            if not response.ok:
                raise UserException(
                    f"LinkedIn API request failed ({response.status_code}): {response.text[:200]}"
                )
            return response


class _ResourceClient:
    """Base class for LinkedIn Ads resource clients."""

    def __init__(self, client: LinkedInAdsClient) -> None:
        self._client = client


class AccountsClient(_ResourceClient):
    """Fetches ad account data."""

    def list_all_accounts(self) -> Iterator[dict]:
        """Yield all ad accounts accessible to the authenticated user."""
        try:
            for element in self._client._paginate_cursor("/adAccounts", {"q": "search"}):
                yield {
                    "id": str(element.get("id", "")),
                    "name": element.get("name", ""),
                }
        except requests.exceptions.HTTPError as e:
            raise UserException(f"Failed to list ad accounts: {e}") from e

    def get_accounts(self, account_id: str) -> Iterator[dict]:
        element = self._client.get(f"/adAccounts/{account_id}")
        yield {
            "id": str(element.get("id", "")),
            "name": element.get("name", ""),
            "status": element.get("status", ""),
            "currency": element.get("currency", ""),
            "type": element.get("type", ""),
            "created_at": element.get("changeAuditStamps", {}).get("created", {}).get("time", ""),
        }


class CampaignsClient(_ResourceClient):
    """Fetches campaign groups and campaigns."""

    def get_campaign_groups(self, account_id: str) -> Iterator[dict]:
        params = {"q": "search"}
        for element in self._client._paginate_cursor(f"/adAccounts/{account_id}/adCampaignGroups", params):
            budget = element.get("totalBudget", {})
            yield {
                "id": str(element.get("id", "")),
                "account_id": account_id,
                "name": element.get("name", ""),
                "status": element.get("status", ""),
                "total_budget": budget.get("amount", ""),
                "start_date": _format_date_field(element.get("runSchedule", {}).get("start")),
                "end_date": _format_date_field(element.get("runSchedule", {}).get("end")),
            }

    def get_campaigns(self, account_id: str) -> Iterator[dict]:
        params = {"q": "search"}
        for element in self._client._paginate_cursor(f"/adAccounts/{account_id}/adCampaigns", params):
            daily_budget = element.get("dailyBudget", {})
            unit_cost = element.get("unitCost", {})
            group_urn = element.get("campaignGroup", "")
            group_id = group_urn.split(":")[-1] if group_urn else ""
            yield {
                "id": str(element.get("id", "")),
                "group_id": group_id,
                "account_id": account_id,
                "name": element.get("name", ""),
                "status": element.get("status", ""),
                "type": element.get("type", ""),
                "cost_type": element.get("costType", ""),
                "daily_budget": daily_budget.get("amount", ""),
                "unit_cost": unit_cost.get("amount", ""),
            }


class CreativesClient(_ResourceClient):
    """Fetches ad creatives."""

    def get_creatives(self, account_id: str, campaign_ids: tuple[str, ...] | list[str]) -> Iterator[dict]:
        encoded_urns = ",".join(
            f"urn:li:sponsoredCampaign:{cid}".replace(":", "%3A") for cid in campaign_ids
        )
        params = {
            "q": "criteria",
            "campaigns": f"List({encoded_urns})",
        }
        for element in self._client._paginate_cursor(f"/adAccounts/{account_id}/creatives", params):
            content = element.get("content", {})
            reference = content.get("reference", "")
            text_ad = content.get("textAd", {})
            raw_id = element.get("id", "")
            creative_id = raw_id.split(":")[-1] if raw_id else ""
            campaign_urn = element.get("campaign", "")
            campaign_id = campaign_urn.split(":")[-1] if campaign_urn else ""
            yield {
                "id": creative_id,
                "campaign_id": campaign_id,
                "status": element.get("intendedStatus", ""),
                "type": element.get("type", ""),
                "content_url": reference,
                "content_title": text_ad.get("headline", ""),
                "content_text": text_ad.get("text", ""),
            }


class AnalyticsClient(_ResourceClient):
    """Fetches ad performance analytics."""

    def get_analytics(
        self,
        account_id: str,
        pivot: Literal["CAMPAIGN", "CREATIVE"],
        start_date: date,
        end_date: date,
        granularity: str,
        creative_campaign_map: dict[str, str] | None = None,
    ) -> Iterator[dict]:
        encoded_urn = f"urn:li:sponsoredAccount:{account_id}".replace(":", "%3A")
        params = {
            "q": "analytics",
            "pivot": pivot,
            "timeGranularity": granularity,
            "accounts": f"List({encoded_urn})",
            "dateRange": (
                f"(start:(year:{start_date.year},month:{start_date.month},day:{start_date.day}),"
                f"end:(year:{end_date.year},month:{end_date.month},day:{end_date.day}))"
            ),
            "fields": ",".join(
                [
                    "impressions",
                    "clicks",
                    "costInLocalCurrency",
                    "externalWebsiteConversions",
                    "videoViews",
                    "reactions",
                    "shares",
                    "comments",
                    "follows",
                    "pivotValues",
                    "dateRange",
                ]
            ),
        }
        # adAnalytics does not support pagination — all results returned in one response (max 15,000)
        data = self._client.get("/adAnalytics", params)
        for element in data.get("elements", []):
            pivot_values = element.get("pivotValues", [])
            pivot_urn = pivot_values[0] if pivot_values else ""
            pivot_id = pivot_urn.split(":")[-1] if pivot_urn else ""
            date_range = element.get("dateRange", {})
            row_date = _format_analytics_date(date_range.get("start", {}))
            base = {
                "date": row_date,
                "granularity": granularity,
                "impressions": element.get("impressions", 0),
                "clicks": element.get("clicks", 0),
                "spend": element.get("costInLocalCurrency", 0),
                "conversions": element.get("externalWebsiteConversions", 0),
                "video_views": element.get("videoViews", 0),
                "reactions": element.get("reactions", 0),
                "shares": element.get("shares", 0),
                "comments": element.get("comments", 0),
                "follows": element.get("follows", 0),
            }
            if pivot == "CAMPAIGN":
                yield {"campaign_id": pivot_id, **base}
            else:
                campaign_id = (creative_campaign_map or {}).get(pivot_id, "")
                yield {"creative_id": pivot_id, "campaign_id": campaign_id, **base}


def _format_date_field(epoch_ms: int | None) -> str:
    """Convert epoch milliseconds to ISO date string."""
    if not epoch_ms:
        return ""
    return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def _format_analytics_date(start: dict) -> str:
    """Convert a LinkedIn dateRange.start dict (year/month/day) to an ISO date string."""
    if not start:
        return ""
    try:
        return date(start["year"], start["month"], start["day"]).isoformat()
    except KeyError as e:
        raise UserException(f"Malformed date range in LinkedIn API response: {start}") from e
