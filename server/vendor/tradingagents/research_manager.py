"""Modified TradingAgents research manager for bounded qualitative synthesis; see NOTICE.md."""
from vendor.tradingagents.context import get_instrument_context_from_state


def create_research_manager(llm):
    def research_manager_node(state) -> dict:
        debate = state["investment_debate_state"]
        prompt = (
            "As the Research Manager, critically weigh the bull and bear evidence. "
            "Weigh the cases independently of which side spoke last. Describe what is "
            "supported, what remains conflicting, and the limits of this snapshot. "
            "Do not turn the debate into an order or trade recommendation.\n"
            + get_instrument_context_from_state(state)
            + "\nImmutable market evidence: " + state["market_report"]
            + "\nDebate history (arguments, not additional evidence): " + debate["history"]
        )
        investment_plan = llm.invoke(prompt).content
        return {
            "investment_debate_state": {**debate, "current_response": investment_plan},
            "investment_plan": investment_plan,
        }
    return research_manager_node
