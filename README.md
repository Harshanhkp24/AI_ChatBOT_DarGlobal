# Estate Atlas — DarGlobal × Wasalt

A source-grounded property research chatbot. It crawls a bounded set of publicly accessible pages from DarGlobal and Wasalt, retrieves relevant snippets locally, and asks OpenRouter's `openrouter/free` router to answer with source links.

## Assignment plan

1. **Collect public data:** At startup, follow each publisher's public sitemap and a small set of seed pages. The crawler first reads `robots.txt` and stops for that publisher if the policy cannot be read. It stays on the listed domains, only requests HTTPS HTML, removes navigation and scripts, waits between pages, and caps the crawl at 45 pages per publisher. Review each website's terms before expanding the crawler or retaining data.
2. **Build the chatbot:** Search retrieved page text for relevant snippets, provide only those excerpts to the language model, and include source URLs in the answer. Listings are snapshots from public pages; they are not guaranteed to be live inventory.
3. **Use a free model:** Set `OPENROUTER_MODEL=openrouter/free`. This routes to an available free model; model availability and free-tier limits can change. Configure an OpenRouter API key at runtime.
4. **Containerize:** Build from the included Dockerfile. The app binds to `0.0.0.0:$PORT` and runs as a non-root user.
5. **Deploy:** `render.yaml` defines a free Render web service. Push this directory to GitHub/GitLab/Bitbucket, connect it to Render, add `OPENROUTER_API_KEY`, and apply the Blueprint. Render then issues a public `*.onrender.com` URL.
6. **Verify:** Open `/api/health` and confirm `documents > 0` and `openrouter_configured: true`; ask a question in the UI and follow the citations.

## Run locally

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env and set OPENROUTER_API_KEY to your key
python app.py
```

Open http://localhost:8000. First startup crawls sources in the background; allow a short time for the source library to populate. `.env` is ignored by Git. For Docker, set `OPENROUTER_API_KEY` in the environment and map port 8000.

## Deployment state

This workspace must be pushed to a Git provider before Render can deploy it. No repository remote or OpenRouter secret is included. Do not commit `.env` or API keys. A live URL is only available after Render completes the first build and deployment.

