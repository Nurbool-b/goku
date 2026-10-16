# goku eSports — online booking + admin

- `index.html` — client site (zones, tariffs, rules, "I'm on my way" request). Talks to Supabase.
- `admin.html` — operator panel (login with email + password). Open `/admin.html` on the same host.
- Backend: Supabase project `goku-control` (tables, row-level security, RPC functions).
- PC agents (power on/off) are in the separate `goku-agents.zip` — it contains secret keys, never commit it.

The Supabase `anon` key inside the HTML files is public by design; all admin actions require an admin login.

Deploy: GitHub Pages → Deploy from a branch → `main` / root.
