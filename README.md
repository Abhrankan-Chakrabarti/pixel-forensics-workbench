# Pixel Forensics Workbench

[![Python CI](https://github.com/Abhrankan-Chakrabarti/pixel-forensics-workbench/actions/workflows/ci.yml/badge.svg)](https://github.com/Abhrankan-Chakrabarti/pixel-forensics-workbench/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-3776AB?logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.0-black?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)

<p align="center">
  <img src="static/img/og-preview.png" alt="Pixel Forensics Workbench Banner" width="100%" />
</p>

A local-first Flask web app for inspecting image pixels, image statistics, spatial relationships, bit planes, compression clues, and candidate anomalies. Developed by **Abhrankan Chakrabarti**. Designed as a practical workbench for manual digital investigation—not as an automatic authenticity verdict.

## What is included

- **44 registered analysis modules** split across Core, Basic Analysis, Pixel Relationships, Anomaly Detection, Image Forensics, Data Hiding & Bitstream, Investigation & Comparison, and Utilities & Reporting.
- Single image upload per session, with selected modules reusing a common decoded image context.
- Individual checkboxes, category selection, Select All, Core Set, Clear, and module search.
- Result cards grouped by category, with larger one-per-row visualizations, readable metrics and analyst notes, isolated module errors, and downloadable, self-contained HTML reports and portable PDF summaries (JSON is kept only as an internal report cache).
- The module selector automatically collapses when analysis completes to give result images more room; use **Show Module Selection** to reopen it.
- Source and result images preserve the full aspect ratio and can be clicked to open an expanded image viewer. RGB channels, the six low-bit planes, eight grayscale bit planes, and overview signals are shown as separate images rather than tiny montages. The hex/ASCII byte view uses larger readable text.
- User-selectable themes and page styles. Defaults: **Midnight Blue**, **Cyber Glow**, **Neon Pulse**. Seven dark themes are included (Hacker Green, Neon Cyberpunk, Midnight Blue, Amber Terminal, Crimson Pulse, Ultraviolet, Stealth Graphite), plus six layouts and six animation modes (with a separate Off option). The border animation cycles blue, cyan, purple, pink, red, orange, yellow, white, and dark grey (no teal).
- Histogram, dominant-colour distribution, horizontal periodicity/autocorrelation, DCT coefficient distributions, and evidence-fusion metric plots are rendered as interactive browser-native SVG charts using the measured values from the analyzers. Hover/focus on graph marks to inspect the corresponding value. Heatmaps, depth maps, bit planes, ELA and other spatial image outputs remain full image visualizations. RGB channel statistics use separate colour tiles and numeric boxes rather than four channel image thumbnails. The analysis wait dialog is larger and animated.
- A deliberately adaptive autostereogram/Magic Eye module: it sweeps horizontal lags to estimate periodicity, derives a candidate disparity range from the image, and creates a candidate depth map and matching-error map. It does not hard-code one magic period.
- Temporary upload/result/report files have an absolute 10-minute retention target from upload, with cleanup checks every 15 seconds. Clearing the image requests immediate deletion. An actively running analysis can defer cleanup until the job ends.
- Tests for the registry, complete analyzer run, separate visual outputs, and measured native-chart payloads.

## Requirements

- Windows 10/11, macOS, or Linux
- Python 3.10 or newer
- Internet access the first time you install Python packages (Flask, NumPy, Pillow)

## Run on Windows 11

1. Extract the ZIP to a normal writable folder, for example `C:\PixelF\pixel-forensics-workbench`.
2. Install Python 3.10+ from [python.org](https://www.python.org/downloads/windows/). On the installer screen, enable **Add Python to PATH**.
3. Double-click **`setup.bat`** once. It creates `.venv` and installs the dependencies from `requirements.txt`.
4. Double-click **`run.bat`**. A terminal opens and the app starts at `http://127.0.0.1:5000`.
5. Keep the terminal open while using the app. Press `Ctrl+C` in that terminal to stop the server.

If Windows blocks the batch file, open Command Prompt in the extracted folder and run:

```bat
setup.bat
run.bat
```

### Manual setup (PowerShell)

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Then open `http://127.0.0.1:5000` in your browser.

## Run tests

Install the test dependency and run the included analyzer tests:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

The tests exercise all 44 analyzer IDs on a generated test image. They do not require any real or private image to be included in the repository.

## Project structure

```text
pixel-forensics-workbench/
├── app.py                     # Flask routes, upload validation, session TTL/cleanup
├── config.py                  # Size limits and paths
├── requirements.txt
├── setup.bat / run.bat         # Windows setup and launch helpers
├── backend/
│   ├── registry.py             # All module IDs and categories
│   ├── core/                   # Image context, visualizations, engine, results
│   ├── basic/                  # Color channels, grayscale, histogram, colors
│   ├── relationships/          # Differences, Magic Eye, XOR, correlation, bit planes
│   ├── anomaly/                # Local statistics and candidate regions
│   ├── forensic/               # Residual, filters, gradients, FFT/DCT, ELA screens
│   ├── data_hiding/             # LSB, bit extraction, file signatures/byte sample
│   ├── investigation/            # Region, tile, hotspot, evidence roll-up
│   └── utilities/                # Normalization, montage, report, hashes
├── templates/index.html
├── static/css/style.css
├── static/js/app.js
├── uploads/                     # Temporary uploaded image sessions
├── results/                     # Generated image visualizations
├── reports/                     # Internal report cache; users download HTML/PDF
├── data/cases/                  # Reserved for future saved-case support
├── data/temp/                   # Temporary processing area
└── tests/
```

## Analysis caveats (important)

These methods are intentionally transparent screening aids. A heatmap, high residual, repeated tile, LSB balance, JPEG boundary, FFT/DCT pattern, or ELA difference **does not by itself prove editing or hidden content**. Images with resizing, compression, sharpening, natural repetition, or fine texture can produce false positives. The autostereogram module reports a candidate period/depth estimate; ordinary images can also have periodic patterns, so manually inspect its correlation and matching-error views.

For large files, the application caps uploads at 20 MiB and image dimensions at 35 million pixels. Many modules work from a copy resized to a maximum 1,400-pixel longest dimension for bounded memory/time; source metadata and SHA-256 still refer to the original uploaded bytes. Pixel coordinates produced by image-analysis modules are therefore explicitly labeled as analysis-copy coordinates where applicable.

## Local privacy and public deployment

By default the web server binds only to `127.0.0.1`; it is not exposed to your LAN or the internet. Files are written temporarily inside `uploads/`, `results/`, and `reports/` for analysis and are scheduled for deletion at the 10-minute retention threshold. They are also cleared when you press Clear. Cleanup runs every 15 seconds and at startup. See `DEPLOYMENT_SECURITY.md` for the retention caveat and production security checklist, and `SECURITY_AUDIT.md` for the changes and remaining risks.

**Do not expose this build directly to the public internet without completing `DEPLOYMENT_SECURITY.md`.** The package includes baseline upload validation, rate limits, origin checks, headers, and cleanup, but still requires a production WSGI server, HTTPS/reverse proxy, host/worker resource limits, edge protection, log/snapshot review, and deployment-specific verification. It is not a guarantee against every DoS attack.

## Main API routes

- `GET /api/health` — server health and module count
- `GET /api/modules` — module catalog
- `POST /api/upload` — validate/save one image and create a session
- `POST /api/analyze` — run selected module IDs
- `GET /api/report/<session_id>/html` — download a self-contained HTML report with embedded visualizations
- `GET /api/report/<session_id>/pdf` — download a portable PDF report summary
- `GET /api/report/<session_id>` — backwards-compatible HTML report download
- `DELETE /api/session/<session_id>` — immediately clear an image session
- `GET /artifacts/<session_id>/<filename>` — access generated PNG visualizations for the active session

## Static pages and attribution

The app includes `/about`, `/privacy`, `/terms`, and `/contact`. Public attribution is credited to **Abhrankan Chakrabarti** with direct links to his LinkedIn profile.

---

## 👨‍💻 Author & Maintainer

**Abhrankan Chakrabarti**
- **LinkedIn**: [Abhrankan Chakrabarti](https://www.linkedin.com/in/abhrankan-chakrabarti-159460214/)
- **GitHub**: [@Abhrankan-Chakrabarti](https://github.com/Abhrankan-Chakrabarti)
- **Email**: [abhrankan@gmail.com](mailto:abhrankan@gmail.com)
