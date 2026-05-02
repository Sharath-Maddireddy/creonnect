# Frontend Documentation

This document describes the Creonnect frontend — a Vite-powered SPA that consumes the backend API.

## Overview

- **Framework:** Vite (lightweight, fast build tool)
- **Location:** `frontend/` directory
- **Entry Point:** `frontend/index.html`
- **Build Output:** `frontend/dist/` (generated)
- **Development Server:** Port 5173 (default Vite)

## Project Structure

```
frontend/
├── index.html          # Main HTML entry point
├── package.json        # Dependencies and scripts
├── package-lock.json
├── vite.config.js      # Vite configuration
├── src/                # Source code
│   ├── main.js         # Application entry point
│   ├── App.vue         # Root component (if using Vue)
│   ├── components/     # Reusable components
│   ├── pages/          # Page-level components
│   ├── services/       # API client helpers
│   ├── stores/         # State management (e.g., Pinia)
│   └── assets/         # Images, fonts, styles
├── public/             # Static assets (served as-is)
├── dist/               # Production build output
└── demos/              # Demo/example pages
```

## Getting Started

### Install Dependencies

```bash
cd frontend
npm install
```

### Development Server

```bash
npm run dev
```

Server runs on `http://localhost:5173` (or next available port).

### Build for Production

```bash
npm run build
```

Output is in `frontend/dist/`. Deploy this folder to a static host or CDN.

### Preview Production Build

```bash
npm run preview
```

Runs the production build locally for testing.

## API Integration

### Backend Base URL

By default, the frontend connects to `http://localhost:8000` (backend API on local development).

**Configuration:**
- Check `src/services/api.js` or environment config for base URL.
- For production, update API base URL to match deployed backend domain.
- May use environment variables like `VITE_API_BASE_URL` for environment-specific config.

### Example API Call (pseudocode)

```javascript
// src/services/dashboard.js
async function getDashboard(userId) {
  const response = await fetch(`/api/creator/dashboard?user_id=${userId}`, {
    credentials: 'include'  // Include session cookies
  });
  return response.json();
}
```

### Authentication

- **Session-based:** Uses session cookies set by backend OAuth flow.
- **Flow:**
  1. User clicks "Connect Instagram" → redirects to backend OAuth.
  2. Backend sets session cookie after OAuth success.
  3. Subsequent API calls include session cookie automatically (`credentials: 'include'`).

## Key Pages / Components

### Dashboard Page
- **Route:** `/dashboard`
- **Purpose:** Display creator dashboard with profile, posts, metrics, charts.
- **API Calls:** `GET /api/creator/dashboard`, `GET /api/creator/analytics`
- **Features:**
  - Profile summary card
  - Post grid with engagement metrics
  - Time-series charts (engagement, views)
  - Account health scoring
  - Action plan / recommendations

### Post Analysis Page
- **Route:** `/analyze`
- **Purpose:** Submit a post for analysis.
- **API Calls:** `POST /api/v1/post-analysis`
- **Features:**
  - Form to input post data (URL, caption, metrics)
  - Display analysis results (vision, scores, recommendations)
  - Cringe/brand-safety summary

### Authentication Pages
- **Login Page:** `/login` → triggers `GET /api/auth/instagram/login`
- **Callback Handler:** Processes OAuth redirect and stores session.
- **Logout:** Button to `POST /api/auth/logout`

## Styling

- **CSS Framework:** (Tailwind, Bootstrap, or custom — check `src/styles/`)
- **Dark Mode:** (If supported, check component configuration)
- **Responsive Design:** Mobile-first approach (check `public/` for viewport meta tags)

## State Management

- **If using Pinia/Vuex:** Check `src/stores/` for global state (user, dashboard, UI).
- **If using Context API (React):** Check `src/context/` for providers.
- Common state:
  - Current user profile
  - Dashboard data cache
  - UI state (loading, modals, etc.)

## Build & Deployment

### Production Build

```bash
npm run build
```

Outputs optimized bundle to `frontend/dist/`.

### Deployment Options

1. **Static Host (Vercel, Netlify):**
   - Push `dist/` to Git.
   - CI/CD auto-builds and deploys.

2. **CDN (Cloudflare, AWS S3 + CloudFront):**
   - Upload `dist/` contents.
   - Set origin backend to API server.

3. **Traditional Web Server (Nginx, Apache):**
   ```nginx
   # Example Nginx config
   server {
     listen 80;
     location / {
       root /var/www/creonnect/frontend/dist;
       try_files $uri $uri/ /index.html;  # SPA routing
     }
     location /api {
       proxy_pass http://backend:8000;  # Proxy to backend
     }
   }
   ```

### Environment Variables for Build

- `VITE_API_BASE_URL` — Backend API URL (used in build time or runtime).
- `VITE_APP_VERSION` — App version (for versioning displays).

## Browser Support

- Modern browsers (Chrome, Firefox, Safari, Edge).
- ES6+ assumed (Vite targets modern JS).
- Polyfills may be needed for older browsers — configure in `vite.config.js`.

## Common Development Tasks

### Add a New Page

1. Create component in `src/pages/NewPage.vue`.
2. Register route in `src/router.js` (or equivalent).
3. Import API helpers from `src/services/`.
4. Fetch data on mount, render with components.

### Add API Helper

1. Create file in `src/services/myApi.js`.
2. Export async functions for each endpoint.
3. Handle errors and return structured data.
4. Import in pages/components as needed.

### Debugging

- **Vite Dev Tools:** Browser DevTools (F12).
- **Network Tab:** See API calls and responses.
- **Console:** Check for errors and logs.
- **Performance:** Use Lighthouse or DevTools Performance tab.

## Performance Tips

- **Lazy Load Routes:** Use dynamic imports for code splitting.
  ```javascript
  const Dashboard = () => import('./pages/Dashboard.vue');
  ```
- **Image Optimization:** Compress images, use WebP format, lazy-load below fold.
- **Caching:** Use service workers for offline support (optional).
- **Bundle Size:** Monitor with `npm run build` output.

## Testing (if applicable)

- **Unit Tests:** Jest or Vitest (check `src/__tests__/`).
- **E2E Tests:** Cypress or Playwright (check `e2e/`).
- **Run Tests:**
  ```bash
  npm run test
  npm run test:e2e
  ```

## Troubleshooting

### API Calls Failing (CORS Error)

- Ensure backend `CORS_ALLOWED_ORIGINS` includes frontend URL.
- Check backend is running on expected port.
- Verify `credentials: 'include'` in API fetch calls.

### Build Fails

- Run `npm install` to ensure dependencies.
- Check Node version (Vite requires Node 14+).
- Check for TypeScript errors (if using TS): `npx tsc --noEmit`

### Styling Not Applied

- Ensure CSS imports are in entry point or component.
- Check Vite CSS loader configuration in `vite.config.js`.
- Inspect DevTools to see computed styles.

## Next Steps

- Implement missing pages/components.
- Add integration tests for API interactions.
- Set up CI/CD deployment pipeline.
- Monitor frontend performance in production.

