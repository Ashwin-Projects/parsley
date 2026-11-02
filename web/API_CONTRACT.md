- POST /api/session -> {session_id}
- POST /api/compile {session_id, sentence, mode: "rules"|"llm"|"hybrid"} -> {
    status: "accepted"|"clarify"|"rejected"|"error",
    minilang?: string, understood?: string (V1 text),
    checks?: {v1:"ok"|"fail", v2:"ok"|"fail"|"skipped", v3:"ok"|"fail"|"skipped"},
    question?: {text, options: string[], kind},
    diagnostics: [{code, stage, message}], suggestion?: string,
    source?: "rules"|"llm", trace?: object }
- POST /api/answer {session_id, answer} -> same shape as compile
- GET /api/program?session_id= -> {minilang, statements: [{english, minilang}]}
- POST /api/run {session_id} -> {output: string[], variables: object, error?: string}
- POST /api/undo, POST /api/reset {session_id} -> {ok}
- GET /api/health -> {version, llm_configured: bool, provider?: string, model?: string}

Backend decisions:
- `question.kind: "derived_value"` asks for an explicit Yes / No answer via `/api/answer`; No declines without appending a statement.
- W510–W514 are non-blocking LLM diagnostics. W513 marks accepted LLM readings and asks the user to check the reading.
- The required health response has no mode field. The UI labels the selected compile mode as `Requested`. An optional `mode: "rules"|"llm"|"hybrid"` extension, when supplied by the backend, is displayed as `Backend` mode instead.
- HTTP 429 may include `Retry-After` seconds or an HTTP date. The client shows retry guidance and never automatically replays mutations. HTTP fetches have a 30-second deadline.
