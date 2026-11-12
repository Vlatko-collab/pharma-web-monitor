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
        "Detected changes on monitored pharma and healthcare websites"
    )
    SubElement(channel, "link").text = (
        "https://github.com/Vlatko-collab/pharma-web-monitor"
    )

    for event in events:
        item = SubElement(channel, "item")

        SubElement(item, "title").text = event["name"]
        SubElement(item, "link").text = event["url"]
        SubElement(item, "guid").text = event["guid"]
        SubElement(item, "pubDate").text = event["date"]
        SubElement(item, "description").text = event["description"]

    ElementTree(rss).write(
        OUTPUT_FILE,
        encoding="utf-8",
        xml_declaration=True,
    )


def main():
    config = load_json(CONFIG_FILE, {"sites": []})
    state = load_json(STATE_FILE, {})
    events = []

    for site in config.get("sites", []):
        name = site["name"]
        url = site["url"]

        print(f"Checking: {name} - {url}")

        try:
            content = fetch_page(url)
            current_hash = page_hash(content)
            previous_hash = state.get(url)

            if previous_hash is None:
                print(f"Initial snapshot created for {name}")

            elif previous_hash != current_hash:
                print(f"Change detected for {name}")

                now = datetime.now(timezone.utc)

                events.append(
                    {
                        "name": f"Website change detected: {name}",
                        "url": url,
                        "guid": hashlib.sha256(
                            f"{url}-{current_hash}".encode("utf-8")
                        ).hexdigest(),
                        "date": now.strftime(
                            "%a, %d %b %Y %H:%M:%S +0000"
                        ),
                        "description": (
                            f"A change was detected on {html.escape(name)}. "
                            f"Review the source page for new or updated content."
                        ),
                    }
                )

            state[url] = current_hash

        except Exception as error:
            print(f"ERROR checking {name}: {error}")

    save_json(STATE_FILE, state)
    create_feed(events)

    print(f"Finished. {len(events)} change(s) detected.")


if __name__ == "__main__":
    main()
