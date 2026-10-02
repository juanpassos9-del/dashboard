# TTS Subscriber Login

Vite/React sign-in page for existing Supabase Auth subscribers. Successful login redirects to the Streamlit dashboard.

## Environment variables

Set these in Vercel Project Settings and in `.env.local` for local development:

```dotenv
VITE_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
VITE_SUPABASE_ANON_KEY=YOUR_SUPABASE_PUBLISHABLE_OR_ANON_KEY
VITE_STREAMLIT_URL=https://YOUR_APP.streamlit.app
```

The Supabase publishable/anon key is intended for browser clients; never use a service-role key here. Configure the Vercel deployment root directory as `DASHBOARD`, with build command `npm run build` and output directory `dist`.

In Supabase Auth, add the deployed Vercel origin to the allowed site URLs/redirect URLs as applicable. This page authenticates the user and redirects to Streamlit. It does not secure direct access to a publicly shared Streamlit app or transfer the Supabase browser session into Streamlit.

## Local development

```bash
npm install
npm run dev
```
