# Frozen held-out paraphrases

`paraphrases.json`: 15 meaning groups, 4 phrasings each (60 inputs). Each group has
`setup` English, its `setup_minilang`, one canonical `expected_minilang`, and four uniquely
identified `paraphrases`. Run each member in a **fresh session**, after its setup. The final
setup declaration determines the reference-stack top. Never share a mutated session between
members of a group.

These are target meanings, not a claim that the current constrained-English front end
accepts every phrase. Natural but unsupported wording is intentional. Record rejection,
clarification and wrong translation as separate outcomes. For semantic paraphrase accuracy,
compare the resulting AST to the gold AST; for exact match compare canonical MiniLang. Do
not count four equally wrong outputs as a correct paraphrase group. Also report the plan's
raw all-members-same-AST consistency separately if required.

Written by the AI-assisted Parser/Verifier contributor from the project plan and language
specification, **before inspecting patterns.py or running these inputs through NLP**. The
specification and development fixtures had been read. This is not an independent human
benchmark; a teammate should review intended equivalence before a final reported study.
No NLP metrics have been generated or used to tune the implementation on these inputs.

The SHA-256 in `paraphrases.sha256` freezes the exact UTF-8 JSON bytes. Gold corrections
must be documented and versioned, never silently made to improve a score.

```
python scripts/validate_paraphrases.py
```

The validator verifies the freeze, schema, unique IDs/text, separation from development
fixtures, and canonical/syntactically/semantically/execution-valid gold programs. It does
not prove that the English annotations are correct and does not score the English front end.
The Evaluation owner can adapt this explicit schema into `eval/dataset.py`; that loader and
full evaluation are outside this assignment.
