# Vercel deployment

The Flask app is detected from the root `app.py` file. Static CSS is served from `public/style.css`.

## Shop accounts

Each shop creates an account at `/register` with its shop name, email, and password. Passwords are stored as one-way hashes. Product and sale rows are scoped to that account's `shop_id`; users must log in to access the dashboard. Forms use CSRF tokens and secure session cookies on Vercel.

## Required Vercel environment variables

Set these in **Project Settings → Environment Variables** for Production and Preview:

- `GNANI_API_KEY` — Gnani API key for Prisma STT and Timbre TTS.
- `FLASK_SECRET_KEY` — a long random secret used to sign sessions.
- `DATABASE_URL` — a PostgreSQL connection string from a hosted provider. Use a pooled connection string if the provider offers one, and require TLS (`sslmode=require`).

Optional:

- `GEMINI_API_KEY` — Gemini API key for command understanding; the local parser fallback remains available when omitted or unavailable.
- `GEMINI_MODEL` — defaults to `gemini-3.8-flash`.

Never commit `.env` or real API keys. SQLite remains the local development default; Vercel refuses to use temporary SQLite storage for shop data.

## Deploy

Import `teena105/DukaanSaathiAI` from GitHub, add the environment variables above, and deploy. Vercel provides the public URL after a successful build. For a multi-shop launch, create the PostgreSQL database first and add its `DATABASE_URL` to Vercel before deploying.
