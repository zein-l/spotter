# Deploying to Vercel

Both apps deploy from this repository. **Option A** runs everything in one Vercel project on one
domain. **Option B** uses two projects and is the fallback if Option A gives you trouble
(Vercel Services is in beta).

Before you start, make sure the code is on the branch Vercel will deploy, usually `main`.

## Option A: one project (Vercel Services)

`vercel.json` at the repository root defines two services:

- `web`: the Vite app in `frontend/`, serving every path.
- `api`: the Django app in `backend/`, serving `/api/*`. Vercel finds it through `manage.py`.

1. On vercel.com, choose **Add New → Project** and import the `spotter` repository.
2. Leave **Root Directory** empty (the repository root).
3. Set **Framework Preset** to **Services**. A project only builds as services when this preset
   is selected *and* `vercel.json` contains `services`. If you can't pick it during import,
   deploy once, then change it under **Settings → Build and Deployment** and redeploy.
4. Under **Environment Variables**, add `DJANGO_SECRET_KEY` with any long random value. For
   example, generate one with `python3 -c "import secrets; print(secrets.token_urlsafe(50))"`.
5. Deploy.

## Option B: two projects

**API project**

1. **Add New → Project**, import the repository, and set **Root Directory** to `backend`.
   Vercel detects Django from `manage.py`. Python 3.12 comes from `.python-version`, and
   dependencies come from `requirements.txt`.
2. Add `DJANGO_SECRET_KEY`.
3. Deploy, then open `https://<api-project>.vercel.app/api/health`. It should return `{"status": "ok", ...}`.

**Web project**

1. **Add New → Project**, import the same repository, and set **Root Directory** to `frontend`.
   Vercel detects Vite.
2. Add `VITE_API_BASE_URL=https://<api-project>.vercel.app` (no trailing slash).
3. Deploy.

The API already accepts CORS requests from any `https://*.vercel.app` origin. For a custom
frontend domain, also set `CORS_ALLOWED_ORIGINS=https://your-domain.com` on the API project.

## Optional: truck routing with OpenRouteService

The default routing (OSRM) needs no key. For a heavy-goods-vehicle profile, sign up for a free
key at <https://openrouteservice.org> and set these on the API (or the single) project:

```
ROUTING_PROVIDER=ors
ORS_API_KEY=<your key>
```

If ORS fails for any reason, the API falls back to OSRM automatically.

## After deploying: checklist

These parts talk to live third-party services. The automated tests mock them, so check them
once on the deployed site:

1. `/api/health` returns `{"status": "ok"}`.
2. Type "Dallas" in a location field: suggestions appear (Photon).
3. Click **Chicago → St. Louis → Dallas**: the map shows streets (OpenFreeMap tiles) and the
   route follows the interstates (OSRM). No yellow "estimated route" banner should appear.
4. The stops list shows a 10-hour rest. Two daily logs render, each totalling `=24:00`.
5. **Print / save all as PDF** produces one landscape page per day.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Every `/api/...` call returns 400 *Bad Request* | The request host isn't in `ALLOWED_HOSTS`. Add your domain to `DJANGO_ALLOWED_HOSTS` (comma-separated). |
| Frontend loads, API calls return 404 | Option A: confirm the Framework Preset is **Services**. Option B: check `VITE_API_BASE_URL`, then redeploy the web project, since Vite reads env vars at build time. |
| Yellow "estimated straight-line route" banner | Both public OSRM servers were unreachable or rate-limited. It recovers on its own; for steady routing, set up ORS (above). |
| Map is grey with no streets | The OpenFreeMap tile host is down. The app switches to CARTO tiles automatically; the route and stops still draw. |
| First request after a while is slow | Serverless cold start, roughly 1–2 s. The page pings `/api/health` on load to warm it while you type. |
