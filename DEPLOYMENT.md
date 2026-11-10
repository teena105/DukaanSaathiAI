# Vercel deployment

This Flask app is detected by Vercel from the root `app.py` file. Static CSS is served from `public/style.css`.

## Environment variables

Set these in Vercel Project Settings → Environment Variables:

- `GNANI_API_KEY` — Gnani API key for Prisma STT and Timbre TTS.
- `GEMINI_API_KEY` — Gemini API key for command understanding (optional; local parser fallback remains enabled).
- `GEMINI_MODEL` — `gemini-3.8-flash`.
- `FLASK_SECRET_KEY` — a long random secret used to sign Flask sessions.

Never commit `.env` or real API keys.

## Database limitation

On Vercel, SQLite uses `/tmp/dukaansaathi.db` so the app can run in a serverless function. Vercel temporary storage is not a persistent shared database: data can reset after a cold start and is not shared reliably across function instances. Use a hosted database before treating this as a production multi-shop service.

## Deploy

Import `teena105/DukaanSaathiAI` at Vercel, configure the environment variables above, and deploy. Vercel provides the public application URL after the deployment succeeds.
