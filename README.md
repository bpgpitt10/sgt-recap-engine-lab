# SGT Recap Engine Lab

Experimental, read-only automation lab for discovering Simulator Golf Tour events before we touch the production High Loft / Low Standards site.

## Current milestone

Given an SGT tour ID, fetch the public tour events feed and classify the events SGT itself labels as **ACTIVE EVENTS** and **PAST EVENTS**.

Test tour: `2370` (`OG Play`).

The first success condition is simple: GitHub Actions can fetch Tour 2370 without a browser session and correctly identify tournament IDs, course names, dates, and completed winners.

## Run locally

```bash
python -m pip install -r requirements.txt
python src/discover.py
```

Write the normalized response to a local JSON file:

```bash
python src/discover.py --write data/discovered-events.json
```

## Safety

This repo is deliberately isolated from `bpgpitt10/high-loft-low-standards`. Nothing here publishes or modifies the production league site.
