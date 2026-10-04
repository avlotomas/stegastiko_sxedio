# Start local app + public demo URL

Start the housing scheme app locally **and** expose a temporary HTTPS URL for external users.

## What to run

From the repo root, execute in the terminal (Django runs in the background; **public URL shows in this same window**):

```powershell
cd stegastiko
.\scripts\start-local-and-public.ps1
```

## After it starts

1. Wait for the green **PUBLIC URL** banner in PowerShell (also updates `.env`).
2. The script restarts Django automatically when the URL is ready.
3. Share the printed `https://….lhr.life` URL (new each time you start the tunnel).

## Local URLs (same machine)

- App: http://127.0.0.1:8000/
- Login: http://127.0.0.1:8000/login/

## Notes

- Keep both windows open while the demo is active.
- Ctrl+C in the tunnel window stops the public URL only; close the Django window to stop the local server.
- Change the default `admin` password before sharing the public link.
