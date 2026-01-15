# Repository Guidelines

## Project Structure & Module Organization

- `dppg_reader.py` holds the GUI, TCP connection, protocol parsing, and export logic.
- `PROTOCOL.md` documents the reverse-engineered serial/TCP protocol details.
- `CLAUDE.md` is the user/ops guide with hardware setup and usage steps.
- `ppg_data_*.csv` and `ppg_data_*.json` are captured sample outputs; treat as sensitive.

## Build, Test, and Development Commands

- `python3 dppg_reader.py` starts the GUI and connects to the device via TCP.
- No build step is required; this is a single-file Python app using the standard library.

## Coding Style & Naming Conventions

- Use 4-space indentation (PEP 8-style) and snake_case for functions/variables.
- Class names use CapWords (e.g., `PPGBlock`, `DPPGReader`).
- Prefer short, descriptive docstrings for non-trivial classes and methods.
- Avoid adding new dependencies unless there is a clear benefit for portability.

## Testing Guidelines

- There is no automated test suite yet.
- When changing parsing or protocol logic, validate with sample data and a real device:
  - Load `ppg_data_*.csv`/`ppg_data_*.json` to confirm sample counts and labels.
  - Confirm the ACK behavior keeps the device "printer online".
- If you add tests, follow `test_*.py` naming and keep them runnable with `python -m unittest`.

## Commit & Pull Request Guidelines

- Commits use short, imperative summaries in sentence case (e.g., "Implement block parser...").
- Include details after a colon only when it improves clarity (e.g., "Initial commit: ...").
- PRs should describe the user-visible change, list any protocol assumptions, and link
  relevant issues or logs. Add screenshots for GUI changes.

## Security & Configuration Tips

- Default device settings are IP `192.168.0.234` and port `1100`; keep them configurable.
- Avoid committing real patient data; sanitize samples before sharing.
