---
name: service-outage
description: Investigates external API outages, HTTP 5xx failures, and outage duration using direct probes, runtime logs, independent monitors, and timestamped reports.
---

# External service outages

1. Trace the failing request to its actual upstream. Read the response body and
   headers, not just the status code. Record endpoint, status and observation time.
2. Compare the same request from the failing runtime and an independent client.
   If results differ, inspect credentials, proxies, DNS and request differences;
   distinguish local authentication failures from provider unavailability.
3. For outage news and timing, search Twitter/X or its mirrors first for provider
   announcements and timestamped user reports. Search the exact hostname and
   service, not just the provider's name. Then check provider notices, public outage
   histories (Downdetector, IsItDownRightNow, Down for Everyone or Just Me) and
   application logs. Render JavaScript-driven monitor results when needed.
4. Separate first observed failure, last observed failure, last known success and
   first observed recovery. A search crawl date, missing report, or a monitor's
   “UP” label does not establish API health or continuous uptime. Check whether
   an announcement concerns the same endpoint, region and incident.
5. Recheck the exact failing endpoint before reporting. Give confirmed evidence,
   the defensible time bounds, and what remains unknown; do not turn two sampled
   timestamps into an exact outage duration. If mirrors fail, switch evidence
   sources rather than treating absent search results as proof of no incident.
6. Inspect existing cache coverage before proposing new storage. Distinguish
   successful-response retention from caching errors, and cached-date availability
   from fresh data. Record durable findings in the relevant dependency wiki page.
