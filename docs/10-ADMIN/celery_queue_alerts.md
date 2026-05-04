# Celery Queue Alerts

The system monitors Redis-backed Celery queues from the maintenance worker and sends throttled email alerts to active users with the `admin` role when queue processing appears stuck.

## What Is Checked

- Redis queue depth for `zip_ocr`, `pii_detection`, `metadata`, `thumbnails`, `maintenance`, `exports`, `s3_sync`, and `default`.
- Active ZIP upload jobs whose queued or processing items are older than the stale threshold.
- Live queue health on `/admin/status` under **Celery Queues** and **Celery Queue Health**.

## Alert Delivery

The scheduled task is `celery_tasks.tasks.maintenance_tasks.check_celery_queues_task`.

Default schedule: every 300 seconds, routed to the `maintenance` queue.

Recipients: active users with the `admin` role and a configured email address.

Alerts are throttled with the `app_settings` key `celery_queue_alert_last_sent_at` so a persistent backlog does not send repeated emails every schedule tick.

## Configuration

Environment variables:

| Variable | Default | Purpose |
| --- | ---: | --- |
| `CELERY_QUEUE_ALERT_ENABLED` | `true` | Enable or disable email alert delivery. |
| `CELERY_QUEUE_MONITOR_INTERVAL_SECONDS` | `300` | Celery Beat interval; minimum is 60 seconds. |
| `CELERY_QUEUE_ALERT_COOLDOWN_MINUTES` | `60` | Minimum time between alert emails. |
| `CELERY_QUEUE_STALE_ZIP_JOB_MINUTES` | `30` | Active ZIP job item age before it is considered stale. |
| `CELERY_QUEUE_<QUEUE>_WARNING` | queue-specific | Queue depth warning threshold. |
| `CELERY_QUEUE_<QUEUE>_CRITICAL` | queue-specific | Queue depth critical threshold. |

Queue threshold variable examples:

```bash
CELERY_QUEUE_ZIP_OCR_WARNING=25
CELERY_QUEUE_ZIP_OCR_CRITICAL=100
CELERY_QUEUE_METADATA_WARNING=50
CELERY_QUEUE_METADATA_CRITICAL=200
```

## Operational Notes

- If `zip_ocr` grows while `thumbnails` remains low, the OCR/ZIP worker is the likely bottleneck.
- If `metadata` or `pii_detection` grows, image post-processing is lagging even if ZIP extraction is active.
- If alerts do not arrive, verify `/admin/email-settings` has an active SMTP configuration and at least one active admin has an email address.
