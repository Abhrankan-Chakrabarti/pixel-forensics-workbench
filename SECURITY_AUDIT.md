# Security review summary

Scope: static review and code changes to the supplied Pixel Forensics Workbench project. This is not a penetration test or a guarantee that every vulnerability is eliminated.

## Changes made

- Upload size and decoded-pixel limits; image format verification; decompression-bomb warnings rejected instead of ignored.
- Uploads use generated session directories and restrictive permissions where supported; user filenames do not control directory paths.
- Module IDs are validated against the registry before execution; analysis requests are size-limited.
- A single in-process analysis slot, per-process request rate limits, and generated-output size limits reduce accidental or simple abusive resource use.
- Same-origin checks are applied to browser mutation requests when an Origin header is present; CORS is not enabled.
- Responses add CSP, no-sniff, frame denial, no-referrer, no-store, permissions, and same-origin resource-policy headers.
- Internal exception messages are withheld from module error cards and unexpected analysis responses.
- Upload, result, and report folders use a creation marker for a 10-minute retention target; cleanup checks every 15 seconds and also runs at startup.
- Added About, Privacy, Terms, and Contact pages and attribution to `om ctf osint industries`. No real name or LinkedIn profile was added.
- Added deployment examples and a public-hosting checklist.

## Residual risks and operational requirements

- Image parsers are complex native-code dependencies. Validation reduces risk but cannot prove a file is safe. Keep Pillow and OS packages patched and isolate image processing with OS/container CPU, memory, process, and disk limits.
- Built-in rate limits and sessions are in process memory. Use one Gunicorn worker for this version; use an edge/WAF limit. Multi-worker or multi-instance deployments require shared session/limiter state and coordinated cleanup.
- Cleanup is best-effort at the 10-minute threshold plus up to one cleanup interval. If analysis is still active, deletion is deferred until it finishes. Strict deletion timing requires killable isolated jobs and ephemeral storage.
- App deletion cannot erase data from swap, filesystem snapshots, backups, provider logs, or separately configured reverse-proxy logs. Review/disable those retention sources where appropriate.
- The service has no user account or authentication layer. The random session UUID functions as a bearer capability for that session; do not leak it. Add authentication if the service is intended for a private or restricted audience.
- The in-memory limiter is per process and not sufficient against distributed DoS. Configure Nginx/AWS WAF and monitor EC2 resource use.
- Review the Privacy Policy against the final AWS, domain, TLS, logging, backup, and snapshot configuration before launch.

## Validation performed in the build environment

- Python syntax compilation completed for application/config/backend files.
- Existing analyzer tests: 5 passed.
- New route/security tests were added, but could not be executed in this build environment because Flask/Werkzeug are not installed here and package installation was unavailable. They should run after installing `requirements-dev.txt` in the project virtual environment.
