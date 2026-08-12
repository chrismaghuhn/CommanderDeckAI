# Data-foundation offline fixtures

These files are intentionally small and contain no external source dump. The E2E
workflow copies the response bytes into a temporary immutable raw snapshot, then
builds normalized, audit, quarantine, report, and task-specific dataset artifacts
under the temporary test root. The fixture config is parsed with the same strict
dataset settings model used by production code.
