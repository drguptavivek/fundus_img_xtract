# Home Charts Cache Plan

## Objective
Add Redis-backed caching for the Home page charts/analytics to reduce repeated heavy queries while keeping rate-limit keys isolated.

## Approach
- Reuse existing Redis instance via Flask-Caching (`RedisCache`) with a dedicated key prefix (`home:charts:`) and short TTL (e.g., 5–15 minutes) to balance freshness and load reduction.
- Serialize chart payloads to JSON-safe structures only (no ORM instances); guard against empty/None data.
- Invalidate or bypass cache on error; log cache hits/misses for observability (lightweight).
- Keep rate-limit keys safe by avoiding destructive Redis commands and using a separate prefix.

## Steps
1) Add a small Redis cache helper (get/set with prefix + TTL, safe JSON serialization).
2) Wrap home chart query assembly in a function that first checks cache, then computes and stores on miss.
3) Ensure homepage route returns cached data and handles Redis unavailability gracefully.
4) Add minimal tests or a manual verification note (hit/miss behavior, data correctness, TTL respected).
5) Document cache keys/TTL in code comments for future tuning.
