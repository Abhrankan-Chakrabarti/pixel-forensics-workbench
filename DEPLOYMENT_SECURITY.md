# Public deployment and security checklist

This project has application-level safeguards, but no single Flask application can guarantee protection from every malicious file or denial-of-service attack. Complete the infrastructure steps below before exposing the service publicly.

## Implemented in this package

- Upload file cap (20 MiB), bounded request body, image format verification, positive dimension check, and a 20-million-pixel ceiling.
- Pillow decompression-bomb warnings are treated as upload failures; the first frame/page is decoded for the analysis context.
- Generated UUID session folders; uploaded filenames are sanitized and do not determine the session path.
- Absolute retention marker per session. Uploads, visualizations, report cache and temporary session artifacts are scheduled for cleanup no later than the 10-minute retention threshold plus the cleanup interval during normal operation. The worker runs every 15 seconds; startup cleanup reaps leftovers from a prior process.
- Per-process request rate limits, one active analysis at a time, module-ID validation, a per-session output-size cap, and same-origin checks when the browser supplies an Origin header.
- Security response headers, Content Security Policy, no-store caching, and generic error messages for unexpected failures.
- About, Privacy, Terms, and Contact pages; attribution uses `om ctf osint industries` without a personal name or LinkedIn link.

## Required EC2 steps before going public

1. Use a dedicated unprivileged Linux user for the application. Do not run Flask as root.
2. Keep the project and its temporary folders writable only by that user (typically directories `0700`, files `0600`). Do not place uploads under a public static directory.
3. Set `PIXEL_FORENSICS_ENV=production` and a strong random `PIXEL_FORENSICS_SECRET` (at least 32 characters) in the service environment. Never put secrets in source control or send them in chat.
4. Install dependencies from `requirements.txt` in a virtual environment. Keep Flask, Pillow, NumPy, the OS and image codecs updated; run a dependency audit before releases.
5. Run behind Nginx or another maintained reverse proxy with HTTPS. Redirect HTTP to HTTPS, set a request-body limit consistent with the app, set upstream/read timeouts, and do not expose the Gunicorn port publicly.
6. AWS Security Group: allow inbound 443 (and 80 only for redirect/certificate validation); restrict SSH (22) to the administrator's known IP/VPN. Do not expose database, Redis, or Gunicorn ports.
7. Start with **one Gunicorn worker** because session state and built-in rate limits are in process memory. Example: `gunicorn --workers 1 --threads 2 --timeout 240 --bind 127.0.0.1:8000 app:app`. The semaphore still allows only one analysis job at a time. Do not scale to multiple workers/instances without moving session state and rate limiting to a shared store and redesigning cleanup coordination.
8. Use systemd or an equivalent supervisor with memory/CPU limits and restart policy. Consider a dedicated container or isolated worker with OS-level memory/CPU/process limits for image decoding and analysis. Application timeouts alone are not a complete DoS defence.
9. Configure host-level disk monitoring and a disk quota/size-limited temporary volume. The application caps generated artifacts per session, but OS logs, reverse-proxy logs, swap, snapshots, and storage backups are managed outside the app.
10. Configure logs to avoid request bodies, image bytes, report contents, session IDs, and sensitive metadata. Review reverse-proxy and cloud logging defaults.
11. If public traffic is expected, add AWS WAF or another edge rate-limit/bot-control layer. The built-in rate limiter is per process and can be bypassed by distributed traffic; it is a baseline, not a replacement for edge controls.
12. Before launch, test uploads near the size/pixel limits, malformed files, expired sessions, many parallel requests, output size caps, HTTPS, report downloads, and cleanup after a forced application restart.

## Retention caveat

The 10-minute policy means the app schedules removal of application-managed temporary files after the session's creation time reaches 10 minutes, with a cleanup pass every 15 seconds. If a module is still actively running at that threshold, cleanup is deferred until that job finishes to avoid deleting files underneath it; this can extend retention for that active job. OS storage, snapshots, backups, swap, and external logs are outside the app's deletion guarantee. For strict retention guarantees, run analysis in a killable isolated worker and use ephemeral encrypted storage with infrastructure-level retention disabled.

## Run locally

Windows: run `setup.bat`, then `run.bat`. For production deployment, do not use `app.py`'s built-in development server.
