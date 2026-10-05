# Persistent Telegram download progress

Approved direction: retain progress per Telegram account and chat in the existing
host-mounted data directory. Read history oldest first at startup and periodically
while connected, so both container downtime and short network gaps are covered.

SQLite stores the initial UTC date, last handled message ID/date, latest completed
scan time, and reserved download paths. Only successful downloads or intentional
extension skips advance progress. A failed download pauses the scan and is retried;
later messages cannot move the checkpoint past a failure. Telegram messages deleted
before recovery cannot be downloaded. Changing extensions does not replay old skips.

Write download intent before starting, then record that a partial file is complete
before renaming it. Recovery reuses the reserved path and recognizes a completed
rename even if checkpoint persistence was interrupted. One watcher uses each data
directory. A destination changed by a user does not trigger automatic redownload.

HISTORY_START_DATE accepts an ISO date or timestamp (UTC when no zone is given).
It applies only to a new account/chat checkpoint. Without it, tracking starts when
first enabled. For this installation the old log's last successful download was
2026-09-24 13:15:16 UTC; bootstrap from that instant. Old logs are not a complete
message ledger, so no claim is made to reconstruct earlier outages.

Verify persistence, offline arrivals, same-second messages, interrupted transfers,
rename/checkpoint crashes, failed retries, extension skips, chat isolation, shutdown,
and initial-date parsing using isolated files and a fake Telegram client.
