# FDA Automation Backend

Node/Express service that takes a structured incident report from the
[UrRecalls](https://github.com/senseikartikey/UrRecalls-app-personal) mobile app
and **files it on the FDA MedWatch consumer-reporting site automatically**, using
a headless browser.

## What it does

- Exposes `POST /api/start-fda-automation`, called by the app's
  "Review & Submit" screen with a `SubmissionPayload`.
- Saves each payload as JSON under `submitted_reports/`.
- Drives the live FDA MedWatch form
  (`accessdata.fda.gov/scripts/medwatch/index.cfm`) with **Puppeteer + stealth**
  (`automation/fdaAutomator.js`), filling every page from the payload.
- Handles the form's reCAPTCHA by solving the **audio challenge** with
  **Google Cloud Speech-to-Text** (see the
  [`automation`](https://github.com/senseikartikey/automation) prototype).
- Ships a reporting side-tool: `generate_dashboard.py` builds an interactive
  Plotly HTML dashboard (`report_dashboard_v2.html`) from the saved reports, and
  `generate_sample_data.py` fabricates sample submissions for testing it.

## Endpoints

| Method | Route | Purpose |
|--------|-------|---------|
| `POST` | `/api/start-fda-automation` | Accept a report payload and run the automation. |
| `GET`  | `/` | Health check. |

## Setup

```bash
npm install
```

Requirements:

- Node 18+
- A Google Cloud service-account key (Speech-to-Text enabled)
- `.env` with at least:
  ```
  PORT=3000
  # Google credentials, e.g. GOOGLE_APPLICATION_CREDENTIALS=./google-cloud-key.json
  ```

## Run

```bash
node server.js
```

The server binds `0.0.0.0` and prints a LAN URL so the Expo app on a phone can
reach it.

## Dashboard

```bash
pip install pandas plotly nltk numpy
python generate_dashboard.py       # -> report_dashboard_v2.html
```

## ⚠️ Scope

This automates a public form **on the author's own behalf** to submit genuine FDA
consumer reports. Reusing the CAPTCHA-solving or form-filling code against sites
you're not authorised to automate breaks their terms of service.
