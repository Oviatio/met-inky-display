#!/usr/bin/env python3

import os
import sys
import random
import requests
from io import BytesIO

# --- VIRTUAL ENVIRONMENT ENFORCEMENT ---
# Adjust this to wherever your virtualenv lives (it must have inky and Pillow installed).
VENV_PYTHON = "/home/display/.virtualenvs/pimoroni/bin/python3"

if sys.executable != VENV_PYTHON:
    if os.path.exists(VENV_PYTHON):
        os.execl(VENV_PYTHON, VENV_PYTHON, *sys.argv)
    else:
        print(f"Error: Virtual environment not found at {VENV_PYTHON}")
        sys.exit(1)

# --- IMPORTS ---
try:
    from PIL import Image, ImageOps, ImageDraw, ImageFont
    from inky.auto import auto
except ImportError:
    print("Error: Inky or PIL not found. Ensure they are installed in the 'pimoroni' venv.")
    sys.exit(1)

# --- Configuration ---
# Verify these against https://collectionapi.metmuseum.org/public/collection/v1/departments
# 11 = European Paintings, 21 = Modern Art (17 was Medieval Art, not paintings)
DEPARTMENT_IDS = "11|21"
BASE_URL = "https://collectionapi.metmuseum.org/public/collection/v1"
OBJECTS_URL = f"{BASE_URL}/objects"
TIMEOUT = 20
MAX_ATTEMPTS = 15

session = requests.Session()
# The Met API sits behind Imperva, which 403s non-browser User-Agents from some hosts
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, image/*;q=0.8, */*;q=0.5",
    "Accept-Language": "en-US,en;q=0.9",
})


def get_json(url, **params):
    """GET a URL and return parsed JSON, raising on HTTP errors or timeouts."""
    resp = session.get(url, params=params or None, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def get_object_ids():
    """Returns all object IDs in the chosen departments.

    Uses /objects (not the paginated /v1.1/search, which caps at 100 results
    per page and 10,000 total) so the random pick covers the whole set.
    """
    data = get_json(OBJECTS_URL, departmentIds=DEPARTMENT_IDS)
    return data.get("objectIDs") or []


def get_random_artwork(object_ids):
    """Picks a random public-domain painting that has an image. Returns a dict or None."""
    obj_id = random.choice(object_ids)
    try:
        obj = get_json(f"{OBJECTS_URL}/{obj_id}")
    except (requests.RequestException, ValueError) as e:
        print(f"API Error on object {obj_id}: {e}")
        return None

    if not obj.get("isPublicDomain") or not obj.get("primaryImage"):
        return None
    if "painting" not in obj.get("classification", "").lower():
        return None

    return {
        "object_id": obj_id,
        "object_url": obj.get("objectURL"),
        "department": obj.get("department"),
        "url": obj["primaryImage"],
        "thumb": obj.get("primaryImageSmall") or obj["primaryImage"],
        "title": obj.get("title") or "Unknown Title",
        "artist": obj.get("artistDisplayName") or "Unknown Artist",
    }


def download_image(url):
    """Downloads an image into RAM. Returns a PIL Image or None."""
    try:
        resp = session.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content))
        img.load()  # force decode now so corrupt files fail here
        return img.convert("RGB")
    except (requests.RequestException, OSError) as e:
        print(f"Image error: {e}")
        return None


def ellipsize(draw, text, font, max_w):
    """Trims text with a trailing '...' until it fits within max_w pixels."""
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(text + "...", font=font) > max_w:
        text = text[:-1]
    return text.rstrip() + "..."


def wrap_text(draw, text, font, max_w, max_lines):
    """Word-wraps text to max_w pixels, ellipsizing the last line if it overflows max_lines."""
    lines, current = [], ""
    words = text.split()
    for i, word in enumerate(words):
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            current = trial
            continue
        if current:
            lines.append(current)
        current = word
        if len(lines) == max_lines - 1:
            # Last allowed line: everything remaining goes here, then gets trimmed
            current = " ".join(words[i:])
            break
    lines.append(current)
    lines[-1] = ellipsize(draw, lines[-1], font, max_w)
    return lines or [""]


def add_overlay(img, title, artist):
    """Adds a high-contrast plaque to the bottom left."""
    draw = ImageDraw.Draw(img)
    width, height = img.size

    try:
        font_main = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
        font_sub = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except OSError:
        font_main = font_sub = ImageFont.load_default()

    pad = 15
    max_text_w = int(width * 0.7) - 2 * pad  # plaque never covers more than ~70% of width

    # Wrap the title by pixel width (max 2 lines), ellipsize the artist to one line
    title_lines = wrap_text(draw, title, font_main, max_text_w, max_lines=2)
    artist_line = wrap_text(draw, artist, font_sub, max_text_w, max_lines=1)

    title_lh, artist_lh = 24, 20
    box_height = pad + len(title_lines) * title_lh + artist_lh + pad // 2
    text_w = max(draw.textlength(t, font=font_main) for t in title_lines)
    text_w = max(text_w, draw.textlength(artist_line[0], font=font_sub))
    box_width = int(text_w) + 2 * pad

    # Draw plaque background, sized to the text
    draw.rectangle([0, height - box_height, box_width, height], fill="black")

    # Draw text
    y = height - box_height + pad // 2
    for line in title_lines:
        draw.text((pad, y), line, fill="white", font=font_main)
        y += title_lh
    draw.text((pad, y), artist_line[0], fill="white", font=font_sub)

    return img


def main():
    try:
        display = auto()
        width, height = display.resolution
    except RuntimeError:
        print("Display not found.")
        return

    try:
        object_ids = get_object_ids()
    except (requests.RequestException, ValueError) as e:
        print(f"Could not fetch object list: {e}")
        return
    if not object_ids:
        print("No objects returned for the selected departments.")
        return

    for attempt in range(1, MAX_ATTEMPTS + 1):
        art = get_random_artwork(object_ids)
        if not art:
            continue

        # Check orientation on the small image to avoid downloading big portraits
        thumb = download_image(art["thumb"])
        if thumb is None:
            continue
        if thumb.width <= thumb.height:
            print(f"Skipping portrait ({thumb.width}x{thumb.height}). Retrying...")
            continue

        # Landscape confirmed, now fetch the full-size image
        img = download_image(art["url"])
        if img is None:
            continue

        print(f"Found landscape: {art['title']} ({img.width}x{img.height})")

        # 1. Crop/resize to the display resolution
        img = ImageOps.fit(img, (width, height), centering=(0.5, 0.5))

        # 2. Add metadata overlay
        img = add_overlay(img, art["title"], art["artist"])

        # 3. Push to display
        print(f"Updating Inky with: {art['title']}")
        display.set_image(img, saturation=0.5)
        display.show()
        print("Update Complete. No disk writes performed.")
        return

    print(f"Failed to find a suitable landscape painting after {MAX_ATTEMPTS} attempts.")


if __name__ == "__main__":
    main()
