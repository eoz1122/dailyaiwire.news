# n8n Workflows

This directory stores DailyAIWire n8n workflow exports that are still operationally relevant.

## Active LinkedIn Workflow

- Final workflow file: `ops/n8n/linkedin-rss-trigger-production.json`
- This is the final production export for the LinkedIn posting automation.
- This is the workflow that was imported into n8n and chosen as the active production baseline.
- The older broken LinkedIn workflow was disabled in n8n.

## Archive

Archived exports live under `ops/n8n/archive/`.

- `archive/linkedin-article-post-test.json`
  - One-item test workflow used to validate the LinkedIn REST image upload and article post flow.
- `archive/linkedin-article-post-scheduled-production.json`
  - Alternate production-oriented export from the transition period before returning to the RSS trigger model.

## Notes

- The production workflow uses the RSS trigger model, limits runs to 8 articles, and spaces posts by 15 minutes.
- LinkedIn posting uses the newer REST flow rather than the old built-in LinkedIn node.
