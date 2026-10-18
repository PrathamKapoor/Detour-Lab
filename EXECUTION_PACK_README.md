# DETOUR LAB — Flash-Model Execution Pack

This pack is designed for a smaller coding model that tends to skip details when given one enormous assignment. You can use the single `MASTER_PROMPT.md` all at once if the agent handles long contexts, but for the most reliable execution use the **sequential gate prompts** below.

## Files

- `DETOUR_LAB_Final_PRD.md`: authoritative product baseline (R0/R1/P2, acceptance and invariants).
- `MASTER_PROMPT.md`: complete 6,000+ word implementation contract with exact engineering semantics and test gates.
- `prompts/00_BOOTSTRAP.md`: the first message to paste into your coding agent; it reads/reconciles the two files and starts.
- `prompts/01_GATE_0.md` through `prompts/08_GATE_7.md`: one gate at a time; don't run a later gate unless earlier tests pass.
- `prompts/09_RESUME_AND_AUDIT.md`: use whenever you start a fresh model session or worry it has drifted from the PRD.

## How to use

1. Open a coding agent with access to your intended local Git repository (or ask it to create the project folder). Put `MASTER_PROMPT.md` and `DETOUR_LAB_Final_PRD.md` into the repository root as guidance; do not claim they are there until you actually place them.
2. Paste `prompts/00_BOOTSTRAP.md` and let the agent inspect the repository. It MUST actually inspect and run commands, not just provide instructions.
3. Paste each gate prompt in order. Require concrete test output and Git status/commit verification before moving on.
4. For a new conversation/context window, paste `prompts/09_RESUME_AND_AUDIT.md` first. It reloads checkpoint files and tests before continuing.
5. R0 is gates 0–3; R1 is gates 4–7. Do not add R2 until full R1 evaluation is honest and green.

## Requirements that may require your decision

- Where to create the repository or which pre-existing repository to modify (unless the agent already has a definite working directory).
- Whether to grant GitHub remote access, push permission, deployment credentials, or a public project license. The agent cannot invent these.
- A legally applicable jurisdictional rulepack or real field-survey values. Until supplied, the app uses transparently synthetic demo rules and explicit unknowns rather than making compliance claims.
- Real city/study area and map-data rights if required for a non-synthetic demonstration. Use a self-contained schematic seed to prove R0 independently.

## Owner attribution

All new commits created by the coding agent, if any, must have author and committer `PrathamKapoor <prathamkapoor027@gmail.com>` under repository-local or per-commit settings only. No history rewriting or unauthorised pushing.

## Success criteria

A working, verified product: import/edit pedestrian graph → simulate closure for a phase and mobility profile → inspect Pass/Fail/Unknown/N/A and evidence → compare confirmed/potential reachability → propose bounded fix and revalidate → stress-test → export canonical JSON/PDF → replay. No static demo outputs, fake statistics or imagined safety certificates.
