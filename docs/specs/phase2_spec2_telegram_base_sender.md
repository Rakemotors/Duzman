# Phase 2 Spec 2 — Telegram Base Sender

Version: 1.0
Status: implemented
Based on: Техническое задание v1.10 от 2026-05-25 (docs/TZ.md)
Reference: GitHub Issue #96

## 1. Context And Goal

Phase 2 Spec 2 adds an isolated Telegram base sender that can format a
`DispatchEvent` and send it through the Telegram Bot API using an injectable
async HTTP transport. The module is inert in this spec: no scheduler wiring, no
AlertGate integration, no database writes, no runtime entrypoint, no AI worker,
and no production deployment.

The goal is to provide the Telegram delivery building block that later specs
can compose with persistence and dispatch orchestration.

## 2. Scope

In scope:

- `TelegramSendResult`, the immutable bounded send result.
- `format_dispatch_event_for_telegram()`, a pure deterministic MarkdownV2
  formatter for `DispatchEvent`.
- `TelegramHttpClient`, an async single-purpose `sendMessage` client with an
  injectable `HttpTransport`.
- `TelegramBaseSender`, an orchestration layer that formats, sends, retries
  transient failures, and always returns `TelegramSendResult`.
- Settings fields for Telegram token, chat id, timeout, and enabled flag.
- Offline unit tests using fake transports and golden formatter fixtures.

Out of scope:

- Scheduler or runtime wiring.
- AlertGate or Pattern Engine changes.
- Database reads or writes to `alert_deliveries`.
- AI explanation creation or reply dispatch.
- Real Telegram network calls or real credentials.
- Multi-chat routing, inline buttons, message edits, or reply threading.

## 3. Contract

`TelegramSendResult` fields:

- `status`: one of `sent`, `failed`, or `skipped_disabled`.
- `telegram_message_id`: Telegram message id on success, otherwise `None`.
- `error_reason`: one of the bounded Spec 2 error reason constants, otherwise
  `None`.
- `attempts`: number of HTTP attempts made; disabled sends use `0`.

Allowed error reasons:

- `telegram_api_error`
- `transport_timeout`
- `transport_network_error`
- `unexpected_response_shape`
- `rate_limited_exhausted`

`TelegramHttpClient.send_message()` posts to Telegram `sendMessage` and returns
the parsed Telegram result dictionary on success. It raises sanitized
`TelegramApiError` or `TelegramTransportError` internally; callers such as
`TelegramBaseSender` convert those exceptions into bounded result values.

## 4. Safety Model

The bot token is stored as `SecretStr` in settings and is never included in
result values, repr output, exception strings, or test fixtures. The HTTP client
builds the token-bearing Telegram URL only inside `send_message()` and does not
store the full URL as object state.

The chat id is configuration data and is not included in error messages by the
client or sender. Tests use fake values only and fake transports only.

Telegram dispatch is disabled by default through `telegram_enabled = False`.
When enabled, settings require both `telegram_bot_token` and `telegram_chat_id`.
`telegram_timeout_ms` must be between 1000 and 30000 inclusive.

## 5. Retry Model

`TelegramBaseSender` defaults to one retry. It retries transient transport
errors, timeout errors, HTTP 5xx API errors, and HTTP 429 rate limits. It does
not retry permanent 4xx errors other than 429.

For 429 responses, the sender respects `Retry-After` when available and caps
the delay at five seconds. If the retry budget is exhausted after a 429, the
result error reason is `rate_limited_exhausted`.

The sender never raises for network or Telegram API failures. It returns
`status="failed"` with a bounded sanitized error reason.

## 6. Tests

Spec 2 tests live under `tests/dispatch/telegram/` and use no real network or
credentials.

Coverage includes:

- Golden formatter output with and without condition snapshots.
- `None` condition snapshots.
- MarkdownV2 escaping for event fields and condition rows.
- Snapshot truncation after the first 20 condition keys.
- Client success, 400, 403, 429, timeout, network failure, unexpected response
  shape, and token-safe repr/exception behavior.
- Sender success, transient retry success, retry exhaustion, permanent error,
  rate-limit exhaustion, disabled sends, and no token leakage in logs.

## 7. Future Tightening

Spec 2 keeps status and error reason values as strings with runtime validation.
Later specs may tighten these to `Literal[...]` or enums after persistence,
AI, and runtime wiring settle the full taxonomy.

Spec 5 is expected to compose this sender with the Spec 1 `Dispatcher` contract
and Spec 3 persistence. Until that wiring exists, the Telegram base sender is
inert and cannot send production alerts by itself.
