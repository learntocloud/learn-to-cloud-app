# Learn to Cloud Frontend

React + TypeScript app built with Vite.

The frontend is intentionally a thin presentation layer: it calls the API for all business rules (progress, locking, validation).

## Local development

Install deps:

```bash
npm install
```

Run dev server:

```bash
npm run dev
```

## Build

```bash
npm run build
```

## Environment variables

See `.env.example` for required values.

- `VITE_API_URL`
- `VITE_CLERK_PUBLISHABLE_KEY`

## Deployment

Production deploys build a container image from `frontend/Dockerfile` (see `.github/workflows/deploy.yml`).
