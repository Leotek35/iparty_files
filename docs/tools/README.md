# Page generators

The system reference and the sprint board are rendered from Python models so the
diagram, the registers and the board never drift from one source.

| Source model | Generator | Outputs |
|---|---|---|
| `docs/architecture_model.py` — every system, its validation, cross-inspections, failure modes, triage paths | `python docs/tools/build_system_reference.py` | `docs/ARCHITECTURE.md`, `docs/architecture.json`, `docs/tools/out/system-reference.html` (the "iParty System Reference" artifact) |
| `docs/sprints/s0_model.py` — Sprint 0 cards with specs, acceptance tests, QA, DoD, references | `python docs/tools/build_sprint_board.py` | `docs/sprints/S0.md`, `docs/tools/out/s0-kanban.html` (the "Sprint 0 Board" artifact), `docs/tools/out/s0_seed.json` (board database seed) |

Rules: edit the model, run the generator, commit the generated Markdown/JSON (the
HTML under `docs/tools/out/` is ignored; it is published as an artifact). After
every incident, add its symptom, touch points and logs to the model and
regenerate; after every sprint, copy `s0_model.py` to the next sprint's model.
