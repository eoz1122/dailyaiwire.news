# n8n Workflows

This directory stores DailyAIWire n8n workflow exports that are still operationally relevant.

## Active LinkedIn Workflow

- Current import file: `outputs/linkedin-n8n/linkedin-rss-scheduled-24-daily.json`
- Import name: `LinkedIn RSS Scheduled 24 Daily - Diverse`
- The workflow schedules up to 24 successful posts per New York day after 06:00.
- Daily diversity caps are 6 research posts, 4 posts from one source, and 6 posts from one category.
- Counts increase only after LinkedIn confirms a successful post.
- The selector and success-state source files live beside this README and are injected into the import JSON.
- Disable the previous LinkedIn workflow only after this workflow is imported, activated, and test-executed successfully.

## Archive

Archived exports live under `ops/n8n/archive/`.

- `archive/linkedin-article-post-test.json`
  - One-item test workflow used to validate the LinkedIn REST image upload and article post flow.
- `archive/linkedin-article-post-scheduled-production.json`
  - Alternate production-oriented export from the transition period before returning to the RSS trigger model.

## Notes

- The LinkedIn feed exposes source and research metadata through additional RSS category elements.
- LinkedIn posting uses the newer REST flow rather than the old built-in LinkedIn node.
