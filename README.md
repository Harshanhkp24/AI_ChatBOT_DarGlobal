# Estate Atlas — DarGlobal × Wasalt

Estate Atlas is a source-grounded property research chatbot for publicly available DarGlobal development information and Wasalt property-market pages. It retrieves relevant source excerpts, answers with an OpenRouter free model, and links users to the pages behind each response.

## Live application

- **Chatbot:** [estate-atlas-dlcd.onrender.com](https://estate-atlas-dlcd.onrender.com/)
- **Health check:** [estate-atlas-dlcd.onrender.com/api/health](https://estate-atlas-dlcd.onrender.com/api/health)
- **Render service:** [estate-atlas-dlcd dashboard](https://dashboard.render.com/web/srv-dbvdspek1f9s73c9c9a0)
- **Source repository:** [Harshanhkp24/AI_ChatBOT_DarGlobal](https://github.com/Harshanhkp24/AI_ChatBOT_DarGlobal)

## Assignment coverage

| Requirement | Implementation |
| --- | --- |
| Public data from DarGlobal and Wasalt | Bounded, `robots.txt`-aware Wasalt crawl plus an attributed DarGlobal snapshot of its Saudi portfolio index and two official project pages. |
| AI chatbot | FastAPI application with local keyword-based retrieval, source-grounded prompts, and linked citations. |
| Free OpenRouter model | Uses `openrouter/free`, which selects an available free text model. The selected model can change between requests. |
| Docker | Containerized with the included Dockerfile; runs as a non-root user and binds to Render's `$PORT`. |
| Public deployment | Deployed on Render at the live URL above, with `OPENROUTER_API_KEY` configured as a service environment variable. |

## Data sources and freshness

The crawler reads each site's public `robots.txt`, follows public sitemap URLs and a small set of seed pages, stays on the listed domains, requests HTTPS HTML only, and limits each publisher crawl to 45 pages with a delay between requests. Crawl results are refreshed when the application starts.

DarGlobal's anti-bot service blocks direct requests from the server crawler. To keep DarGlobal questions grounded, the Docker image includes a small snapshot checked on **November 19, 2026** from these official pages:

- [Saudi Arabia project portfolio](https://darglobal.co.uk/projects/properties-in-saudi-arabia)
- [Neptune, Interiors by Mouawad](https://darglobal.co.uk/neptune)
- [Trump Tower Jeddah](https://darglobal.co.uk/trump-tower-jeddah)

Live crawl content takes precedence over snapshot content for a matching page if the page becomes accessible. The snapshot is intentionally limited and should be refreshed as DarGlobal publishes changes. The Wasalt corpus is fetched from its public pages when the app starts.

This is a research assistant, not a live inventory feed. Availability, prices, completion dates, and terms can change; follow the source links and confirm current details with the publisher.

## How it works

1. At startup, the app loads its bundled DarGlobal snapshot and refreshes the permitted publisher pages in the background.
2. It ranks documents by keyword overlap with the user's question and selects up to five relevant pages.
3. It sends those excerpts to OpenRouter with instructions to answer from the supplied evidence and cite sources.
4. The UI displays source links alongside the answer.

The retriever is deliberately lightweight and does not use a vector database or embedding model.

## Run locally

Requires Python 3.12 or newer.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and set your own OpenRouter key:

```env
OPENROUTER_API_KEY=your_key_here
OPENROUTER_MODEL=openrouter/free
PUBLIC_URL=http://localhost:8000
```

Start the application and open <http://localhost:8000>:

```powershell
python app.py
```

Never commit `.env` or share the API key. `.gitignore` excludes the local environment file.

## Run with Docker

```powershell
docker build -t estate-atlas .
docker run --rm -p 8000:8000 --env-file .env estate-atlas
```

## Deploy on Render

The repository includes a Render Blueprint at [`render.yaml`](render.yaml). The web service builds from the Dockerfile and auto-deploys commits to `main`.

Set these variables under **Render → estate-atlas-dlcd → Environment**:

| Variable | Value |
| --- | --- |
| `OPENROUTER_API_KEY` | Your private OpenRouter API key |
| `OPENROUTER_MODEL` | `openrouter/free` |

Keep the key in Render's Environment settings or a local, ignored `.env` file. Do not add it to source code, `render.yaml`, or GitHub.

The free Render instance may spin down when idle, so the first request after a quiet period can take longer. OpenRouter's free model availability and rate limits can also vary.

## API

`GET /api/health` reports service status, loaded document count, configured model-key status, and source publishers. It does not return the API key.

`POST /api/chat` accepts a JSON request:

```json
{
  "message": "What DarGlobal projects are listed in Saudi Arabia?",
  "history": []
}
```

The response includes the answer, selected model, and source links.

