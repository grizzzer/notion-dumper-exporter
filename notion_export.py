"""
Notion public page exporter.
Recursively fetches all nested pages from a public Notion URL
and produces a single HTML document with embedded images.
"""

import requests
import urllib.parse
import re
import sys
import os
import time
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional


HTML_HEAD = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{TITLE}}</title>
<style>
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    max-width: 900px;
    margin: 0 auto;
    padding: 20px 40px;
    line-height: 1.7;
    color: #1a1a1a;
    background: #fff;
  }
  h1 { font-size: 2em; border-bottom: 2px solid #e0e0e0; padding-bottom: 8px; }
  h2 { font-size: 1.6em; margin-top: 2em; border-bottom: 1px solid #eee; }
  h3 { font-size: 1.3em; margin-top: 1.5em; }
  h4 { font-size: 1.1em; margin-top: 1.2em; }
  img { max-width: 100%; height: auto; border-radius: 4px; margin: 8px 0; }
  figure { margin: 16px 0; }
  figcaption { font-size: 0.85em; color: #666; text-align: center; }
  pre {
    background: #1e1e1e;
    color: #d4d4d4;
    padding: 16px;
    border-radius: 6px;
    overflow-x: auto;
    font-size: 0.9em;
    line-height: 1.5;
  }
  code { font-family: 'Consolas', 'Monaco', monospace; }
  p > code {
    background: #f0f0f0;
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 0.9em;
  }
  blockquote {
    border-left: 4px solid #ccc;
    margin: 16px 0;
    padding: 8px 16px;
    color: #444;
    background: #fafafa;
  }
  .callout {
    display: flex;
    gap: 12px;
    background: #f7f6f3;
    border-radius: 6px;
    padding: 16px;
    margin: 12px 0;
  }
  .callout-icon { font-size: 1.3em; }
  .column-list { display: flex; gap: 16px; }
  .column { flex: 1; }
  hr { border: none; border-top: 1px solid #e0e0e0; margin: 24px 0; }
  table { border-collapse: collapse; margin: 16px 0; width: 100%; }
  th, td { border: 1px solid #ddd; padding: 8px 12px; text-align: left; }
  th { background: #f5f5f5; font-weight: 600; }
  details { margin: 8px 0; }
  summary { cursor: pointer; font-weight: 500; }
  a { color: #2196F3; text-decoration: none; }
  a:hover { text-decoration: underline; }
  section.page { margin-bottom: 16px; }
  section.depth-1 { border-top: 3px solid #333; padding-top: 24px; margin-top: 32px; }
  section.depth-2 { border-top: 1px solid #ccc; padding-top: 16px; margin-top: 24px; }
  /* --- TOC sidebar --- */
  #toc {
    position: fixed;
    top: 0; left: 0;
    width: 280px;
    height: 100vh;
    background: #fafafa;
    border-right: 1px solid #e0e0e0;
    display: flex;
    flex-direction: column;
    z-index: 100;
    transition: transform .25s ease;
    font-size: 13px;
  }
  #toc.collapsed { transform: translateX(-280px); }
  #toc.collapsed + #content { margin-left: 0; }
  .toc-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 16px;
    border-bottom: 1px solid #e0e0e0;
    font-weight: 700;
    font-size: 15px;
    flex-shrink: 0;
  }
  #toc-toggle {
    background: none; border: none; font-size: 18px;
    cursor: pointer; padding: 2px 6px; border-radius: 4px;
    color: #555;
  }
  #toc-toggle:hover { background: #eee; }
  /* floating open button when collapsed */
  #toc-open {
    display: none;
    position: fixed;
    top: 12px; left: 12px;
    z-index: 101;
    background: #fff;
    border: 1px solid #ddd;
    border-radius: 6px;
    font-size: 20px;
    padding: 4px 10px;
    cursor: pointer;
    box-shadow: 0 2px 8px rgba(0,0,0,.1);
  }
  #toc-open:hover { background: #f5f5f5; }
  #toc.collapsed ~ #toc-open { display: block; }
  #toc-body {
    overflow-y: auto;
    flex: 1;
    padding: 8px 0;
  }
  .toc-item {
    display: block;
    padding: 4px 16px;
    color: #333;
    text-decoration: none;
    border-left: 3px solid transparent;
    line-height: 1.4;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .toc-item:hover { background: #eee; }
  .toc-item.active { border-left-color: #2196F3; color: #2196F3; font-weight: 600; }
  .toc-d0 { padding-left: 16px; font-weight: 600; }
  .toc-d1 { padding-left: 28px; }
  .toc-d2 { padding-left: 40px; font-size: 12px; }
  .toc-d3 { padding-left: 52px; font-size: 12px; }
  .toc-d4 { padding-left: 64px; font-size: 11px; }
  .toc-d5 { padding-left: 76px; font-size: 11px; }
  #content { margin-left: 280px; transition: margin-left .25s ease; }
  @media print {
    #toc, #toc-open { display: none !important; }
    #content { margin-left: 0 !important; }
    body { max-width: none; padding: 10px; }
    section.depth-1 { page-break-before: always; }
    pre { white-space: pre-wrap; word-wrap: break-word; }
  }
  @media (max-width: 900px) {
    #toc { width: 260px; }
    #toc.collapsed { transform: translateX(-260px); }
    #content { margin-left: 260px; }
    #toc.collapsed + #content { margin-left: 0; }
  }
</style>
</head>
<body>
"""

HTML_FOOT = """
<button id="toc-open" aria-label="Open TOC">&#x2630;</button>
<script>
(function(){
  var toc = document.getElementById('toc');
  var toggle = document.getElementById('toc-toggle');
  var openBtn = document.getElementById('toc-open');
  toggle.addEventListener('click', function(){ toc.classList.add('collapsed'); });
  openBtn.addEventListener('click', function(){ toc.classList.remove('collapsed'); });

  // highlight active TOC item on scroll
  var items = document.querySelectorAll('.toc-item');
  var targets = [];
  items.forEach(function(a){
    var id = a.getAttribute('href').slice(1);
    var el = document.getElementById(id);
    if(el) targets.push({link: a, el: el});
  });
  var raf;
  function onScroll(){
    if(raf) return;
    raf = requestAnimationFrame(function(){
      raf = null;
      var scrollY = window.scrollY + 80;
      var active = targets[0];
      for(var i = 0; i < targets.length; i++){
        if(targets[i].el.offsetTop <= scrollY) active = targets[i];
        else break;
      }
      items.forEach(function(a){ a.classList.remove('active'); });
      if(active) {
        active.link.classList.add('active');
        // scroll TOC to keep active item visible
        var body = document.getElementById('toc-body');
        var top = active.link.offsetTop - body.offsetTop;
        if(top < body.scrollTop || top > body.scrollTop + body.clientHeight - 30){
          body.scrollTop = top - body.clientHeight / 3;
        }
      }
    });
  }
  window.addEventListener('scroll', onScroll, {passive:true});
  onScroll();
})();
</script>
"""


@dataclass
class Block:
    id: str
    type: str
    properties: dict = field(default_factory=dict)
    format: dict = field(default_factory=dict)
    content: list = field(default_factory=list)
    space_id: str = ""
    parent_id: str = ""
    collection_id: str = ""
    view_ids: list = field(default_factory=list)


class NotionExporter:
    def __init__(self, root_url: str, download_images: bool = True):
        self.root_url = root_url
        self.download_images = download_images
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        self.base_domain = self._extract_domain(root_url)
        self.root_page_id = self._extract_page_id(root_url)
        self.visited_pages = set()
        self.image_cache = {}
        self.all_blocks = {}
        self.page_order = []

    def _extract_domain(self, url: str) -> str:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def _extract_page_id(self, url: str) -> str:
        path = urllib.parse.urlparse(url).path
        raw = path.rstrip("/").split("-")[-1]
        if len(raw) == 32:
            return f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}"
        return raw

    def _api_url(self, endpoint: str) -> str:
        return f"{self.base_domain}/api/v3/{endpoint}"

    def fetch_page_blocks(self, page_id: str) -> dict[str, Block]:
        blocks = {}
        cursor = {"stack": []}
        chunk_num = 0

        while True:
            payload = {
                "page": {"id": page_id},
                "limit": 100,
                "cursor": cursor,
                "chunkNumber": chunk_num,
                "verticalColumns": False,
            }

            try:
                resp = self.session.post(self._api_url("loadPageChunk"), json=payload, timeout=30)
                resp.raise_for_status()
            except requests.RequestException as e:
                print(f"  [!] Failed to fetch page {page_id}: {e}", file=sys.stderr)
                break

            data = resp.json()
            record_map = data.get("recordMap", {})
            raw_blocks = record_map.get("block", {})

            if not raw_blocks:
                break

            for bid, bdata in raw_blocks.items():
                v = bdata.get("value", {}).get("value", bdata.get("value", {}))
                if not v:
                    continue
                block = Block(
                    id=bid,
                    type=v.get("type", "unknown"),
                    properties=v.get("properties", {}),
                    format=v.get("format", {}),
                    content=v.get("content", []),
                    space_id=v.get("space_id", ""),
                    parent_id=v.get("parent_id", ""),
                    collection_id=v.get("collection_id", ""),
                    view_ids=v.get("view_ids", []),
                )
                blocks[bid] = block

            new_cursor = data.get("cursor", {})
            if not new_cursor.get("stack") or new_cursor == cursor:
                break
            cursor = new_cursor
            chunk_num += 1
            time.sleep(0.05)

        return blocks

    def _parse_record_blocks(self, record_map: dict) -> dict[str, Block]:
        blocks = {}
        for bid, bdata in record_map.get("block", {}).items():
            v = bdata.get("value", {}).get("value", bdata.get("value", {}))
            if not v:
                continue
            blocks[bid] = Block(
                id=bid,
                type=v.get("type", "unknown"),
                properties=v.get("properties", {}),
                format=v.get("format", {}),
                content=v.get("content", []),
                space_id=v.get("space_id", ""),
                parent_id=v.get("parent_id", ""),
                collection_id=v.get("collection_id", ""),
            )
        return blocks

    def _fetch_toggle_children(self, block_id: str, space_id: str) -> dict[str, Block]:
        """Fetch a toggle block's children via loadCachedPageChunks (they are not
        included in the page's block tree)."""
        payload = {
            "requests": [
                {
                    "page": {"id": block_id, "spaceId": space_id},
                    "cursor": {"stack": []},
                    "verticalColumns": False,
                }
            ]
        }
        try:
            resp = self.session.post(self._api_url("loadCachedPageChunks"), json=payload, timeout=30)
            resp.raise_for_status()
            return self._parse_record_blocks(resp.json().get("recordMap", {}))
        except requests.RequestException as e:
            print(f"  [!] Failed to fetch toggle children {block_id}: {e}", file=sys.stderr)
            return {}

    def _fetch_collection_rows(self, collection_id: str, view_id: str, space_id: str) -> dict[str, Block]:
        """Fetch rows of an embedded collection view (database) via queryCollection."""
        payload = {
            "clientType": "notion_app",
            "source": {"type": "collection", "id": collection_id, "spaceId": space_id},
            "collectionView": {"id": view_id, "spaceId": space_id},
            "loader": {
                "reducers": {"collection_group_results": {"type": "results", "limit": 100}},
                "sort": [],
                "searchQuery": "",
                "archiveStatus": "NON_ARCHIVED",
                "userTimeZone": "Asia/Jakarta",
            },
        }
        try:
            resp = self.session.post(self._api_url("queryCollection"), json=payload, timeout=30)
            resp.raise_for_status()
            return self._parse_record_blocks(resp.json().get("recordMap", {}))
        except requests.RequestException as e:
            print(f"  [!] Failed to fetch collection {collection_id}: {e}", file=sys.stderr)
            return {}

    def _expand_lazy_content(self, page_blocks: dict[str, Block]):
        """Backfill toggle children and collection view rows for a page's blocks."""
        space_id = next((b.space_id for b in page_blocks.values() if b.space_id), "")
        # --- toggles (recursive) ---
        queue = [b for b in page_blocks.values() if b.type == "toggle"]
        processed = set()
        while queue:
            tb = queue.pop(0)
            if tb.id in processed:
                continue
            processed.add(tb.id)
            if tb.content and all(self.all_blocks.get(cid) for cid in tb.content):
                # children already fetched; queue nested toggles
                for cid in tb.content:
                    c = self.all_blocks.get(cid) or page_blocks.get(cid)
                    if c and c.type == "toggle":
                        queue.append(c)
                continue
            new_blocks = self._fetch_toggle_children(tb.id, tb.space_id or space_id)
            time.sleep(0.1)
            for bid, nb in new_blocks.items():
                if bid not in self.all_blocks:
                    self.all_blocks[bid] = nb
                    page_blocks.setdefault(bid, nb)
            if new_blocks:
                tb.content = [cid for cid in new_blocks if new_blocks[cid].parent_id == tb.id] or list(new_blocks.keys())
            for cid in tb.content:
                c = new_blocks.get(cid)
                if c and c.type == "toggle":
                    queue.append(c)
        # --- any block whose referenced children are missing (e.g. callouts) ---
        for _ in range(3):
            pending = []
            for b in list(page_blocks.values()):
                missing_kids = [cid for cid in b.content if cid not in self.all_blocks]
                if missing_kids:
                    pending.append(b)
            if not pending:
                break
            for b in pending:
                new_blocks = self._fetch_toggle_children(b.id, b.space_id or space_id)
                time.sleep(0.1)
                for bid, nb in new_blocks.items():
                    self.all_blocks.setdefault(bid, nb)
                    page_blocks.setdefault(bid, nb)
        # --- collection views ---
        for b in list(page_blocks.values()):
            if b.type not in ("collection_view", "collection_view_page"):
                continue
            view_ids = b.view_ids or b.format.get("collection_view_ids", []) or [None]
            rows = {}
            if b.collection_id:
                for vid in view_ids[:1]:
                    rows = self._fetch_collection_rows(b.collection_id, vid, b.space_id or space_id)
                    time.sleep(0.1)
                    if rows:
                        break
            row_pages = [rb for rb in rows.values() if rb.type == "page" and rb.parent_id == b.collection_id]
            b.content = [rb.id for rb in row_pages]
            for rb in row_pages:
                self.all_blocks.setdefault(rb.id, rb)
                page_blocks.setdefault(rb.id, rb)
                self.crawl(rb.id)

    def crawl(self, page_id: str = None, depth: int = 0):
        if page_id is None:
            page_id = self.root_page_id

        if page_id in self.visited_pages:
            return
        self.visited_pages.add(page_id)

        blocks = self.fetch_page_blocks(page_id)
        self.all_blocks.update(blocks)

        page_block = blocks.get(page_id)
        if page_block:
            title = self._get_text(page_block.properties.get("title", []))
            indent = "  " * depth
            print(f"{indent}[page] {title}")
            self.page_order.append(page_id)

        self._expand_lazy_content(blocks)

        if page_block and page_block.content:
            for child_id in page_block.content:
                child = blocks.get(child_id)
                if child and child.type == "page":
                    self.crawl(child_id, depth + 1)
                    time.sleep(0.05)

    def _get_text(self, title_array) -> str:
        if not title_array:
            return ""
        parts = []
        for segment in title_array:
            if isinstance(segment, list) and len(segment) > 0:
                parts.append(str(segment[0]))
        return "".join(parts)

    def _get_rich_html(self, title_array) -> str:
        if not title_array:
            return ""
        parts = []
        for segment in title_array:
            if not isinstance(segment, list) or len(segment) == 0:
                continue
            text = str(segment[0]).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            text = text.replace("\n", "<br>")

            if len(segment) > 1 and isinstance(segment[1], list):
                for fmt in segment[1]:
                    if not isinstance(fmt, list) or not fmt:
                        continue
                    code = fmt[0]
                    if code == "b":
                        text = f"<strong>{text}</strong>"
                    elif code == "i":
                        text = f"<em>{text}</em>"
                    elif code == "s":
                        text = f"<del>{text}</del>"
                    elif code == "c":
                        text = f"<code>{text}</code>"
                    elif code == "a" and len(fmt) > 1:
                        href = fmt[1].replace('"', "&quot;")
                        text = f'<a href="{href}">{text}</a>'
                    elif code == "h" and len(fmt) > 1:
                        color = fmt[1]
                        if "_background" in color:
                            bg = color.replace("_background", "")
                            text = f'<span style="background-color:{bg};">{text}</span>'
                        else:
                            text = f'<span style="color:{color};">{text}</span>'
                    elif code == "_":
                        text = f"<u>{text}</u>"
            parts.append(text)
        return "".join(parts)

    def _collect_image_tasks(self):
        tasks = []
        for bid, block in self.all_blocks.items():
            if block.type != "image":
                continue
            source = ""
            src_prop = block.properties.get("source", [])
            if src_prop and isinstance(src_prop[0], list):
                source = src_prop[0][0]
            if not source:
                source = block.format.get("display_source", "")
            if source:
                tasks.append((source, bid, block.space_id))
        return tasks

    def _download_single_image(self, source: str, block_id: str, space_id: str) -> tuple:
        encoded_src = urllib.parse.quote(source, safe="")
        img_url = (
            f"{self.base_domain}/image/{encoded_src}"
            f"?table=block&id={block_id}&spaceId={space_id}&width=1600"
        )
        try:
            resp = requests.get(img_url, timeout=20, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            if resp.status_code == 200:
                ct = resp.headers.get("Content-Type", "image/png")
                ext = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif",
                       "image/webp": ".webp", "image/svg+xml": ".svg"}.get(ct, ".png")
                fname = f"{block_id.replace('-', '')}{ext}"
                fpath = os.path.join(self.images_dir, fname)
                with open(fpath, "wb") as f:
                    f.write(resp.content)
                return (f"{source}|{block_id}", f"images/{fname}")
        except Exception:
            pass
        return (f"{source}|{block_id}", "")

    def download_all_images(self):
        tasks = self._collect_image_tasks()
        total = len(tasks)
        if total == 0:
            print("  No images to download.")
            return

        print(f"  Downloading {total} images (8 concurrent)...")
        done = 0
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {
                pool.submit(self._download_single_image, src, bid, sid): (src, bid)
                for src, bid, sid in tasks
            }
            for future in as_completed(futures):
                cache_key, data_uri = future.result()
                self.image_cache[cache_key] = data_uri
                done += 1
                if done % 20 == 0 or done == total:
                    print(f"  [{done}/{total}] images downloaded")

    def _get_cached_image(self, source: str, block_id: str) -> str:
        return self.image_cache.get(f"{source}|{block_id}", "")

    def _render_block(self, block: Block) -> str:
        t = block.type
        props = block.properties
        fmt = block.format

        if t == "text":
            html = self._get_rich_html(props.get("title", []))
            if not html:
                return "<br>"
            return f"<p>{html}</p>"

        elif t in ("header", "sub_header", "sub_sub_header"):
            level = {"header": "h2", "sub_header": "h3", "sub_sub_header": "h4"}[t]
            text = self._get_rich_html(props.get("title", []))
            return f"<{level}>{text}</{level}>"

        elif t == "image":
            source = ""
            src_prop = props.get("source", [])
            if src_prop and isinstance(src_prop[0], list):
                source = src_prop[0][0]
            if not source:
                source = fmt.get("display_source", "")

            if source and self.download_images:
                data_uri = self._get_cached_image(source, block.id)
                if data_uri:
                    caption = self._get_text(props.get("caption", []))
                    cap_html = f"<figcaption>{caption}</figcaption>" if caption else ""
                    return f'<figure><img src="{data_uri}" style="max-width:100%;">{cap_html}</figure>'
            return ""

        elif t == "code":
            code_text = self._get_text(props.get("title", []))
            lang = self._get_text(props.get("language", []))
            escaped = code_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            return f'<pre><code class="language-{lang}">{escaped}</code></pre>'

        elif t == "bulleted_list":
            text = self._get_rich_html(props.get("title", []))
            children = self._render_children(block)
            if children:
                return f"<ul><li>{text}{children}</li></ul>"
            return f"<ul><li>{text}</li></ul>"

        elif t == "numbered_list":
            text = self._get_rich_html(props.get("title", []))
            children = self._render_children(block)
            if children:
                return f"<ol><li>{text}{children}</li></ol>"
            return f"<ol><li>{text}</li></ol>"

        elif t == "to_do":
            text = self._get_rich_html(props.get("title", []))
            checked = props.get("checked", [["No"]])[0][0] == "Yes"
            check = "☑" if checked else "☐"
            return f"<p>{check} {text}</p>"

        elif t == "toggle":
            text = self._get_rich_html(props.get("title", []))
            children = self._render_children(block)
            return f"<details><summary>{text}</summary>{children}</details>"

        elif t == "callout":
            text = self._get_rich_html(props.get("title", []))
            icon = fmt.get("page_icon", "")
            plain_title = re.sub(r"<[^>]+>", "", text)
            children_html = self._render_children(block)
            plain_children = re.sub(r"<[^>]+>", "", children_html).strip()
            # avoid duplicating text that already lives in the callout title
            if plain_children and plain_children in plain_title:
                children_html = ""
            body = text + children_html
            return f'<div class="callout"><span class="callout-icon">{icon}</span><div>{body}</div></div>'

        elif t == "quote":
            text = self._get_rich_html(props.get("title", []))
            return f"<blockquote>{text}</blockquote>"

        elif t == "divider":
            return "<hr>"

        elif t == "bookmark":
            link = self._get_text(props.get("link", []))
            title = self._get_text(props.get("title", [])) or link
            if link:
                return f'<p><a href="{link}">{title}</a></p>'
            return ""

        elif t == "video":
            source = self._get_text(props.get("source", []))
            if not source:
                source = fmt.get("display_source", "")
            if source:
                return f'<p><a href="{source}">[Video: {source}]</a></p>'
            return ""

        elif t == "embed":
            source = self._get_text(props.get("source", []))
            if not source:
                source = fmt.get("display_source", "")
            if source:
                return f'<p><a href="{source}">[Embed: {source}]</a></p>'
            return ""

        elif t == "table_of_contents":
            return ""

        elif t == "column_list":
            children = self._render_children(block)
            return f'<div class="column-list">{children}</div>'

        elif t == "column":
            children = self._render_children(block)
            ratio = fmt.get("column_ratio", 0.5)
            width = int(ratio * 100)
            return f'<div class="column" style="width:{width}%;">{children}</div>'

        elif t == "table":
            return self._render_table(block)

        elif t == "equation":
            expr = self._get_text(props.get("title", []))
            return f"<p><code>{expr}</code></p>"

        elif t == "file":
            source = self._get_text(props.get("source", []))
            title = self._get_text(props.get("title", [])) or "file"
            return f'<p>[File: {title}]</p>'

        elif t == "page":
            return ""

        elif t in ("collection_view", "collection_view_page"):
            parts = []
            for row_id in block.content:
                row = self.all_blocks.get(row_id)
                if not row:
                    continue
                title = self._get_text(row.properties.get("title", []))
                anchor = row_id.replace("-", "")
                icon = row.format.get("page_icon", "")
                parts.append(f'<li><a href="#{anchor}">{icon} {title}</a></li>')
            if parts:
                return f"<ul>{''.join(parts)}</ul>"
            return ""

        return ""

    def _render_children(self, block: Block) -> str:
        if not block.content:
            return ""
        return self._render_block_ids(block.content)

    def _render_block_ids(self, ids: list) -> str:
        """Render a sequence of block ids, merging consecutive numbered_list
        blocks into a single <ol> so numbering doesn't restart at 1."""
        parts = []
        ol_run = []
        def flush_ol():
            if ol_run:
                parts.append("<ol>" + "".join(f"<li>{i}</li>" for i in ol_run) + "</ol>")
                ol_run.clear()
        for child_id in ids:
            child = self.all_blocks.get(child_id)
            if not child or child.type == "page":
                continue
            if child.type == "numbered_list":
                text = self._get_rich_html(child.properties.get("title", []))
                inner = self._render_block_ids(child.content or [])
                ol_run.append(text + inner)
                continue
            flush_ol()
            parts.append(self._render_block(child))
        flush_ol()
        return "\n".join(parts)

    def _render_table(self, block: Block) -> str:
        if not block.content:
            return ""
        rows_html = []
        for i, row_id in enumerate(block.content):
            row = self.all_blocks.get(row_id)
            if not row:
                continue
            props = row.properties
            cells = []
            for key in sorted(props.keys()):
                if key.startswith("\\") or key == "title":
                    continue
                cells.append(self._get_rich_html(props[key]))
            tag = "th" if i == 0 else "td"
            cells_html = "".join(f"<{tag}>{c}</{tag}>" for c in cells)
            rows_html.append(f"<tr>{cells_html}</tr>")
        return f'<table border="1" cellpadding="4" cellspacing="0">{"".join(rows_html)}</table>'

    def _render_page(self, page_id: str, depth: int = 1) -> str:
        block = self.all_blocks.get(page_id)
        if not block:
            return ""

        title = self._get_text(block.properties.get("title", []))
        heading_level = min(depth, 6)
        icon = block.format.get("page_icon", "")
        if icon and (icon.startswith("http://") or icon.startswith("https://")):
            icon_html = f'<img src="{icon}" style="width:1.2em;height:1.2em;vertical-align:middle;margin-right:4px;">'
        elif icon:
            icon_html = f"{icon} "
        else:
            icon_html = ""

        anchor = page_id.replace("-", "")
        parts = [f'<h{heading_level} id="{anchor}">{icon_html}{title}</h{heading_level}>']

        if block.content:
            rendered_ids = [cid for cid in block.content
                            if self.all_blocks.get(cid) and self.all_blocks[cid].type != "page"]
            body = self._render_block_ids(rendered_ids)
            if body:
                parts.append(body)

        return "\n".join(parts)

    def _build_toc(self) -> str:
        items = []
        for page_id in self.page_order:
            block = self.all_blocks.get(page_id)
            if not block:
                continue
            depth = self._get_page_depth(page_id)
            title = self._get_text(block.properties.get("title", []))
            icon = block.format.get("page_icon", "")
            if icon and (icon.startswith("http://") or icon.startswith("https://")):
                icon = ""
            anchor = page_id.replace("-", "")
            indent = depth - 1
            items.append(
                f'<a href="#{anchor}" class="toc-item toc-d{min(indent, 5)}"'
                f' data-depth="{indent}">{icon + " " if icon else ""}{title}</a>'
            )
        return (
            '<nav id="toc">'
            '<div class="toc-header">'
            '<span class="toc-title">Contents</span>'
            '<button id="toc-toggle" aria-label="Toggle TOC">&#x2630;</button>'
            '</div>'
            '<div id="toc-body">' + "\n".join(items) + '</div>'
            '</nav>'
        )

    def export_html(self, output_path: str):
        out_dir = os.path.dirname(os.path.abspath(output_path)) or "."
        self.images_dir = os.path.join(out_dir, "images")
        os.makedirs(self.images_dir, exist_ok=True)

        print("\n[1/3] Crawling pages...")
        self.crawl()
        print(f"\nFound {len(self.page_order)} pages, {len(self.all_blocks)} total blocks")

        print("[2/3] Downloading images...")
        self.download_all_images()

        print("[3/3] Rendering HTML...")
        root_block = self.all_blocks.get(self.root_page_id)
        root_title = self._get_text(root_block.properties.get("title", [])) if root_block else "Export"

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(HTML_HEAD.replace("{{TITLE}}", root_title))
            f.write(self._build_toc())
            f.write('<main id="content">\n')

            for i, page_id in enumerate(self.page_order):
                block = self.all_blocks.get(page_id)
                if not block:
                    continue
                depth = self._get_page_depth(page_id)
                rendered = self._render_page(page_id, depth)
                if rendered:
                    f.write(f'<section class="page depth-{depth}">{rendered}</section>\n')

                if (i + 1) % 50 == 0:
                    print(f"  [{i+1}/{len(self.page_order)}] pages rendered")

            f.write('</main>\n')
            f.write(HTML_FOOT)
            f.write("</body>\n</html>\n")

        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        img_count = len([v for v in self.image_cache.values() if v])
        print(f"\nDone! Saved to {output_path} ({size_mb:.1f} MB)")
        print(f"  Pages: {len(self.page_order)}")
        print(f"  Images: {img_count}")

    def _get_page_depth(self, page_id: str) -> int:
        depth = 1
        current = page_id
        seen = set()
        while current and current != self.root_page_id and current not in seen:
            seen.add(current)
            block = self.all_blocks.get(current)
            if block and block.parent_id:
                parent = self.all_blocks.get(block.parent_id)
                if parent and parent.type == "page":
                    depth += 1
                    current = block.parent_id
                else:
                    break
            else:
                break
        return depth


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    if len(sys.argv) < 2:
        print("Usage: python notion_export.py <notion_url> [output.html]")
        sys.exit(1)

    url = sys.argv[1]
    output = sys.argv[2] if len(sys.argv) > 2 else "export.html"

    exporter = NotionExporter(url)
    exporter.export_html(output)


if __name__ == "__main__":
    main()
