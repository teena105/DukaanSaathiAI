# Vercel deployment

DukaanSaathi AI is a single-shop dashboard with no login or registration. It is detected by Vercel from the root `app.py`; the deployed stylesheet is `public/style.css`.

## Environment variables

Required:

- `GNANI_API_KEY` — Gnani API key for Prisma speech-to-text and Timbre text-to-speech.
- `FLASK_SECRET_KEY` — a long random value used to secure Flask sessions and voice confirmations.

Optional:

- `DATABASE_URL` — a PostgreSQL connection string for persistent product and sales data. If unset, local development uses `dukaansaathi.db`; Vercel uses temporary `/tmp` SQLite storage, which can reset between instances or deployments.
- `GEMINI_API_KEY` — Gemini key for command understanding; the local parser is used if Gemini is absent or unavailable.
- `GEMINI_MODEL` — defaults to `gemini-3.8-flash`.

Never commit `.env` or real API keys.

## Deploy

Import `teena105/DukaanSaathiAI` from GitHub, configure the environment variables, and deploy. Vercel provides the public URL after a successful build.
