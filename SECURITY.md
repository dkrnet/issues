# Security Policy

## Supported versions

Security fixes are considered for the current public version of the project.

The application is intended for authenticated internal, small-network, air-gapped, or isolated deployments behind Apache authentication. It is not intended to be exposed as a public unauthenticated issue-tracking service.

## Reporting a vulnerability

Please report security issues privately to the project maintainer rather than opening a public issue with exploit details. Include the affected version or commit, deployment context, reproduction steps, and any relevant logs with sensitive information removed.

## Deployment notes

- Deploy behind properly configured Apache authentication.
- Ensure protected actions receive a trusted `REMOTE_USER` value from the web server.
- Keep the SQLite database, per-user config directory, and optional `/etc/issues.conf` outside the web document root.
- Restrict filesystem permissions so the Apache runtime user has only the access required by the application.
- Review upload limits and local mail configuration before enabling attachments or notification email.
