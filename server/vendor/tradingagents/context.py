"""Modified snapshot-only subset of TradingAgents context helpers; see NOTICE.md."""

def get_language_instruction() -> str:
    return ""


def get_instrument_context_from_state(state) -> str:
    return state["instrument_context"]


def opponent_argument_or_opening(text: str, opponent: str) -> str:
    text = (text or "").strip()
    return text or f"(The {opponent} has not spoken yet — open the debate with your own case.)"


def report_or_absent(text: str, source: str) -> str:
    text = (text or "").strip()
    return text or f"(No {source} report in this run: it is not available, not an empty finding.)"
