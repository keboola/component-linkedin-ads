"""LinkedIn Ads extractor component."""

import json
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import batched

from keboola.component.base import ComponentBase, sync_action
from keboola.component.dao import ColumnDefinition, TableDefinition
from keboola.component.exceptions import UserException
from keboola.component.sync_actions import SelectElement
from keboola.csvwriter import ElasticDictWriter
from keboola.utils import parse_datetime_interval

from configuration import Configuration
from linkedin_client import AccountsClient, AnalyticsClient, CampaignsClient, CreativesClient, LinkedInAdsClient


@dataclass
class _WriterRecord:
    writer: ElasticDictWriter
    table_def: TableDefinition
    primary_key: list[str]


class Component(ComponentBase):
    def __init__(self) -> None:
        super().__init__()
        self.cfg = Configuration(**self.configuration.parameters)
        if self.cfg.debug:
            logging.getLogger().setLevel(logging.DEBUG)
        oauth = self.configuration.oauth_credentials
        if not oauth:
            raise UserException("Missing OAuth credentials. Authorize the component via Keboola OAuth.")
        access_token = self._extract_access_token(oauth)
        if not access_token:
            raise UserException(
                "Missing OAuth access token. The stored credentials may be expired or invalid. "
                "Re-authorize the component via Keboola OAuth."
            )
        self._client = LinkedInAdsClient(access_token)
        self._writers: dict[str, _WriterRecord] = {}
        self._total_rows_written: int = 0
        self._campaign_ids_cache: list[str] | None = None
        self._creative_campaign_map_cache: dict[str, str] | None = None

    @sync_action("list_accounts")
    def list_accounts(self) -> list[SelectElement]:
        return [
            SelectElement(value=row["id"], label=f"{row['name']} ({row['id']})")
            for row in AccountsClient(self._client).list_all_accounts()
        ]

    def run(self) -> None:
        if not self.cfg.ad_account_id:
            raise UserException(
                "ad_account_id is required. Select an account from the dropdown or enter a numeric account ID."
            )
        state = self.get_state_file()
        start_date, end_date = self._determine_date_range(state, self.cfg.date_start, self.cfg.date_end)
        logging.info(f"Syncing account {self.cfg.ad_account_id} from {start_date} to {end_date}")

        self._sync_endpoint(self.cfg.endpoint, self.cfg.ad_account_id, start_date, end_date)

        self._flush_writers()
        if self._total_rows_written > 0:
            self.write_state_file({"last_run_date": end_date.isoformat()})

    def _sync_endpoint(self, endpoint: str, account_id: str, start_date: date, end_date: date) -> None:
        if endpoint == "accounts":
            self._write_rows("ad_accounts", AccountsClient(self._client).get_accounts(account_id), ["id"])

        elif endpoint == "campaigns":
            campaigns_client = CampaignsClient(self._client)
            self._write_rows("campaign_groups", campaigns_client.get_campaign_groups(account_id), ["id"])
            rows = list(campaigns_client.get_campaigns(account_id))
            # Populate ID cache so downstream endpoints (creatives, analytics) don't re-fetch
            if self._campaign_ids_cache is None:
                self._campaign_ids_cache = [row["id"] for row in rows]
            self._write_rows("campaigns", rows, ["id"])

        elif endpoint == "creatives":
            if self._creative_campaign_map_cache is None:
                self._creative_campaign_map_cache = {}
            for batch in batched(self._get_campaign_ids(account_id), 100):
                rows = list(CreativesClient(self._client).get_creatives(account_id, batch))
                for row in rows:
                    self._creative_campaign_map_cache[row["id"]] = row["campaign_id"]
                self._write_rows("creatives", rows, ["id"])

        elif endpoint == "analytics":
            analytics_client = AnalyticsClient(self._client)
            self._write_rows(
                "analytics_by_campaign",
                analytics_client.get_analytics(
                    account_id, "CAMPAIGN", start_date, end_date, self.cfg.analytics_granularity
                ),
                ["campaign_id", "date", "granularity"],
            )
            self._write_rows(
                "analytics_by_creative",
                analytics_client.get_analytics(
                    account_id,
                    "CREATIVE",
                    start_date,
                    end_date,
                    self.cfg.analytics_granularity,
                    creative_campaign_map=self._build_creative_campaign_map(account_id),
                ),
                ["creative_id", "campaign_id", "date", "granularity"],
            )

    def _get_campaign_ids(self, account_id: str) -> list[str]:
        """Fetch campaign IDs once per run and cache them."""
        if self._campaign_ids_cache is None:
            self._campaign_ids_cache = [row["id"] for row in CampaignsClient(self._client).get_campaigns(account_id)]
        return self._campaign_ids_cache

    def _build_creative_campaign_map(self, account_id: str) -> dict[str, str]:
        """Return creative_id → campaign_id mapping, reusing data from the creatives sync if already fetched."""
        if self._creative_campaign_map_cache is not None:
            return self._creative_campaign_map_cache
        self._creative_campaign_map_cache = {}
        for batch in batched(self._get_campaign_ids(account_id), 100):
            for creative in CreativesClient(self._client).get_creatives(account_id, batch):
                self._creative_campaign_map_cache[creative["id"]] = creative["campaign_id"]
        return self._creative_campaign_map_cache

    def _write_rows(self, table_name: str, rows, primary_key: list[str]) -> None:
        """Append rows to the named output table, creating the writer on first use."""
        written = 0
        for row in rows:
            if table_name not in self._writers:
                table_def = self.create_out_table_definition(f"{table_name}.csv", incremental=True)
                self._writers[table_name] = _WriterRecord(
                    writer=ElasticDictWriter(table_def.full_path, list(row.keys())),
                    table_def=table_def,
                    primary_key=primary_key,
                )
            self._writers[table_name].writer.writerow(row)
            written += 1
        self._total_rows_written += written
        if written:
            logging.info(f"Wrote {written} rows to {table_name}")
        else:
            logging.info(f"No rows returned for {table_name}")

    def _flush_writers(self) -> None:
        """Close all open writers and write their manifests."""
        for table_name, record in self._writers.items():
            record.writer.close()
            schema = {
                col: ColumnDefinition(primary_key=(col in record.primary_key)) for col in record.writer.fieldnames
            }
            table_def = self.create_out_table_definition(
                record.table_def.name,
                incremental=record.table_def.incremental,
                schema=schema,
            )
            self.write_manifest(table_def)

    @staticmethod
    def _determine_date_range(state: dict, date_start: str, date_end: str) -> tuple[date, date]:
        today = date.today()
        if date_start.strip().lower() == "last_run":
            if state and "last_run_date" in state:
                resolved_start = state["last_run_date"]
            else:
                resolved_start = (today - timedelta(days=365)).isoformat()
        else:
            resolved_start = date_start
        try:
            start_str, end_str = parse_datetime_interval(resolved_start, date_end, "%Y-%m-%d")
            return date.fromisoformat(start_str), date.fromisoformat(end_str)
        except (ValueError, TypeError) as e:
            raise UserException(f"Invalid date range ({resolved_start!r} – {date_end!r}): {e}") from e

    @staticmethod
    def _extract_access_token(oauth) -> str | None:
        """Extract access_token from OAuth credentials, handling both dict and JSON-string formats."""
        data = oauth.data
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                return None
        if isinstance(data, dict):
            return data.get("access_token")
        return None


if __name__ == "__main__":
    try:
        comp = Component()
        comp.execute_action()
    except UserException as exc:
        logging.exception(exc)
        exit(1)
    except Exception as exc:
        logging.exception(exc)
        exit(2)
