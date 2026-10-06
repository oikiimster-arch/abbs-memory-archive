#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ABBS Forum Thread Parser & Archiver
Extracts original author chronicles, full community discussions, metadata, and historical photos.
"""

import os
import re
import json
import shutil
from pathlib import Path

def parse_abbs_htm(htm_path, output_dir):
    """
    Parses an ABBS .htm thread file saved with IE/Firefox.
    Extracts author, time, floor, quoted text, content, and local images.
    """
    with open(htm_path, 'r', encoding='gbk', errors='ignore') as f:
        html = f.read()

    # Determine files folder
    base_name = os.path.splitext(os.path.basename(htm_path))[0]
    files_folder = os.path.join(os.path.dirname(htm_path), f"{base_name}.files")
    if not os.path.exists(files_folder):
        files_folder = os.path.join(os.path.dirname(htm_path), f"{base_name}_files")

    # Extract thread title
    m_title = re.search(r'<title>(.*?)</title>', html, re.I)
    title = m_title.group(1).replace('- ABBS 论坛', '').strip() if m_title else "未命名文献"

    # Split into post table rows
    parts = re.split(r'<TR class=(?:odd|even)>', html, flags=re.I)
    if len(parts) <= 1:
        parts = re.split(r'<TR[^>]*class=[\'"]?(?:odd|even)[\'"]?[^>]*>', html, flags=re.I)

    floors = []
    op_author = None
    target_img_dir = os.path.join(output_dir, "images")
    os.makedirs(target_img_dir, exist_ok=True)

    for i, part in enumerate(parts[1:], start=1):
        # Extract author
        m_author = re.search(r'<TD[^>]*width=[\'"]?150[\'"]?[^>]*>.*?<B>([^<]+)</B>', part, re.DOTALL | re.I)
        author = m_author.group(1).strip() if m_author else f"User_{i}"

        if i == 1 and not op_author:
            op_author = author

        # Extract role/level
        m_role = re.search(r'<B>[^<]+</B>\s*<BR>\s*([^<]+)', part, re.I)
        role = m_role.group(1).strip() if m_role else "会员"
        if "发贴:" in role:
            role = role.split("发贴:")[0].strip()

        # Extract post timestamp
        m_time = re.search(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})', part)
        post_time = m_time.group(1).strip() if m_time else ""

        # Extract content TD (the right cell width="100%")
        content_cell = ""
        m_cell = re.search(r'<TD[^>]*width=[\'"]?100%[\'"]?[^>]*>(.*?)</TD>', part, re.DOTALL | re.I)
        if m_cell:
            content_cell = m_cell.group(1)
        else:
            tds = re.findall(r'<TD[^>]*>(.*?)</TD>', part, re.DOTALL | re.I)
            content_cell = tds[1] if len(tds) >= 2 else part

        # Strip header icons
        if post_time and post_time in content_cell:
            idx = content_cell.find(post_time)
            rest = content_cell[idx + len(post_time):]
            rest = re.sub(r'<A[^>]*><IMG[^>]*></A>', '', rest, flags=re.I)
            content_cell = rest

        # Extract quotes: e.g. [quote] or "XXX wrote:"
        quotes = []
        quote_matches = re.finditer(r'<TABLE[^>]*border=1[^>]*>.*?<TD[^>]*>(.*?)</TD>.*?</TABLE>', content_cell, re.DOTALL | re.I)
        for qm in quote_matches:
            q_text = re.sub(r'<[^>]+>', ' ', qm.group(1)).strip()
            quotes.append(q_text)

        # Extract images
        img_srcs = re.findall(r'<IMG[^>]*?src=[\"\']([^\"\']+\.(?:jpg|jpeg|png|gif))[\"\']', content_cell, re.I | re.DOTALL)
        copied_images = []
        for src in img_srcs:
            fname = os.path.basename(src)
            if any(icon in fname.lower() for icon in ['post.gif', 'icon_', 'pixel.gif', 'title.gif', 'crossbg.gif', 'logo', 'button', 'star']):
                continue
            
            src_disk_path = None
            if os.path.exists(files_folder):
                cand = os.path.join(files_folder, fname)
                if os.path.exists(cand):
                    src_disk_path = cand
            
            if src_disk_path and os.path.isfile(src_disk_path):
                dest_path = os.path.join(target_img_dir, fname)
                if not os.path.exists(dest_path):
                    shutil.copy2(src_disk_path, dest_path)
                copied_images.append(f"images/{fname}")

        # Clean text
        def replace_img(match):
            img_tag = match.group(0)
            m_s = re.search(r'src=[\"\']([^\"\']+)[\"\']', img_tag, re.I)
            if m_s:
                fn = os.path.basename(m_s.group(1))
                if any(icon in fn.lower() for icon in ['post.gif', 'icon_', 'pixel.gif', 'title.gif', 'crossbg.gif', 'logo', 'button', 'star']):
                    return ''
                return f'<div class="abbs-post-photo-wrap"><img src="images/{fn}" class="abbs-post-photo" alt="ABBS 历史图记" loading="lazy" /></div>'
            return ''

        cleaned_html = re.sub(r'<IMG[^>]+>', replace_img, content_cell, flags=re.I | re.DOTALL)
        cleaned_html = re.sub(r'<script[^>]*>.*?</script>', '', cleaned_html, flags=re.DOTALL | re.I)
        cleaned_html = re.sub(r'<A\s+href=[^>]*>\s*</A>', '', cleaned_html, flags=re.I)
        cleaned_html = re.sub(r'(?:<BR>\s*){3,}', '<br><br>', cleaned_html, flags=re.I)
        cleaned_html = cleaned_html.strip()

        is_op = (author == op_author)

        floors.append({
            "floor": i,
            "author": author,
            "role": role,
            "time": post_time,
            "is_op": is_op,
            "images": copied_images,
            "content": cleaned_html
        })

    result = {
        "title": title,
        "op_author": op_author,
        "total_floors": len(floors),
        "op_floors": len([f for f in floors if f["is_op"]]),
        "reply_floors": len([f for f in floors if not f["is_op"]]),
        "floors": floors
    }

    json_path = os.path.join(output_dir, "thread.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    total_imgs = len(os.listdir(target_img_dir))
    print(f"Parsed {len(floors)} floors (OP: {result['op_floors']}, Replies: {result['reply_floors']}). Copied {total_imgs} photos to {target_img_dir}. Output: {json_path}")
    return result

if __name__ == "__main__":
    source = "/Users/kensu/A-Kensu Studio Folder/X-Private/F-旅游日志/人说山西好风光/人说山西好风光 1/人说山西好风光 - ABBS 论坛.htm"
    out = "/Users/kensu/A-Kensu Studio Folder/Web/archive_poc/shanxi_1"
    parse_abbs_htm(source, out)
