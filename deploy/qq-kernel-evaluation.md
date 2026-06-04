# QQ Kernel Evaluation

Updated: 2026-06-04

## Recommendation

Keep the current NapCatQQ runtime for now. The account just hit risk controls, so switching login shape immediately is higher risk than reducing message rate and stabilizing behavior.

If a replacement is needed later, test in this order during a planned downtime:

1. LLOneBot / LuckyLilliaBot
2. Lagrange.Core / Lagrange.OneBot
3. OpenShamrock only if an Android device or emulator path is explicitly required

Do not use go-cqhttp for this deployment.

## Current Runtime: NapCatQQ

Pros:

- Active NTQQ-based OneBot implementation.
- Rich OneBot 11 API surface and plugin support.
- Already deployed and connected to Sumika.
- Text, image sending, custom face import, and reverse WebSocket are working.

Observed limits:

- Current Linux QQ kernel rejected avatar update.
- Current kernel rejected active friend-add attempts for the tested target.

Decision:

- Keep it as the production kernel.
- Do not retry bulk friend/profile operations while the account is warm.
- Use GUI approval and slow outbound pacing.

## Candidate: LLOneBot / LuckyLilliaBot

Pros:

- Supports OneBot 11, Satori, and Milky.
- Recent releases and active repository state as of this review.
- Good first migration candidate because the agent already speaks OneBot.

Risks:

- Still an unofficial QQ integration path.
- Migration requires a planned outage and fresh login flow.
- Unknown whether avatar/friend-add behavior is better than current NapCat without testing.

Decision:

- Best next candidate if NapCat remains blocked on required features.

## Candidate: Lagrange.Core / Lagrange.OneBot

Pros:

- Pure C# NTQQ protocol implementation.
- Provides Lagrange.OneBot.
- Server-native and headless-friendly.

Risks:

- Pure protocol implementations may have different login/signature compatibility risk.
- Less aligned with "normal client runtime" than NTQQ-plugin style deployments.

Decision:

- Good staging candidate for headless reliability, not the immediate production switch.

## Candidate: OpenShamrock

Pros:

- Android QQ + Xposed/LSPosed approach can be closer to mobile-client behavior.
- OneBot-compatible.

Risks:

- Repository metadata shows archived/stopped-maintenance state.
- Requires Android device/emulator plus Xposed/LSPosed/LSPatch style environment.
- More operational moving parts and higher maintenance cost.

Decision:

- Not recommended for this ECS v1.

## Candidate: go-cqhttp

Decision:

- Not recommended. It is historically important, but current QQ bot deployments should prefer maintained NTQQ-era alternatives.

## Sources

- NapCatQQ: https://github.com/NapNeko/NapCatQQ
- LLOneBot / LuckyLilliaBot: https://github.com/LLOneBot/LuckyLilliaBot
- Lagrange.Core: https://github.com/LagrangeDev/Lagrange.Core
- OpenShamrock metadata: https://awesome.ecosyste.ms/projects/github.com%2Fwhitechi73%2Fopenshamrock
- go-cqhttp migration discussion: https://github.com/Mrs4s/go-cqhttp/issues/2471
