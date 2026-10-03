"""Anonymous public avatar downloads, bounded decoding and a local daily cache."""

import io
import json
import logging
import time
import urllib.request
from urllib.parse import urlsplit

MAX_BYTES = 2 * 1024 * 1024
CACHE_SECONDS = 24 * 60 * 60
IMAGE_HOSTS = {f"i{i}.hdslb.com" for i in range(4)}


def avatar_url(value):
    if not isinstance(value, str):
        return ""
    if value.startswith("//"):
        value = "https:" + value
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return ""
    if parsed.scheme not in ("http", "https") or parsed.hostname not in IMAGE_HOSTS:
        return ""
    if parsed.username or parsed.password or port not in (None, 80, 443):
        return ""
    return "https://" + parsed.netloc + parsed.path


class AvatarRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not avatar_url(newurl):
            raise ValueError("Unexpected avatar redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _read(url, limit):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.build_opener(AvatarRedirect()).open(request, timeout=8) as response:
        body = response.read(limit + 1)
    if len(body) > limit:
        raise ValueError("Avatar response too large")
    return body


def load_avatar(root, uid, url=""):
    from PIL import Image, ImageOps
    uid = int(uid)
    if uid <= 0:
        raise ValueError("Invalid avatar UID")
    path = root / "cache" / "avatars" / f"{uid}.png"
    if path.exists() and time.time() - path.stat().st_mtime < CACHE_SECONDS:
        with Image.open(path) as image:
            return image.convert("RGBA")
    url = avatar_url(url)
    if not url:
        body = json.loads(_read(
            f"https://api.live.bilibili.com/live_user/v1/Master/info?uid={uid}", MAX_BYTES
        ))
        url = avatar_url(((body.get("data") or {}).get("info") or {}).get("face"))
    if not url:
        raise ValueError("Public avatar unavailable")
    try:
        with Image.open(io.BytesIO(_read(url, MAX_BYTES))) as image:
            if image.width * image.height > 4096 * 4096:
                raise ValueError("Avatar dimensions too large")
            thumbnail = ImageOps.fit(image.convert("RGB"), (128, 128), Image.Resampling.LANCZOS)
    except Image.DecompressionBombError as exc:
        raise ValueError("Avatar dimensions too large") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    thumbnail.save(temporary, format="PNG")
    temporary.replace(path)
    return thumbnail.convert("RGBA")


def round_avatar(image, size):
    from PIL import Image, ImageDraw, ImageOps
    image = ImageOps.fit(image, (size, size), Image.Resampling.LANCZOS).convert("RGBA")
    mask = Image.new("L", (size, size))
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    image.putalpha(mask)
    return image


class AvatarLoader:
    def __init__(self, root, dispatcher):
        self.root, self.dispatcher = root, dispatcher
        self.images, self.pending, self.failures = {}, set(), {}

    def request(self, uid, url, callback):
        if not isinstance(uid, int) or uid <= 0:
            return
        if uid in self.images:
            callback(self.images[uid])
            return
        if uid in self.pending or time.monotonic() < self.failures.get(uid, 0):
            return
        self.pending.add(uid)

        def finish(image):
            self.pending.discard(uid)
            if image is not None:
                self.images[uid] = image
                callback(image)
            else:
                self.failures[uid] = time.monotonic() + 300

        def download():
            try:
                image = load_avatar(self.root, uid, url)
            except (OSError, ValueError, KeyError, TypeError):
                logging.info("Public avatar unavailable for UID %s; keeping placeholder", uid)
                image = None
            self.dispatcher.post(lambda: finish(image))

        self.dispatcher.submit(download)
