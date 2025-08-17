# Homarr Navidrome Web Player

A tiny Flask backend + vanilla HTML/JS frontend that embeds nicely in a **Homarr** iFrame.  
It proxies Navidrome’s Subsonic API, serves cover art, and streams audio with **HTTP Range support** so seeking works.

> Works today: play/pause, back/next, random, seeking, volume, search (server API).  
> Still rough around the edges, but usable.

---

## Features (current)

- 🎵 Play/Pause, Back, Next
- 🔀 Random queue (fetches a batch from Navidrome)
- ⏱️ Click/drag **seek** (backend proxies ranges via `/rest/download`)
- 🔊 Volume with persisted setting
- 🔎 **Search API** (`/api/search?query=...`) returning up to 25 songs (UI uses top 5)

---

## Quick start

### 1) Clone & install

```bash
git clone https://github.com/<you>/<repo>.git /opt/navidrome-iframe
cd /opt/navidrome-iframe

# (optional) python venv
python3 -m venv .venv
. .venv/bin/activate

pip install -r requirements.txt
```

### 2) Create your env file (do **not** commit this)

`/opt/navidrome-iframe/webplayer.env`

```bash
export NAVIDROME_URL='https://your-navidrome.example.com'
export NAVIDROME_USER='changeme'
export NAVIDROME_PASS='changeme'
export PORT=5069
```

Lock it down:

```bash
chmod 600 /opt/navidrome-iframe/webplayer.env
```

### 3) Run it

```bash
. /opt/navidrome-iframe/webplayer.env
cd /opt/navidrome-iframe
python3 webplayer.py
```

You should see:

```
Running on http://127.0.0.1:5069
```

### 4) Add to Homarr

Create a **Website/iFrame tile** pointing at:

```
http://<server-host-or-tailscale-name>:5069/
```

---

## Start on boot (cron)

Add this to your `crontab -e`:

```cron
@reboot /bin/sh -lc 'sleep 15; . /opt/navidrome-iframe/webplayer.env; mkdir -p "$HOME/.logs"; cd /opt/navidrome-iframe; /usr/bin/python3 webplayer.py >> "$HOME/.logs/webplayer.log" 2>&1 &'
```

Manual restart (same env):

```bash
fuser -k 5069/tcp 2>/dev/null || pkill -f '/opt/navidrome-iframe/webplayer.py'
/bin/sh -lc '. /opt/navidrome-iframe/webplayer.env; cd /opt/navidrome-iframe; nohup /usr/bin/python3 webplayer.py >> "$HOME/.logs/webplayer.log" 2>&1 & disown'
```

---

## Environment variables

| Variable         | Description                     | Example                     |
| ---------------- | ------------------------------- | --------------------------- |
| `NAVIDROME_URL`  | Base URL to your Navidrome      | `https://music.example.com` |
| `NAVIDROME_USER` | Navidrome/Subsonic user         | `alice`                     |
| `NAVIDROME_PASS` | Navidrome/Subsonic **password** | `supersecret`               |
| `PORT`           | Flask listen port (optional)    | `5069`                      |

> The app also accepts `SUBSONIC_USER` / `SUBSONIC_PASSWORD` if you prefer those names.

---

## API the UI calls

- `GET /api/random/list?size=25` → `{ success, songs: [{id,title,artist,coverArt}] }`
- `GET /api/search?query=…` → `{ success, results: [...] }` (server hits `search3`)
- `GET /api/cover/:id` → cover image (proxied)
- `GET /api/stream/:id` → **Range-aware** audio stream (proxied to `/rest/download`)

---

## Repo layout

```
webplayer.py      # Flask backend (proxy + JSON APIs + static index)
index.html        # Frontend player (vanilla HTML/JS/CSS)
requirements.txt  # Flask, requests, flask-cors
.env.example      # Example env (placeholders only)
.gitignore        # ignores your real env + logs + caches
```

---

## Security & secrets

- Keep real credentials in **`webplayer.env`** (or any env file you source), not in Git.
- `.gitignore` already excludes common `.env` names + `webplayer.env`.
- If you ever committed secrets by accident, rotate them in Navidrome and purge the file from Git history.

---

## Troubleshooting

- **Clicking progress jumps to 0:00**  
  Your browser couldn’t seek; the backend must support **HTTP Range**.  
  This app proxies via `/rest/download` and forwards `Range`, returning `206 Partial Content`.  
  Sanity check:

  ```bash
  curl -I -H "Range: bytes=0-1" "http://127.0.0.1:5069/api/stream/<SONG_ID>"
  ```

  You should see `206` and `Accept-Ranges: bytes`.

- **Search returns empty**  
  Confirm your user has library access and Navidrome search is enabled. Try a short substring.

- **Port already in use**  
  `fuser -k 5069/tcp` and re-run.

- **Not sizing correctly in some Homarr tiles/monitors**  
  Known issue (see below). Resize the tile larger as a workaround.

---

## Known issues / current quirks

- 🧩 **Sizing/responsiveness** isn’t perfect on some monitors / Homarr tile sizes.
- ⏱️ **Some songs show duration as `∞:NaN`**. It mostly works, but some streams still report odd metadata.
- ⏭️ **Next button behavior** can feel like it “shuffles” rather than strictly going to the next intended track in certain states.
- 🔁 Browser autoplay policies may block autoplay until interaction.

---

## Roadmap / planned improvements

- 🌈 **Audio visualizer** (Web Audio API Analyser + canvas)
- 📐 **Responsive layout** for all Homarr tile sizes, clamp-based typography, better overflow handling
- 🎚️ Refined queue: _true_ next/previous, add-to-queue, clear queue
- 💾 Persist queue & position in `localStorage` so reloads resume where you left off
- 🎛️ Media Session API (lock-screen/notification controls + artwork)
- 🎨 Overall look & polish (button styling, micro-animations)
- 🧪 Better error toasts & loading states

---

## License

MIT (or choose your preferred license).

---

## Credits

- [Navidrome](https://www.navidrome.org/) for the excellent Subsonic-compatible server
- Homarr community for the dashboard where this lives ❤️
