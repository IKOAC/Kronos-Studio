# Kronos Studio — UI redesign review handoff

## Scope and status
- Workstream: frontend-only design preview. No changes to forecasting APIs, backend inference, Groq integration, or trading capabilities.
- Local development branch: `design/bold-typography-terminal`, based on `feature/three-model-confidence`.
- Review URLs on this Mac: http://localhost:3000/ and http://localhost:3000/saved-results.
- Screenshot previews on user's Desktop: `Kronos-2.0-Desktop.png`, `Kronos-2.0-Mobile.png`, `Kronos-2.0-Archive.png`, `Kronos-2.0-Archive-Mobile.png`.
- **Do not push, merge, or begin feature additions until user has reviewed the design.**

## User-supplied visual specification
"Bold Typography Design System" from user's pasted text. Treat its principles as authoritative:
- Editorial poster typography / Inter Tight large headings / Inter body / JetBrains Mono labels.
- `#0A0A0A` near-black background; `#FAFAFA` foreground; sparse vermillion `#FF3D00` accent.
- Sharp corners, thin border lines, underline interactions, fast decisive motion, no ornamental drop shadows.
- Negative space and asymmetric 7/5-ish terminal workspace; large heading reserved for editorial framing. Charts and dense technical values prioritize legibility and accuracy.
- Responsive mobile, accessible focus, reduced-motion support.

## Preserved functionality
- Six forecasting models: Kronos Mini, Small, Base; Chronos-2; TimesFM 2.5; FinCast.
- Single and batch forecast modes, model selection/custom model IDs, dataset/CSV selectors, sampling parameters.
- Price charts with live Binance overlay and volume controls, saved results, downloads, model comparison scores.
- No change to model forecasts, endpoints, position calculations, investment decisions or trades.

## Test record
- TypeScript (`npx tsc --noEmit`) and ESLint passed.
- Next.js production build passed including `/`, `/saved-results`, and `/icon.svg`.
- Chrome 1440px desktop and 390px mobile full-page captures both routes: HTTP 200, no horizontal overflow, proper Inter Tight typography.
- 6-model list loaded, checkbox selection tested, batch tab tested with genuine browser pointer click, saved results chart renders and archive selection works.
- API backend on port 8000 and Next frontend port 3000 remain accessible.
- No Groq credentials added anywhere in repository.

## Deferred Groq + quotas — important
- User wants Groq integration LATER, after UI design reviewed.
- Groq GPT-OSS 120B benchmark passed tool-calling and basic arithmetic tests. No Groq API calls performed during redesign.
- Existing API key lives **privately outside the repo** on the user's Mac and must NEVER be embedded in frontend code, committed, printed, or exposed to client requests.
- Local 5%-milestone quota monitor exists outside repo in a private user configuration area; hourly quota-watch automation was created in ChatGPT.
- Every future Groq API request must go through the local usage recorder (or an equivalent integrated quota logging layer) to measure daily token and request usage and issue alerts at each newly crossed 5% threshold. Respect Groq headers and time-based reset.
- Previous benchmark (not current calendar day unless dates coincide): 3,211 recorded tokens / 200,000 assumed daily allowance (1.61%) and 8 requests out of 1,000. No daily availability guarantee.
- Planned order, only after approval: deterministic Python financial calculations -> Groq AI explanation/validation layer -> TradingAgents integration -> backtesting / paper testing.
- GitHub privacy work was explicitly deferred; existing public fork and open PR #1 unchanged.

## Review first
User should evaluate layout, typography, density, chart interactions, settings ergonomics, and saved research on both desktop and phone. Fix requested design issues before any new feature development.
