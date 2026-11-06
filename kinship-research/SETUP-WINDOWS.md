# Run dynasty_ locally on Windows

The GitHub repository is [dynasty-research](https://github.com/NikodemSzewczyk-hash/dynasty-research).
Its Hugo project lives inside the existing `kinship-research` folder. This folder name is kept for deployment compatibility even though the public brand is now **dynasty_**.

## Local setup

1. Install [Hugo Extended](https://gohugo.io/installation/windows/): `winget install -e --id Hugo.Hugo.Extended`. Restart PowerShell.
2. Install Git if it isn't installed already.
3. Run:
   ```powershell
   git clone https://github.com/NikodemSzewczyk-hash/dynasty-research.git
   cd dynasty-research\kinship-research
   hugo server -D
   ```
4. Visit http://localhost:1313/ to preview the site.

## Editing and publishing

- Change content under `content/`, templates under `layouts/`, and styles under `static/css/`.
- Commit and push changes to the GitHub `main` branch to deploy via the existing Netlify project at https://dynastyecon.netlify.app/.
- Netlify builds from `kinship-research` (configured in the repository-root `netlify.toml`).
- Do not rename the Hugo directory without updating the build configuration.

## Current status

The website includes a small curated research archive. Automated ingestion and publication are not yet enabled.
