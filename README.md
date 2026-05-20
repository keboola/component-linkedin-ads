LinkedIn Ads Extractor
======================

The LinkedIn Ads extractor pulls advertising data from your LinkedIn Ads accounts into Keboola. It uses the LinkedIn Marketing API to extract accounts, campaigns, creatives, and analytics, and supports configurable time granularity and date ranges for analytics syncs.

**Table of Contents:**

[TOC]

Prerequisites
=============

- A LinkedIn account with access to one or more LinkedIn Ads accounts.
- OAuth authorization via Keboola Connection. The component uses the official LinkedIn Marketing API (`r_ads`, `r_ads_reporting`).

Features
========

| **Feature**             | **Description**                                                       |
|-------------------------|-----------------------------------------------------------------------|
| Generic UI Form         | Dynamic UI form for easy configuration.                               |
| Row-Based Configuration | Allows running multiple endpoints/accounts within a single component. |
| OAuth                   | OAuth authentication enabled.                                         |
| Incremental Loading     | Output tables are loaded incrementally with primary keys.             |
| Backfill Mode           | Use `last_run` to resume analytics syncs from the last successful run.|
| Date Range Filter       | Specify the date range for analytics extraction.                      |

Supported Endpoints
===================

- **Accounts** – metadata of the configured ad account.
- **Campaigns** – campaign groups and campaigns under the account.
- **Creatives** – creatives belonging to campaigns under the account.
- **Analytics** – campaign- and creative-level performance metrics (`analytics_by_campaign`, `analytics_by_creative`) with `DAILY`, `MONTHLY`, or `ALL_TIME` granularity.

If you need additional endpoints, please submit your request to
[ideas.keboola.com](https://ideas.keboola.com/).

Configuration
=============

Ad Account
----------
Select your LinkedIn Ads account from the dropdown after authorizing, or enter the numeric account ID directly.

Endpoint
--------
Choose which resource to extract: `accounts`, `campaigns`, `creatives`, or `analytics`.

Analytics Granularity
---------------------
For the `analytics` endpoint, select the time granularity: `DAILY`, `MONTHLY`, or `ALL_TIME`.

Date Start / Date End
---------------------
For the `analytics` endpoint, specify the sync range. Both fields accept any `dateparser` expression (e.g. `today`, `7 days ago`, `1 month ago`) or an absolute date (`YYYY-MM-DD`). Use `last_run` as `date_start` to continue from the last successful run (falls back to 365 days ago on the first run).

Output
======

Output tables are loaded incrementally and use the following primary keys:

| **Table**                | **Primary key**                                |
|--------------------------|------------------------------------------------|
| `ad_accounts`            | `id`                                           |
| `campaign_groups`        | `id`                                           |
| `campaigns`              | `id`                                           |
| `creatives`              | `id`                                           |
| `analytics_by_campaign`  | `campaign_id`, `date`, `granularity`           |
| `analytics_by_creative`  | `creative_id`, `campaign_id`, `date`, `granularity` |

Development
-----------

To customize the local data folder path, replace the `CUSTOM_FOLDER` placeholder with your desired path in the `docker-compose.yml` file:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    volumes:
      - ./:/code
      - ./CUSTOM_FOLDER:/data
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Clone this repository, initialize the workspace, and run the component using the following
commands:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
git clone https://github.com/keboola/component-linkedin-ads component-linkedin-ads
cd component-linkedin-ads
docker-compose build
docker-compose run --rm dev
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Run the test suite and perform lint checks using this command:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
docker-compose run --rm test
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Integration
===========

For details about deployment and integration with Keboola, refer to the
[deployment section of the developer
documentation](https://developers.keboola.com/extend/component/deployment/).
