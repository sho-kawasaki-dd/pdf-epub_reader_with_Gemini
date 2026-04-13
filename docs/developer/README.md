# Developer Documentation

This section explains how the application is structured and which diagrams should be used to understand or extend it.

## Supported Local Launch Paths

- Windows PowerShell wrapper: `.\gem-read_launch.ps1`
- Canonical module startup: `uv run python -m pdf_epub_reader`

## Read First

1. [docs/developer/architecture.md](docs/developer/architecture.md)
2. [docs/developer/runtime-flows.md](docs/developer/runtime-flows.md)
3. [docs/developer/testing.md](docs/developer/testing.md)

## Diagrams

1. [docs/developer/diagrams/system-overview.md](docs/developer/diagrams/system-overview.md)
2. [docs/developer/diagrams/layer-dependencies.md](docs/developer/diagrams/layer-dependencies.md)
3. [docs/developer/diagrams/open-file-sequence.md](docs/developer/diagrams/open-file-sequence.md)
4. [docs/developer/diagrams/selection-to-ai-sequence.md](docs/developer/diagrams/selection-to-ai-sequence.md)
5. [docs/developer/diagrams/cache-lifecycle.md](docs/developer/diagrams/cache-lifecycle.md)

## Documentation Goals

- Make the MVP boundaries explicit
- Make runtime flows easier to reason about
- Keep diagrams close to code so they can be updated with implementation changes
