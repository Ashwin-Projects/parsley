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
