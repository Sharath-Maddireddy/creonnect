# Creonnect AI Guardrails

This is a production analytics and AI intelligence backend.

All modifications must follow these rules:

1. Deterministic First
- All numeric scores must be computed deterministically.
- AI must never compute or influence numeric scoring.
- AI is used only for narrative explanation.

2. Minimal Refactoring
- Do not refactor unrelated files.
- Do not rename existing functions unless explicitly instructed.
- Do not change API contracts unless explicitly instructed.
- Keep diffs small and surgical.

3. Separation of Concerns
- services/signal_engine.py → deterministic math only.
- services/ai_post_analysis.py → AI narrative only.
- services/post_insights.py → orchestration only.
- Do not mix AI logic with scoring logic.

4. Safety Rules
- Never divide by zero.
- Guard against missing fields.
- Round floats consistently.
- Validate all AI JSON output.
- Never expose stack traces in API responses.

5. AI Constraints
- AI must only reference metrics provided.
- AI must not fabricate missing data.
- AI must not generate numeric scores.
