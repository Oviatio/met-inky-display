# Met Art Inky Display

Shows a random public-domain painting from [The Metropolitan Museum of Art](https://www.metmuseum.org/) on a Raspberry Pi with a [Pimoroni Inky](https://shop.pimoroni.com/collections/inky) e-ink display, with a small title/artist plaque in the bottom-left corner.

Each run:

1. Fetches all object IDs from the Met's Open Access API for the configured departments (European Paintings and Modern Art by default).
2. Picks random objects until it finds a public-domain **painting** with an image.
3. Checks the thumbnail and skips portrait-orientation images (to avoid downloading large files it will crop away).
4. Downloads the full image into memory, crops/resizes it to the display resolution, and overlays the title and artist.
5. Pushes it to the display. Nothing is written to disk.

## Requirements

- Raspberry Pi with a supported Inky display (detected automatically via `inky.auto`)
- Python 3.9+
- [`inky`](https://github.com/pimoroni/inky), `Pillow`, and `requests`
- DejaVu fonts (`/usr/share/fonts/truetype/dejavu/`); falls back to the default PIL font if missing

## Setup

```bash
python3 -m venv ~/.virtualenvs/pimoroni
source ~/.virtualenvs/pimoroni/bin/activate
pip install -r requirements.txt
```

The script re-launches itself inside a virtualenv. Edit `VENV_PYTHON` at the top of `met_scrape.py` to point at yours (the default is `/home/display/.virtualenvs/pimoroni/bin/python3`).

## Usage

```bash
python3 met_scrape.py
```

To refresh on a schedule, add a cron entry (e-ink panels shouldn't be refreshed more than every few minutes; daily is plenty):

```cron
0 7 * * * /home/<user>/.virtualenvs/pimoroni/bin/python3 /home/<user>/met_scrape.py
```

## Configuration

Edit the constants near the top of `met_scrape.py`:

| Setting | Default | Meaning |
|---|---|---|
| `DEPARTMENT_IDS` | `"11\|21"` | Met department IDs, pipe-separated. See the [departments endpoint](https://collectionapi.metmuseum.org/public/collection/v1/departments). |
| `TIMEOUT` | `20` | HTTP timeout in seconds |
| `MAX_ATTEMPTS` | `15` | Random picks to try before giving up |

## Notes

- The Met API is behind a CDN that can return 403 for non-browser User-Agents, so the script sends a browser-style User-Agent.
- Only objects flagged `isPublicDomain` by the Met are used. See the [Met Open Access policy](https://www.metmuseum.org/policies/open-access).
