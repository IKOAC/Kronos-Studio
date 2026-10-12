# Modified for Kronos: bounded evidence-only prompt and local context import; upstream revision in NOTICE.md.
from vendor.tradingagents.context import (
    get_instrument_context_from_state,
    get_language_instruction,
    opponent_argument_or_opening,
    report_or_absent,
)


def create_bull_researcher(llm):
    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

        current_response = opponent_argument_or_opening(
            investment_debate_state.get("current_response", ""), "bear analyst"
        )
        market_research_report = report_or_absent(state["market_report"], "market")
        sentiment_report = report_or_absent(state["sentiment_report"], "sentiment")
        news_report = report_or_absent(state["news_report"], "news")
        fundamentals_report = report_or_absent(state["fundamentals_report"], "fundamentals")
        instrument_context = get_instrument_context_from_state(state)
        asset_type = state.get("asset_type", "stock")
        target_label = "stock" if asset_type == "stock" else "asset"
        fundamentals_label = (
            "Company fundamentals report"
            if asset_type == "stock"
            else "Asset fundamentals report (may be unavailable for crypto)"
        )

        prompt = f"""You are the Bull Researcher in a bounded market-evidence review.
Evaluate the favorable interpretations of the supplied market evidence. If bullish support is weak, say so; do not manufacture a bullish case.
Return a concise qualitative assessment in the required JSON fields. Use the exact
supplied evidence IDs. No digits in the summary or limitations; evidence IDs may
contain digits. Do not quote prices, indicator labels containing digits, or perform
arithmetic. Never infer news, growth, fundamentals or sentiment that were not supplied.

Resources available:
{instrument_context}
Immutable market evidence: {market_research_report}
Sentiment: {sentiment_report}
News: {news_report}
{fundamentals_label}: {fundamentals_report}
Debate history (interpretations, not new evidence): {history}
Last bear argument: {current_response}
""" + get_language_instruction()

        response = llm.invoke(prompt)

        argument = f"Bull Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node
