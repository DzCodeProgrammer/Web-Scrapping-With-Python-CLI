import os
import re
import json
import time
from urllib.request import urlopen, Request, urlretrieve
from urllib.error import URLError, HTTPError
from urllib.parse import urljoin
from html.parser import HTMLParser

# Regex untuk mendeteksi file tertentu
FILE_EXT_RE = re.compile(r"\.(pdf|zip|rar|exe|txt|docx|doc|xls|xlsx|pptx|ppt|csv|apk)$", re.I)


# ========================
# HTML PARSER NATIVE
# ========================
class FullParser(HTMLParser):
    def __init__(self, target_tags, target_attrs, base_url):
        super().__init__()
        self.target_tags = {t.lower() for t in target_tags}
        self.target_attrs = {a.lower() for a in target_attrs}
        self.base = base_url

        self.capturing = None
        self.text_results = []
        self.attr_results = []
        self.links = []
        self.images = []
        self.files = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs = dict(attrs)

        # Capture attribute values
        for name, val in attrs.items():
            if name.lower() in self.target_attrs:
                absolute = urljoin(self.base, val)
                self.attr_results.append({"tag": tag, "attr": name, "value": absolute})

                if name == "href":
                    self.links.append(absolute)
                    if FILE_EXT_RE.search(absolute):
                        self.files.append(absolute)

                if name == "src":
                    self.images.append(urljoin(self.base, val))

        # Capture text for target tags
        if tag in self.target_tags:
            self.capturing = tag

    def handle_endtag(self, tag):
        if tag == self.capturing:
            self.capturing = None

    def handle_data(self, data):
        if self.capturing:
            d = data.strip()
            if d:
                self.text_results.append(f"[{self.capturing}] {d}")


# ========================
# FETCH HTML
# ========================
def fetch_html(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(req, timeout=15) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="ignore")
    except Exception as e:
        raise RuntimeError(f"Error fetching URL: {e}")


# ========================
# DOWNLOAD FILE
# ========================
def download_file(url, folder):
    try:
        os.makedirs(folder, exist_ok=True)
        filename = os.path.basename(url.split("?")[0]) or str(int(time.time()))
        path = os.path.join(folder, filename)
        urlretrieve(url, path)
        return path
    except:
        return None


# ========================
# PROGRAM UTAMA
# ========================
def main():
    print("=== CLI Web Scraper ===")
    url = input("URL: ").strip()

    tags = input("Tags (comma, ex: h1,p,span): ").strip().split(",")
    attrs = input("Attributes (comma, ex: href,src): ").strip().split(",")

    download_images = input("Download images? (y/n): ").lower() == "y"
    download_files = input("Download files? (y/n): ").lower() == "y"

    print("\n[INFO] Fetching HTML...")
    html = fetch_html(url)

    parser = FullParser(tags, attrs, url)
    parser.feed(html)

    # === Print hasil ===
    print("\n[INFO] Extracted Text:")
    for t in parser.text_results:
        print(" -", t)

    print("\n[INFO] Attributes Found:")
    for a in parser.attr_results:
        print(f" - {a['tag']} | {a['attr']} | {a['value']}")

    # === Save JSON Output ===
    output = {
        "url": url,
        "text": parser.text_results,
        "attributes": parser.attr_results,
        "images": parser.images,
        "files": parser.files,
        "links": parser.links,
    }

    with open("scraped_output.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=4)

    print("\n[OK] Saved to scraped_output.json")

    # === Download Images & Files ===
    if download_images:
        print("\n[INFO] Downloading images...")
        for img in parser.images:
            saved = download_file(img, "images")
            print(" -", img, "->", saved)

    if download_files:
        print("\n[INFO] Downloading files...")
        for f in parser.files:
            saved = download_file(f, "files")
            print(" -", f, "->", saved)

    print("\n[DONE] Scraping complete.")


    # ========================
    # EXPORT VIEWER
    # ========================
    print("\n=== Export Output ===")
    print("1. Markdown (.md)")
    print("2. Text (.txt)")
    print("3. Word Compatible (.rtf)")
    print("0. Skip export")

    choice = input("Pilih format: ").strip()

    # Load JSON hasil scraping
    with open("scraped_output.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    # Build Markdown Content
    md = []
    md.append(f"# Scraped Result\n")
    md.append(f"**URL:** {data['url']}\n")

    md.append("## Extracted Text")
    for t in data["text"]:
        md.append(f"- {t}")

    md.append("\n## Attributes")
    for a in data["attributes"]:
        md.append(f"- **{a['tag']}** | {a['attr']} → {a['value']}")

    md.append("\n## Images")
    for img in data["images"]:
        md.append(f"- {img}")

    md.append("\n## Files")
    for fl in data["files"]:
        md.append(f"- {fl}")

    md_output = "\n".join(md)

    # === Save as Markdown ===
    if choice == "1":
        with open("scraped_output.md", "w", encoding="utf-8") as f:
            f.write(md_output)
        print("[OK] Saved as scraped_output.md")

    # === Save as TXT ===
    elif choice == "2":
        with open("scraped_output.txt", "w", encoding="utf-8") as f:
            f.write(md_output)
        print("[OK] Saved as scraped_output.txt")

    # === Save as RTF (Word readable) ===
    elif choice == "3":
        rtf_text = md_output.replace("\n", r"\par " + "\n")
        with open("scraped_output.rtf", "w", encoding="utf-8") as f:
            f.write("{\\rtf1\\ansi\n")
            f.write(rtf_text)
            f.write("\n}")
        print("[OK] Saved as scraped_output.rtf")

    elif choice == "0":
        print("Skipped export.")

    else:
        print("Invalid choice.")


# ========================
# RUN
# ========================
if __name__ == "__main__":
    main()
