import urllib.request, re, sys, json

REEL_URL = "https://www.instagram.com/reel/DVbTkfTE98X/"

headers = {
    "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uaTxt.php)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

req = urllib.request.Request(REEL_URL, headers=headers)
with urllib.request.urlopen(req, timeout=20) as resp:
    html = resp.read().decode("utf-8", errors="replace")

print(f"Page fetched: {len(html)} chars")

# Extract og:image
patterns = [
    r'property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
    r'content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
    r'"thumbnail_url"\s*:\s*"([^"]+)"',
    r'<meta[^>]*og:image[^>]*content=["\']([^"\']+)["\']',
]

found_url = None
for p in patterns:
    m = re.search(p, html)
    if m:
        raw = m.group(1)
        found_url = raw.replace("\\u0026", "&").replace("&amp;", "&").replace("&#038;", "&")
        print(f"THUMBNAIL_URL={found_url}")
        break

if not found_url:
    # Dump all meta tags for debugging
    metas = re.findall(r'<meta[^>]+>', html)
    for meta in metas:
        if 'image' in meta.lower() or 'og:' in meta.lower():
            print("META:", meta[:300])

# Extract og:description (caption)
cap_m = re.search(r'property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']', html)
if not cap_m:
    cap_m = re.search(r'content=["\']([^"\']+)["\'][^>]+property=["\']og:description["\']', html)
caption = cap_m.group(1).replace("&quot;", '"').replace("&#039;", "'").replace("&amp;", "&") if cap_m else "N/A"
print(f"CAPTION={caption}")

# Save for main script
info = {"thumbnail_url": found_url, "caption": caption}
with open("reel_info.json", "w") as f:
    json.dump(info, f, indent=2)
print("Saved to reel_info.json")
