
<h1 align="center">Geraldo Grell</h1>

<p align="center">
  <code>software engineer</code> ·
  <code>backend &amp; infrastructure</code> ·
  <code>new york, ny</code> ·
  <code>open to relocation</code>
</p>

<p align="center">
  I build ingestion pipelines and the infrastructure underneath them.<br>
  Scheduled jobs, append-only stores, and the Kubernetes they run on.
</p>

<p align="center">
  <a href="mailto:FILL_EMAIL@example.com"><img alt="Email" src="https://img.shields.io/badge/email-me-0b0f14?style=flat-square&labelColor=0b0f14&color=3fb950"></a>
  <a href="https://www.linkedin.com/in/geraldo-grell/"><img alt="LinkedIn" src="https://img.shields.io/badge/linkedin-geraldo--grell-0b0f14?style=flat-square&labelColor=0b0f14&color=58a6ff"></a>
  <a href="FILL_RESUME_URL"><img alt="Resume" src="https://img.shields.io/badge/resume-pdf-0b0f14?style=flat-square&labelColor=0b0f14&color=8b949e"></a>
</p>

<p align="center"><sub><b>Status:</b> open to software engineering roles — backend, platform, data infrastructure.</sub></p>

---

## Control plane

Things I run, not things I finished once. Status and last-run times are written by
[`status.yml`](.github/workflows/status.yml), which polls each repo's latest workflow run every six hours
and rewrites the block below. If a row says `failing`, it is actually failing.

<!-- STATUS:START -->
| service | what it does | stack | status |
| :--- | :--- | :--- | :--- |
| [**edgar-instrument**](FILL_REPO_URL) | Ingests SEC EDGAR filings on a schedule; scores an investment-thesis ledger with Brier scores against realized outcomes | `python` `postgres` `actions` | `awaiting first run` |
| [**open-docket**](FILL_REPO_URL) | Pulls federal court filings from the CourtListener API into an append-only JSONL store | `python` `courtlistener` `actions` | `awaiting first run` |
| [**uma**](FILL_REPO_URL) | Music discovery over pgvector embeddings, driven by pairwise choices written to an append-only table | `typescript` `postgres` `pgvector` | `awaiting first run` |
| [**hire-signal**](FILL_REPO_URL) | Application pipeline and triage board tracking 450 companies — status, dedup, next action | `typescript` `node` `postgres` | `awaiting first run` |
<!-- STATUS:END -->

<sub>Last refreshed: <!-- UPDATED:START -->never<!-- UPDATED:END --></sub>

---

## Shipped

Append-only. Newest first. Nothing gets edited out — same rule as the stores underneath the services above.

```
FILL_DATE  uma          evaluation harness — taste prediction at 66–80% (FILL: n, baseline)
FILL_DATE  hire-signal  triage board shipped; 450 companies under tracking
FILL_DATE  open-docket  CourtListener ingestion running on an Actions schedule
FILL_DATE  edgar-instrument  Brier-scored thesis ledger wired to realized outcomes
```

---

## Stack

| | |
| :--- | :--- |
| **Languages** | `TypeScript` `Python` `SQL` `Bash` |
| **Infrastructure** | `AWS EKS` `Kubernetes` `Helm` `Terraform` `ArgoCD` `Docker` `GitHub Actions` `Linux` |
| **Data** | `PostgreSQL` `pgvector` |
| **Web** | `Node.js` `Express` `React / Next.js` |

<sub>Listed only where I would survive a 45-minute interview. Things I have touched but would not claim are not here.</sub>

---

<details>
<summary><b>The longer version</b></summary>

<br>

I came to software sideways. Physics concentration at Manhattan University, then a CS degree at WGU,
with a few years of unglamorous operations work in between — a bank branch running a core banking platform,
a residential facility where the life-safety system going down was a real problem and not a page in a runbook.

That background is why the work above looks the way it does. I am less interested in apps than in the thing
that has to keep running on Tuesday at 3 a.m. with nobody watching: the scheduled job, the append-only store
that survives a bad re-run, the deploy that either works or rolls back cleanly.

**Currently:** finishing the CS degree at WGU, running the pipelines above, and looking for a team where
infrastructure is a first-class concern rather than something the backend engineers do on Fridays.

**Reach me:** swegeraldogrell@gmail.com

</details>

<p align="center"><sub>This README is rebuilt by a GitHub Action. If it looks stale, something in my own pipeline broke, and that is on me.</sub></p>
