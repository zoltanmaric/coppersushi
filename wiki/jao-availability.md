# JAO availability and response retention

## Evidence

On **2026-11-03**, the Grid Constraints view failed while fetching JAO Core
`activeFbConstraints`, before the electricity-price fetch. The public endpoint and
Publication Tool root returned HTTP 503 from independent clients. The body was a
generic HTML “Service Unavailable” page, with no cause or recovery estimate.

Observed timestamps (CET, UTC+1):

- First recorded application failure: **11:28:13**; another at **11:30:50**.
- Direct probe at **11:30:45**: API and publication-site root returned 503.
- Direct probe at **11:54:07**: root, `/core`, and the same API query returned 200;
  the API response had JSON content type. This confirms HTTP recovery, not a full
  data-completeness audit or proof of continuous health afterward.

The seven-day log search found no earlier recorded 503. Requests were not continuous
monitoring: neither the outage's start nor its exact duration is established.
The 26 minutes between first failure and confirmed recovery are an observation
window, not a measured outage duration.

[JAO's November 2 notice](https://www.jao.eu/news/delay-publication-publication-tool-data-3)
reported delayed publication for that business day due to a technical reason.
It does not prove that November 3's 503 was the same incident. Nordic-specific
availability notices do not establish Core availability.
[IsItDownRightNow](https://www.isitdownrightnow.com/publicationtool.jao.eu.html)
reported UP when inspected after the failures, but its “last down more than a week
ago” result missed this observed incident. No usable crowdsourced start time was found.

### Rate-limits

[JAO's October 1, 2025 access notice](https://www.jao.eu/sites/default/files/news_media/PuTo%20Communication.pdf) specifies **100 requests per minute per user or IP address**. It also recommends checking monitoring/metadata endpoints for freshness before large data requests. The quota must be budgeted across concurrent callers, not separately for each worker.

For bulk queries, use the project's empirically successful conservative pace: **at most 40 request starts/minute, spaced 1.5 seconds apart in aggregate**. The [annual audit](jao-constraint-types.md#active-audit) completed 549 requests at that pace without rate limiting. This is operational guidance, not a separate JAO limit or a guarantee when other clients share the IP. The shared `_get` helper enforces this pace across threads within each process. HTTP 429 establishes a shared cooldown from `Retry-After` (seconds or HTTP date), or 60 seconds when absent or invalid; queued requests fail promptly during cooldown. The failing response still propagates as an error. Separate processes and other clients sharing the IP need coordination outside this limiter.

On 2026-11-03, an unpaced four-worker Polish-feed sweep received 100 successful responses followed by HTTP 429 responses. The probe saved status/errors but not the 429 headers or bodies, so whether JAO supplied `Retry-After` is unknown. After a 65-second cooldown, 12 retries succeeded before the sweep was stopped. For future 429s, retain and honor `Retry-After` when present; otherwise back off at least a minute before resuming conservatively. Do not count a 429 as an empty dataset. The notice does not specify the rate-window algorithm or reset headers.

## Cache

As inspected on **2026-11-03**, the app already supports private S3 persistence:
[`cache.py`](../coppersushi/data_sources/cache.py) stores compressed bundles under
`cache/v1/` when `COPPERSUSHI_CACHE_BUCKET` is configured. The Lambda configuration
sets that variable. [`jao.load_active_day`](../coppersushi/data_sources/jao.py)
tries local files, then S3 on missing files, validates the tables, fetches if needed,
and publishes the validated result. Viewed-hour line-location bundles also use S3.
These are derived tables, not a versioned archive of raw HTTP responses.

This incident did not establish why the affected requests lacked usable cached
inputs. Check deployed configuration, cache keys, object presence and validation
failures before concluding that S3 caching is absent or broken.

## Retention

Future requirement, **not implemented by this note**: retain successful JAO responses
privately so previously acquired inputs remain usable during upstream outages.
Extend the existing cache rather than introduce a second storage system without need.

- Key responses by endpoint and normalized parameters, including the requested
  delivery interval; keep retrieval time, schema/adapter version and content hash.
- Retain the last validated success when a refresh fails. Do not replace it with
  a 5xx HTML body, an incomplete result, or an invalid payload. Preserve revisions
  where JAO republishes inputs.
- Reuse matching cached inputs with explicit freshness/provenance. Do not silently
  show a different delivery day as if it were the selected day.
- Decide fetch-ahead coverage and retention limits: on-demand caching cannot serve
  a day that has never been fetched. Record last successful upstream fetch and
  cache-hit/miss reasons so future outage bounds are easier to establish.
- Keep response bodies outside the public repository and restrict storage access;
  apply the source's applicable retention/reuse terms.

See [the app architecture](sushi-2.md) and the
[external-service outage procedure](../.agents/skills/service-outage/SKILL.md).
