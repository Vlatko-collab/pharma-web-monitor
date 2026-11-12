import json
import hashlib
import html
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, ElementTree

CONFIG_FILE = "config.json"
STATE_FILE = "state.json"
OUTPUT_FILE = "feed.xml"


def fetch_page(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 PharmaWebMonitor/1.0"
        },
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="ignore")


def load_json(filename, default):
    path = Path(filename)

    if not path.exists():
        return default

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def page_hash(content):
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def create_feed(events):
    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")

    SubElement(channel, "title").text = "Daily Pharma Intelligence Web Monitor"
    SubElement(channel, "description").text = (
        "Detected changes on monitored
