import logging
from typing import Literal

from keboola.component.exceptions import UserException
from pydantic import BaseModel, ValidationError, field_validator


class Configuration(BaseModel):
    """Merged root + row configuration. The platform delivers all parameters as one flat dict."""

    debug: bool = False
    ad_account_id: str = ""
    endpoint: Literal["accounts", "campaigns", "creatives", "analytics"] = "analytics"
    analytics_granularity: Literal["DAILY", "MONTHLY", "ALL_TIME"] = "DAILY"
    date_start: str = "last_run"
    date_end: str = "today"

    def __init__(self, **data):
        try:
            super().__init__(**data)
        except ValidationError as e:
            msgs = [f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()]
            raise UserException(f"Configuration error: {', '.join(msgs)}") from e
        if self.debug:
            logging.debug("Component will run in Debug mode")

    @field_validator("ad_account_id")
    @classmethod
    def strip_urn_prefix(cls, v: str) -> str:
        """Accept both raw numeric ID and full URN; always store raw numeric ID."""
        if v.startswith("urn:li:sponsoredAccount:"):
            return v.split(":")[-1]
        return v

    @field_validator("date_start")
    @classmethod
    def validate_date_start(cls, v: str) -> str:
        if v.strip().lower() == "last_run":
            return v
        import dateparser
        if dateparser.parse(v) is None:
            raise ValueError(
                f"Invalid date_start: {v!r}. Use 'last_run', 'today', '5 days ago', '1 month ago', or 'YYYY-MM-DD'."
            )
        return v

    @field_validator("date_end")
    @classmethod
    def validate_date_end(cls, v: str) -> str:
        import dateparser
        if dateparser.parse(v) is None:
            raise ValueError(
                f"Invalid date_end: {v!r}. Use 'today', '1 day ago', '1 month ago', or 'YYYY-MM-DD'."
            )
        return v
