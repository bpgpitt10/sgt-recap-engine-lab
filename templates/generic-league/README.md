# Generic SGT league site starter

A league site repository only needs the generated site plus these two source files:

- `league.json` — league/tour/branding configuration.
- `.github/workflows/league-auto.yml` — copy from `templates/generic-league/league-auto.yml`.

The workflow checks out `bpgpitt10/sgt-recap-engine-lab` as the shared engine. The league repository owns its own deterministic history, AI checkpoints, published-event state, generated HTML, and recap archive.

## Required setup

1. Copy `templates/generic-league/league.json` to the new repository root and set:
   - `tourId`
   - `tourName`
   - `leagueId`
   - `site.title`
   - `site.brand`
   - `site.baseUrl` after the Pages URL is known.
2. Copy the workflow to `.github/workflows/league-auto.yml`.
3. Add repository secret `OPENAI_API_KEY`.
4. Optional: add `DISCORD_WEBHOOK_URL`.
5. Enable GitHub Pages from the repository's `main` branch/root.

## First run

With no `.automation/published-events.json`, every currently completed SGT event is treated as backlog. The workflow processes missing event IDs oldest-first, checkpoints validated AI batches, renders the complete site, and marks those IDs published only in the final validated site commit.

## Later runs

The six-hour schedule computes:

`completed event IDs - published event IDs = publication queue`

This prevents a failed event from being skipped if another tournament completes before the failure is recovered.

## Secrets and cost

The site owner supplies their own OpenAI API key. The workflow uses GPT-5.4 mini as primary and GPT-5.6 Luna as emergency fallback. Discord is optional.
