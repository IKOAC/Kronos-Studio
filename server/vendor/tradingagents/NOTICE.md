# TradingAgents research nodes

Source: https://github.com/TauricResearch/TradingAgents
Pinned commit: 1394a3f72aa4393e1a98f51b382434c4b4c2d972 (v0.6.0).
License: Apache-2.0; full upstream license included in LICENSE.

The bull and bear researchers retain upstream factory interfaces and debate
state transitions. Their prompts are shortened to qualitative interpretations
of the immutable snapshot, with absent sources explicitly marked. Their
context import points to this isolated snapshot-only helper.
The research manager retains the upstream debate/synthesis state interface but
uses a bounded qualitative research prompt instead of actionable ratings and
LangChain structured-output/fallback helpers. These are modified files.
The context helper includes only the four functions needed by those nodes,
with no data vendors, environment loading, identity lookup or portfolio tools.
Kronos invokes a single bull turn, a single bear response and manager synthesis
through its metered Groq adapter. The full upstream graph, data tools, memory,
trade/portfolio agents and CLI are not included in this research profile.
