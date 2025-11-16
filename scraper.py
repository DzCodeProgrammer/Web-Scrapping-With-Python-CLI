# tk_native_scraper_full.py
import os
import re
import csv
import json
import time
import threading
from urllib.request import urlopen, Request, urlretrieve
from urllib.error import URLError, HTTPError
from urllib.parse import urljoin
from html.parser import HTMLParser
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# ---------------------------
# Config: file extensions classifying "downloadable files"
FILE_EXT_RE = re.compile(r"\.(pdf|zip|rar|exe|txt|docx|doc|xls|xlsx|pptx|ppt|csv|apk)$", re.I)

# ---------------------------
# HTML parser - captures text for chosen tags, attributes, links, images, files
class FullParser(HTMLParser):
    def __init__(self, target_tags, target_attrs, base_url):
        super().__init__()
        self.target_tags = {t.lower() for t in target_tags}
        self.target_attrs = {a.lower() for a in target_attrs}
        self.base = base_url

        self.capturing_tag = None
        self.text_results = []      # list of "[tag] content"
        self.attr_results = []      # list of {"tag":tag, "attr":name, "value":value}
        self.links = []             # hrefs
        self.images = []            # src
        self.files = []             # downloadable files

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs = dict(attrs)

        # capture attributes requested
        for name, val in attrs.items():
            if name.lower() in self.target_attrs:
                val_abs = urljoin(self.base, val)
                self.attr_results.append({"tag": tag, "attr": name.lower(), "value": val_abs})
                # if attr is href/src classify link/image/file too
                if name.lower() == "href":
                    self.links.append(val_abs)
                    if FILE_EXT_RE.search(val_abs):
                        self.files.append(val_abs)
                if name.lower() in ("src",):
                    self.images.append(urljoin(self.base, val))

        # begin capturing text for chosen tags
        if tag in self.target_tags:
            self.capturing_tag = tag

    def handle_endtag(self, tag):
        if self.capturing_tag == tag:
            self.capturing_tag = None

    def handle_data(self, data):
        if self.capturing_tag:
            txt = data.strip()
            if txt:
                self.text_results.append(f"[{self.capturing_tag}] {txt}")

# ---------------------------
# Helper network functions (native urllib) with basic error handling
def fetch_html(url, timeout=15):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="ignore")
    except (HTTPError, URLError) as e:
        raise RuntimeError(f"Network error: {e}") from e

def safe_url_join(base, link):
    try:
        return urljoin(base, link)
    except:
        return link

def download_file(url, folder):
    try:
        os.makedirs(folder, exist_ok=True)
        name = os.path.basename(url.split("?")[0]) or str(int(time.time()))
        path = os.path.join(folder, name)
        urlretrieve(url, path)
        return path
    except Exception as e:
        return None

# ---------------------------
# GUI Application
class ScraperApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Native Tk Scraper — Full Features")
        self.root.geometry("980x680")
        self.root.minsize(900, 600)

        # state
        self.dark_mode = True
        self.thread = None
        self.stop_flag = False

        # layout: top control area, tabs below
        self._make_top_controls()
        self._make_tabs()
        self._apply_theme()

    # top controls
    def _make_top_controls(self):
        frame = ttk.Frame(self.root)
        frame.pack(fill="x", padx=10, pady=8)

        ttk.Label(frame, text="URL:").grid(row=0, column=0, sticky="w")
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(frame, textvariable=self.url_var, width=80)
        self.url_entry.grid(row=0, column=1, columnspan=6, padx=6, sticky="w")

        ttk.Label(frame, text="Tags (comma):").grid(row=1, column=0, sticky="w", pady=(6,0))
        self.tags_var = tk.StringVar(value="h1,h2,h3,p,span,title")
        self.tags_entry = ttk.Entry(frame, textvariable=self.tags_var, width=40)
        self.tags_entry.grid(row=1, column=1, sticky="w", pady=(6,0), padx=6)

        ttk.Label(frame, text="Attrs (comma):").grid(row=1, column=2, sticky="w", padx=(8,0), pady=(6,0))
        self.attrs_var = tk.StringVar(value="href,src,class,id")
        self.attrs_entry = ttk.Entry(frame, textvariable=self.attrs_var, width=30)
        self.attrs_entry.grid(row=1, column=3, sticky="w", pady=(6,0), padx=6)

        # options
        self.chk_images = tk.BooleanVar(value=True)
        self.chk_files = tk.BooleanVar(value=True)
        ttk.Checkbutton(frame, text="Download Images", variable=self.chk_images).grid(row=1, column=4, padx=6, sticky="w")
        ttk.Checkbutton(frame, text="Collect Files", variable=self.chk_files).grid(row=1, column=5, padx=6, sticky="w")

        # buttons
        self.start_btn = ttk.Button(frame, text="Start Scrape", command=self.start_scrape)
        self.start_btn.grid(row=0, column=7, padx=6)
        self.cancel_btn = ttk.Button(frame, text="Stop", command=self.stop_scrape, state="disabled")
        self.cancel_btn.grid(row=1, column=7, padx=6)
        ttk.Button(frame, text="Save All", command=self.save_all).grid(row=0, column=8, padx=6)

        # theme toggle
        self.theme_btn = ttk.Button(frame, text="Toggle Light/Dark", command=self.toggle_theme)
        self.theme_btn.grid(row=1, column=8, padx=6)

    # tabs: Results, Attributes, Images/Files, Logs
    def _make_tabs(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(0,10))

        # Results tab (text content)
        self.tab_results = ttk.Frame(self.notebook)
        self.results_txt = tk.Text(self.tab_results, wrap="word", bg="#0f1115", fg="#e6eef6")
        self.results_txt.pack(fill="both", expand=True, side="left")
        self.results_scroll = ttk.Scrollbar(self.tab_results, command=self.results_txt.yview)
        self.results_scroll.pack(side="right", fill="y")
        self.results_txt.config(yscrollcommand=self.results_scroll.set)
        self.notebook.add(self.tab_results, text="Results (Text)")

        # Attributes tab
        self.tab_attrs = ttk.Frame(self.notebook)
        self.attrs_tree = ttk.Treeview(self.tab_attrs, columns=("tag","attr","value"), show="headings")
        self.attrs_tree.heading("tag", text="Tag")
        self.attrs_tree.heading("attr", text="Attribute")
        self.attrs_tree.heading("value", text="Value / URL")
        self.attrs_tree.pack(fill="both", expand=True, side="left")
        self.attrs_scroll = ttk.Scrollbar(self.tab_attrs, command=self.attrs_tree.yview)
        self.attrs_scroll.pack(side="right", fill="y")
        self.attrs_tree.config(yscrollcommand=self.attrs_scroll.set)
        self.notebook.add(self.tab_attrs, text="Attributes")

        # Images & Files tab
        self.tab_media = ttk.Frame(self.notebook)
        self.media_listbox = tk.Listbox(self.tab_media)
        self.media_listbox.pack(fill="both", expand=True, side="left")
        media_btn_frame = ttk.Frame(self.tab_media)
        media_btn_frame.pack(side="right", fill="y", padx=6)
        ttk.Button(media_btn_frame, text="Download Selected Image", command=self.download_selected_image).pack(pady=6)
        ttk.Button(media_btn_frame, text="Download All Images", command=self.download_all_images).pack(pady=6)
        ttk.Button(media_btn_frame, text="Open Images Folder", command=self.open_images_folder).pack(pady=6)
        self.notebook.add(self.tab_media, text="Images & Files")

        # Logs tab with progress bar
        self.tab_logs = ttk.Frame(self.notebook)
        self.log_txt = tk.Text(self.tab_logs, height=10, bg="#0b0b0b", fg="#dfefff")
        self.log_txt.pack(fill="both", expand=True)
        self.progress = ttk.Progressbar(self.tab_logs, orient="horizontal", mode="determinate")
        self.progress.pack(fill="x", padx=6, pady=6)
        self.notebook.add(self.tab_logs, text="Logs / Progress")

    # theme toggle
    def _apply_theme(self):
        if self.dark_mode:
            bg = "#0b0f14"
            fg = "#e6eef6"
            txt_bg = "#0f1115"
        else:
            bg = "#f2f6fa"
            fg = "#0b1622"
            txt_bg = "#ffffff"

        self.root.configure(bg=bg)
        # set textbox bg/fg
        self.results_txt.configure(bg=txt_bg, fg=fg, insertbackground=fg)
        self.log_txt.configure(bg=txt_bg, fg=fg, insertbackground=fg)
        # listbox
        self.media_listbox.configure(bg=txt_bg, fg=fg)
        # treeview style
        s = ttk.Style()
        if self.dark_mode:
            s.configure("Treeview", background="#0f1115", foreground="#e6eef6", fieldbackground="#0f1115")
        else:
            s.configure("Treeview", background="#fff", foreground="#000", fieldbackground="#fff")

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self._apply_theme()

    # start/stop scraping
    def start_scrape(self):
        url = self.url_var.get().strip()
        if not url.startswith("http"):
            messagebox.showerror("Error", "Masukkan URL yang valid (http/https).")
            return
        if self.thread and self.thread.is_alive():
            messagebox.showwarning("Running", "Scrape sedang berjalan.")
            return

        # reset UI
        self.results_txt.delete("1.0", tk.END)
        self.attrs_tree.delete(*self.attrs_tree.get_children())
        self.media_listbox.delete(0, tk.END)
        self.log_txt.delete("1.0", tk.END)
        self.progress["value"] = 0
        self.stop_flag = False
        self.cancel_btn.config(state="normal")
        self.start_btn.config(state="disabled")

        # prepare args
        tags = [t.strip().lower() for t in self.tags_var.get().split(",") if t.strip()]
        attrs = [a.strip().lower() for a in self.attrs_var.get().split(",") if a.strip()]
        download_images = bool(self.chk_images.get())
        collect_files = bool(self.chk_files.get())

        # start background thread
        self.thread = threading.Thread(target=self._worker_scrape, args=(self.url_var.get(), tags, attrs, download_images, collect_files), daemon=True)
        self.thread.start()

    def stop_scrape(self):
        self.stop_flag = True
        self.log("Stop requested. Thread will terminate after current step.")

    # background worker
    def _worker_scrape(self, url, tags, attrs, download_images, collect_files):
        try:
            self.log(f"[INFO] Fetching: {url}")
            html = fetch_html(url)
        except Exception as e:
            self.log(f"[ERROR] {e}")
            self._finish_scrape()
            return

        parser = FullParser(tags, attrs, url)
        parser.feed(html)

        # update UI with text results
        self._append_results(parser.text_results)

        # update attributes tree
        for a in parser.attr_results:
            self.attrs_tree.insert("", "end", values=(a["tag"], a["attr"], a["value"]))

        # links
        for l in parser.links:
            # add to media list if file-like
            if collect_files and FILE_EXT_RE.search(l):
                parser.files.append(l)

        # images
        for img in parser.images:
            self.media_listbox.insert("end", f"IMG: {img}")

        # files
        for f in parser.files:
            self.media_listbox.insert("end", f"FILE: {f}")

        total_items = max(1, len(parser.images) + len(parser.files))
        processed = 0
        self.progress["maximum"] = total_items

        # download images if requested
        images_folder = os.path.join(os.getcwd(), "scraped_images")
        files_folder = os.path.join(os.getcwd(), "scraped_files")

        if download_images:
            for img in parser.images:
                if self.stop_flag: break
                self.log(f"Downloading image: {img}")
                local = download_file_if_possible(img, images_folder)
                if local:
                    self.log(f"Saved image -> {local}")
                else:
                    self.log(f"[WARN] Failed to download: {img}")
                processed += 1
                self._set_progress(processed)
        else:
            processed += len(parser.images)
            self._set_progress(processed)

        if collect_files:
            for f in parser.files:
                if self.stop_flag: break
                self.log(f"Downloading file: {f}")
                local = download_file_if_possible(f, files_folder)
                if local:
                    self.log(f"Saved file -> {local}")
                else:
                    self.log(f"[WARN] Failed to download: {f}")
                processed += 1
                self._set_progress(processed)
        else:
            processed += len(parser.files)
            self._set_progress(processed)

        # done
        self.log("[DONE] Scrape completed.")
        self._finish_scrape()

    # helpers to safely update UI from thread
    def _append_results(self, items):
        def append():
            if not items:
                self.results_txt.insert(tk.END, "[INFO] No text items found for chosen tags.\n")
            else:
                for it in items:
                    self.results_txt.insert(tk.END, it + "\n\n")
        self.root.after(0, append)

    def _set_progress(self, value):
        self.root.after(0, lambda: self.progress.step(value - self.progress["value"]))

    def log(self, text):
        ts = time.strftime("%H:%M:%S")
        def append(): 
            self.log_txt.insert(tk.END, f"[{ts}] {text}\n")
            self.log_txt.see(tk.END)
        self.root.after(0, append)

    def _finish_scrape(self):
        def finish():
            self.cancel_btn.config(state="disabled")
            self.start_btn.config(state="normal")
            self.progress["value"] = self.progress["maximum"]
        self.root.after(0, finish)

    # Download helpers invoked by UI buttons
    def download_selected_image(self):
        sel = self.media_listbox.curselection()
        if not sel:
            messagebox.showinfo("Info", "Pilih item di tab Images & Files.")
            return
        item = self.media_listbox.get(sel[0])
        url = item.split(":",1)[1].strip()
        folder = filedialog.askdirectory(title="Pilih folder simpan")
        if not folder:
            return
        self.log(f"Downloading selected: {url}")
        dest = download_file_if_possible(url, folder)
        if dest:
            messagebox.showinfo("Saved", f"Saved to {dest}")
        else:
            messagebox.showwarning("Fail", "Gagal mendownload.")

    def download_all_images(self):
        folder = filedialog.askdirectory(title="Pilih folder simpan (all)")
        if not folder:
            return
        # gather urls
        items = self.media_listbox.get(0, "end")
        count = 0
        for it in items:
            typ, url = it.split(":",1)
            url = url.strip()
            if typ.strip() == "IMG":
                count += 1
                self.log(f"Downloading {url}")
                download_file_if_possible(url, folder)
        messagebox.showinfo("Done", f"Attempted download of {count} images. Check log for status.")

    def open_images_folder(self):
        folder = os.path.join(os.getcwd(), "scraped_images")
        if not os.path.exists(folder):
            messagebox.showinfo("Info", "Folder images belum ada.")
            return
        try:
            if os.name == "nt":
                os.startfile(folder)
            else:
                # mac / linux
                import subprocess
                subprocess.Popen(["open" if os.uname().sysname == "Darwin" else "xdg-open", folder])
        except Exception:
            messagebox.showinfo("Info", f"Folder: {folder}")

    # Save aggregated results to CSV/JSON/TXT
    def save_all(self):
        # collect
        text = self.results_txt.get("1.0", tk.END).strip().splitlines()
        attrs = [self.attrs_tree.item(i)["values"] for i in self.attrs_tree.get_children()]
        media = list(self.media_listbox.get(0, "end"))

        ftypes = [("JSON file","*.json"),("CSV file","*.csv"),("Text file","*.txt")]
        file = filedialog.asksaveasfilename(defaultextension=".json", filetypes=ftypes)
        if not file:
            return
        if file.endswith(".json"):
            out = {"text": text, "attributes":[{"tag":v[0],"attr":v[1],"value":v[2]} for v in attrs], "media": media}
            with open(file,"w",encoding="utf-8") as f:
                json.dump(out, f, indent=2, ensure_ascii=False)
        elif file.endswith(".csv"):
            with open(file,"w",newline="",encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["type","content"])
                for t in text:
                    writer.writerow(["text", t])
                for v in attrs:
                    writer.writerow(["attr", "|".join([str(x) for x in v])])
                for m in media:
                    writer.writerow(["media", m])
        else:
            with open(file,"w",encoding="utf-8") as f:
                f.write("=== TEXT ===\n")
                for t in text: f.write(t+"\n")
                f.write("\n=== ATTRS ===\n")
                for v in attrs: f.write("|".join([str(x) for x in v])+"\n")
                f.write("\n=== MEDIA ===\n")
                for m in media: f.write(m+"\n")
        messagebox.showinfo("Saved", f"Hasil disimpan ke: {file}")

# ---------------------------
# helper to safely try downloading and return local path or None
def download_file_if_possible(url, folder):
    try:
        os.makedirs(folder, exist_ok=True)
        url_abs = url
        filename = os.path.basename(url_abs.split("?")[0]) or f"file_{int(time.time())}"
        dest = os.path.join(folder, filename)
        # try direct retrieve
        urlretrieve(url_abs, dest)
        return dest
    except Exception as e:
        # log only
        return None

# ---------------------------
# main runner
def main():
    root = tk.Tk()
    app = ScraperApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
