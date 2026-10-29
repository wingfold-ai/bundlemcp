## MODIFIED Requirements

### Requirement: OPS-8 Logs
Every log record the process writes — structlog events and standard-library loggers such as uvicorn's alike — SHALL be
rendered as one structured line per event to the process's standard error stream, in the format chosen by
`BUNDLEMCP_LOG_FORMAT` (`json`, the default, or `text` for terminals), at the minimum level set by
`BUNDLEMCP_LOG_LEVEL`. Every line written while serving a request SHALL carry the request id, the client IP, and — once
resolved — the endpoint, the MCP session id and the caller (user id or API key id). Secrets, tokens, header values, and
tool arguments MUST never be logged. No debug prints in hot paths — enforced by ruff config (`T20`) and review. A record
logged with an exception SHALL carry that exception's type, message and stack frames in an `exception` field, in both
formats. It MUST NOT carry any frame's local variables, the input a validation error rejected, or the parameters of a
failed database statement.

#### Scenario: Library and application logs share the JSON format
- **GIVEN** the log format is `json` and the level `INFO`
- **WHEN** uvicorn's access logger and a structlog logger each emit a record
- **THEN** both lines are JSON objects carrying `logger`, `level`, `event` and `timestamp`

#### Scenario: Records below the level are dropped
- **GIVEN** the level is `INFO`
- **WHEN** a logger emits a `DEBUG` record
- **THEN** nothing is written for it

#### Scenario: Print statements are rejected
- **WHEN** library code contains a `print(...)` call
- **THEN** `uv run ruff check .` fails with a `T20` finding

#### Scenario: Request context on every line of a tool call
- **GIVEN** a client authenticated with API key `k1` calling a tool on endpoint `main` in session `s1`
- **WHEN** the call writes log lines (for example an upstream failure)
- **THEN** every one of those lines carries the same `request_id`, `endpoint` `main`, `session_id` `s1`, `api_key_id`
  of `k1` and `client_ip`
- **AND** none carries the key value

#### Scenario: Request id is returned to the client
- **WHEN** any HTTP request is served
- **THEN** the response carries an `X-Request-Id` header equal to the `request_id` on that request's log lines

#### Scenario: Context does not leak between requests
- **WHEN** two requests for different endpoints are served concurrently
- **THEN** each request's log lines carry only its own request id, endpoint and caller

#### Scenario: Unresolved fields are omitted
- **WHEN** a request is rejected before its credential is evaluated
- **THEN** its log lines carry `request_id` and `client_ip` but no caller field

#### Scenario: A logged exception carries its traceback
- **GIVEN** the log format is `json`
- **WHEN** code logs a warning with the exception it caught
- **THEN** the line is one JSON object whose `exception` field names the exception type, its message and the frames
  it passed through

#### Scenario: A traceback never shows local variables
- **GIVEN** the log format is `text` or `json`
- **WHEN** an exception is logged from a frame whose local variable holds a token
- **THEN** the token appears nowhere in the output

#### Scenario: Rejected input and statement parameters stay out of the log
- **WHEN** a validation error over a secret-bearing value, or a failed database statement whose parameters include a
  ciphertext, is logged with its exception
- **THEN** the line names the error and its location but contains neither the value nor the parameters
