import json
import hashlib
import html
import re
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from html.parser import HTMLParser
from xml.etree.ElementTree import Element, SubElement, ElementTree


CONFIG_FILE = "config.json"
STATE_FILE = "state.json"
OUTPUT_FILE = "feed.xml"


def fetch_page(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 PharmaWebMonitor/2.0"
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


class LinkParser(HTMLParser):
    def __init__(self, base_url):
        super().__init__()
        self.base_url = base_url
        self.links = []

        self.current_href = None
        self.current_text = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            attrs_dict = dict(attrs)
            href = attrs_dict.get("href")

            if href:
                self.current_href = href
                self.current_text = []

    def handle_data(self, data):
        if self.current_href is not None:
            self.current_text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.current_href is not None:
            text = " ".join(self.current_text)
            text = re.sub(r"\s+", " ", text).strip()

            absolute_url = urllib.parse.urljoin(
                self.base_url,
                self.current_href
            )

            parsed = urllib.parse.urlparse(absolute_url)

            if parsed.scheme in ("http", "https"):
                self.links.append(
                    {
                        "title": text,
                        "url": absolute_url
                    }
                )

            self.current_href = None
            self.current_text = []


def extract_links(content, base_url):
    parser = LinkParser(base_url)

    try:
        parser.feed(content)
    except Exception:
        return []

    results = []
    seen = set()

    ignored_titles = {
        "",
        "home",
        "početna",
        "pocetna",
        "naslovna",
        "više",
        "vise",
        "opširnije",
        "opsirnije",
        "read more",
        "more"
    }

    ignored_extensions = (
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".svg",
        ".css",
        ".js",
        ".ico"
    )

    for link in parser.links:
        title = link["title"].strip()
        url = link["url"].strip()

        clean_title = title.lower()

        if clean_title in ignored_titles:
            continue

        if len(title) < 8:
            continue

        if url.lower().endswith(ignored_extensions):
            continue

        # ukloni anchor dio URL-a
        parsed = urllib.parse.urlparse(url)
        url = urllib.parse.urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                parsed.query,
                ""
            )
        )

        key = url

        if key in seen:
            continue

        seen.add(key)

        results.append(
            {
                "title": title[:300],
                "url": url
            }
        )

    return results


def create_feed(events):
    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")

    SubElement(
        channel,
        "title"
    ).text = "Daily Pharma Intelligence Web Monitor"

    SubElement(
        channel,
        "description"
    ).text = (
        "New or changed content detected on monitored "
        "pharma and healthcare websites"
    )

    SubElement(
        channel,
        "link"
    ).text = (
        "https://github.com/Vlatko-collab/pharma-web-monitor"
    )

    for event in events:
        item = SubElement(channel, "item")

        SubElement(
            item,
            "title"
        ).text = event["name"]

        SubElement(
            item,
            "link"
        ).text = event["url"]

        SubElement(
            item,
            "guid"
        ).text = event["guid"]

        SubElement(
            item,
            "pubDate"
        ).text = event["date"]

        SubElement(
            item,
            "description"
        ).text = event["description"]

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
            current_links = extract_links(content, url)

            site_state = state.get(url)

            # Kompatibilnost sa starim state.json formatom
            if isinstance(site_state, str):
                previous_hash = site_state
                previous_links = []

            elif isinstance(site_state, dict):
                previous_hash = site_state.get("hash")
                previous_links = site_state.get("links", [])

            else:
                previous_hash = None
                previous_links = []

            current_urls = {
                item["url"]: item
                for item in current_links
            }

            previous_urls = set(previous_links)

            if previous_hash is None:
                print(
                    f"Initial snapshot created for {name}: "
                    f"{len(current_links)} links stored."
                )

            elif previous_hash != current_hash:
                print(f"Change detected for {name}")

                new_urls = [
                    link_url
                    for link_url in current_urls
                    if link_url not in previous_urls
                ]

                # Ograniči broj novih rezultata sa jednog sajta.
                # Ovo sprečava da jedna velika izmjena menija
                # zatrpa cijeli Daily Pharma Intelligence izvještaj.
                new_urls = new_urls[:10]

                now = datetime.now(timezone.utc)

                if new_urls:
                    for new_url in new_urls:
                        item = current_urls[new_url]
                        title = item["title"]

                        print(
                            f"NEW CONTENT: {name} | "
                            f"{title} | {new_url}"
                        )

                        events.append(
                            {
                                "name": f"{name}: {title}",
                                "url": new_url,
                                "guid": hashlib.sha256(
                                    (
                                        f"{name}|{new_url}|"
                                        f"{current_hash}"
                                    ).encode("utf-8")
                                ).hexdigest(),
                                "date": now.strftime(
                                    "%a, %d %b %Y %H:%M:%S +0000"
                                ),
                                "description": (
                                    f"New content detected on "
                                    f"{html.escape(name)}: "
                                    f"{html.escape(title)}"
                                ),
                            }
                        )

                else:
                    # Stranica je promijenjena, ali nije pronađen
                    # novi direktni link. Zadržavamo fallback kako
                    # važna promjena ne bi potpuno nestala iz izvještaja.
                    print(
                        f"Page changed for {name}, "
                        f"but no new link was identified."
                    )

                    events.append(
                        {
                            "name": (
                                f"{name}: Website content changed"
                            ),
                            "url": url,
                            "guid": hashlib.sha256(
                                (
                                    f"{url}|{current_hash}"
                                ).encode("utf-8")
                            ).hexdigest(),
                            "date": now.strftime(
                                "%a, %d %b %Y %H:%M:%S +0000"
                            ),
                            "description": (
                                f"A change was detected on "
                                f"{html.escape(name)}, but no new "
                                f"direct content link was identified. "
                                f"Review the monitored page."
                            ),
                        }
                    )

            state[url] = {
                "hash": current_hash,
                "links": list(current_urls.keys())
            }

        except Exception as error:
            print(f"ERROR checking {name}: {error}")

    save_json(STATE_FILE, state)
    create_feed(events)

    print(
        f"Finished. {len(events)} new item(s) detected."
    )


if __name__ == "__main__":
    main()
