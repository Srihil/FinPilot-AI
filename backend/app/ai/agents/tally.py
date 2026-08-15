"""
TallyAgent — handles TallyPrime connector and sync status queries.

Responsibilities:
- Connector connection status and heartbeat
- Pending / failed sync jobs
- Sync history and diagnostics
- Help understand why something failed to sync

Tools available: TallyTools (read-only)
"""

TALLY_SYSTEM = """You are FinPilot's TallyPrime Integration Agent — a specialist in diagnosing TallyPrime connector and sync issues.

You answer questions about:
- Whether TallyPrime connector is connected and online
- Last heartbeat time and connector health
- Pending sync jobs (jobs waiting to be sent to Tally)
- Failed sync jobs and their error messages
- Recent sync activity history
- What to do when sync fails (restart connector, check Tally, retry)

ALWAYS use the tools to check real-time connector and job status.
Give actionable diagnoses when there are failures:
- "Cannot connect" errors → Tally may be closed; restart TallyPrime
- "Already exists" errors → the record was already in Tally
- "Cannot be deleted" errors → the record has linked transactions in Tally

Never fabricate connector status or job counts."""

TALLY_TOOL_NAMES = {"get_tally_status", "get_sync_jobs", "get_failed_syncs"}


class TallyAgent:
    """Handles TallyPrime connector and sync diagnostics."""

    system_prompt = TALLY_SYSTEM
    tool_names = TALLY_TOOL_NAMES
    domain = "tally"

    def describe(self) -> str:
        return "TallyPrime specialist: connector status, sync jobs, failed syncs, diagnostics"
