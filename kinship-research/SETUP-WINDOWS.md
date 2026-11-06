# Get Kinship running on your PC and GitHub

## Local preview in 3 steps

1. Extract `kinship-research-starter.zip` to a folder such as `Documents\kinship-research`.
2. Install Hugo (in PowerShell: `winget install -e --id Hugo.Hugo.Extended`). Restart the terminal.
3. Inside the project folder, run `hugo server -D`, then open <http://localhost:1313/>.

The separate `kinship-preview.html` file can also be opened directly in a browser; it is a static design preview and does not require Hugo.

## Connect to GitHub (the one manual action)

1. Open <https://github.com/new>. Create a **private** repository named `kinship-research` on your personal account. For the commands below, **do not** initialize it with a README, license, or `.gitignore`; those are already inside the ZIP.
2. Open PowerShell in the extracted project folder, then run:

```powershell
git init
git add .
git commit -m "Initial Kinship research prototype"
git branch -M main
git remote add origin https://github.com/NikodemSzewczyk-hash/kinship-research.git
git push -u origin main
```

If Git prompts for authentication, complete the browser sign-in or use GitHub Desktop. The repo remains private until you explicitly change its visibility.

## Publish later

Link that repository to Netlify or Cloudflare Pages. Configure the build command `hugo --minify` and output folder `public`. Set the Hugo version to the version in `.github/workflows/build.yml`. Before adding a real domain, change `baseURL` in `hugo.toml`.

## What is NOT live yet

The research pipeline only generates *unreviewed* candidate metadata; it is not scheduled, not linked to the current ChatGPT Sites publication, and does not automatically publish papers. The existing ChatGPT-hosted Kinship site remains untouched.
