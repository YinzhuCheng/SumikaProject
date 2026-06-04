# Codex Preferences

- Preserve experiment artifacts by default. Do not clean intermediate files, caches, logs, raw LLM request payloads, raw LLM responses, parsed outputs, or validation reports unless explicitly asked and target paths are named.
- For grading/OCR/LLM experiments, save enough raw call records to reproduce the result, with secrets removed. Never save API keys, platform tokens, cookies, or authorization headers.
- Do not automatically write grading results back to external platforms unless explicitly approved.

