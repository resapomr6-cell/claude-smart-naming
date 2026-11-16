#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Agent Output Governance — 智能体输出治理引擎

治理 AI 智能体（Claude Code 等）产生的一堆文件：乱命名、重复、临时、散乱。
全生命周期：生成(命名) → 组织(分类) → 归档(回溯) → 清理(删除)

用法：
    python govern.py scan [目录]      扫描并生成治理报告（只读）
    python govern.py rename [目录]    重命名乱命名文件（读内容提标题）
    python govern.py organize [目录]  按分类目录整理文件
    python govern.py archive [目录]   归档长期未动的文件
    python govern.py cleanup [目录]   清理临时/垃圾文件
    python govern.py dedup [目录]     识别并删除重复文件

所有命令默认 --dry-run（只预览不修改），加 --apply 才真正执行。
"""

import argparse
import hashlib
import os
import re
import shutil
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional

# ---------- 规则定义 ----------

# 绝对乱命名：这些词作为文件名主体，任何扩展名都是乱命名
ABSOLUTE_BAD = [
    re.compile(r'^(output|result|out|res)[_\-]?\d*$', re.I),
    re.compile(r'^(temp|tmp)[_\-]?\d*$', re.I),
    re.compile(r'^(untitled|未命名|新建|无标题)[_\-]?\d*$', re.I),
    re.compile(r'^new[_\-]?\d*$', re.I),
]

# hash/时间戳乱码：只在「文档类」文件才算乱命名（数据/缓存里 hash 可能是合法 ID）
DOC_EXTENSIONS = {'.md', '.txt', '.docx', '.doc', '.tex', '.rst'}
HASH_LIKE = [
    re.compile(r'^\d{8}[_\-][a-f0-9]{6,}$', re.I),   # 20261116_a1b2c3
    re.compile(r'^[a-f0-9]{8,}$', re.I),              # 纯 hash
    re.compile(r'^\d{10,}$'),                          # 纯时间戳
    re.compile(r'^[a-z0-9]{6,}_\d{8}$', re.I),        # hash_20261116
]

# 临时 / 垃圾文件
TEMP_PATTERNS = [
    re.compile(r'\.(tmp|temp|bak|swp|swo)$', re.I),
    re.compile(r'\.(log|pyc|pyo)$', re.I),
    re.compile(r'~$'),
    re.compile(r'^\.DS_Store$'),
    re.compile(r'^\.#'),
    re.compile(r'^~\$'),
    re.compile(r'^\._'),
]

# 版本冗余：明确的「副本」信号。不含正常的 v1/v2 版本管理或 final 约定（易误判）。
VERSION_PATTERNS = [
    re.compile(r'copy[_\s\-]*(\d+)?', re.I),            # copy, copy 2
    re.compile(r'\((\d+)\)\s*$'),                        # (1) (2)
    re.compile(r'(副本|备份|修订)$'),                     # 中文副本词
]

# 分类目录 → 匹配规则（按顺序，命中即归类）
CATEGORY_RULES = [
    ('报告', [re.compile(r'报告|总结|report|review|summary', re.I),
              re.compile(r'\.pdf$', re.I)]),
    ('笔记', [re.compile(r'笔记|note|reading|思考|想法|idea', re.I)]),
    ('工具', [re.compile(r'\.(py|sh|js|bat|ps1|rb|go|rs)$', re.I),
              re.compile(r'script|脚本|tool', re.I)]),
    ('数据', [re.compile(r'\.(csv|json|xlsx?|parquet|db|sqlite)$', re.I)]),
    ('图片', [re.compile(r'\.(png|jpe?g|gif|svg|webp|ico)$', re.I)]),
    ('文档', [re.compile(r'\.(md|txt|docx?|tex)$', re.I)]),
]

# 归档阈值：超过 N 天未修改，视为「可归档」
ARCHIVE_DAYS = 30

# 治理引擎自身与仓库文件，永不参与归档/整理
PROTECTED = {'govern.py', 'README.md', 'LICENSE', 'CLAUDE.md', '.gitignore'}


# ---------- 工具函数 ----------

def is_bad_name(path: Path) -> bool:
    """文件名主体是否乱命名（去掉扩展名后匹配）。"""
    stem = Path(path.name).stem
    if any(p.search(stem) for p in ABSOLUTE_BAD):
        return True
    if path.suffix.lower() in DOC_EXTENSIONS:
        return any(p.search(stem) for p in HASH_LIKE)
    return False


def is_temp(name: str) -> bool:
    return any(p.search(name) for p in TEMP_PATTERNS)


def has_version_junk(name: str) -> bool:
    stem = Path(name).stem
    return any(p.search(stem) for p in VERSION_PATTERNS)


def sanitize(title: str, max_len: int = 30) -> str:
    """把标题清洗成合法文件名。"""
    title = re.sub(r'[\\/:*?"<>|\r\n\t]', ' ', title)
    title = re.sub(r'\s+', ' ', title).strip(' .')
    return title[:max_len]


def extract_title(path: Path) -> Optional[str]:
    """从文件内容提炼一个摘要标题。"""
    try:
        if path.suffix.lower() == '.md':
            for line in path.read_text(encoding='utf-8', errors='ignore').splitlines()[:60]:
                m = re.match(r'^#+\s+(.+)', line)
                if m:
                    return sanitize(m.group(1))
        elif path.suffix.lower() in ('.py', '.sh', '.js', '.ts'):
            text = path.read_text(encoding='utf-8', errors='ignore')
            m = re.search(r'"""(.*?)"""', text, re.S)
            if m:
                first = m.group(1).strip().splitlines()[0]
                return sanitize(first)
        elif path.suffix.lower() == '.txt':
            for line in path.read_text(encoding='utf-8', errors='ignore').splitlines():
                line = line.strip()
                if line and not line.startswith(('#', '//', ';')):
                    return sanitize(line)
    except Exception:
        pass
    return None


def file_hash(path: Path) -> str:
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def find_files(root: Path):
    """遍历目录，跳过隐藏目录与 node_modules。"""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith('.') and d != 'node_modules']
        for fn in filenames:
            if fn.startswith('.'):
                continue
            yield Path(dirpath) / fn


# ---------- 子命令 ----------

def cmd_scan(root: Path):
    bad, temp, junk = [], [], []
    for p in find_files(root):
        rel = p.relative_to(root)
        name = p.name
        if is_temp(name):
            temp.append(rel)
        if is_bad_name(p):
            bad.append(rel)
        if has_version_junk(name):
            junk.append(rel)

    print(f"📂 扫描目录：{root}\n")
    print(f"🔴 乱命名文件（{len(bad)} 个）—— 建议 rename")
    for r in bad:
        print(f"    {r}")
    print(f"\n🟡 版本冗余文件（{len(junk)} 个）—— 建议人工确认后 dedup")
    for r in junk:
        print(f"    {r}")
    print(f"\n🗑️  临时/垃圾文件（{len(temp)} 个）—— 建议 cleanup")
    for r in temp:
        print(f"    {r}")
    if not (bad or temp or junk):
        print("✅ 目录很干净，没有发现需要治理的文件。")


def cmd_rename(root: Path, apply: bool):
    count = 0
    for p in list(find_files(root)):
        if not is_bad_name(p):
            continue
        title = extract_title(p)
        if title is None:
            print(f"⚠️  无法提炼标题，跳过：{p.relative_to(root)}")
            continue
        new_name = title + p.suffix
        new_path = p.with_name(new_name)
        if new_path.exists():
            print(f"⚠️  目标已存在，跳过：{p.name} -> {new_name}")
            continue
        print(f"{'♻️ ' if apply else '🎯 '}{p.name}  ->  {new_name}")
        if apply:
            p.rename(new_path)
        count += 1
    print(f"\n{'已重命名' if apply else '待重命名'} {count} 个文件。")


def cmd_organize(root: Path, apply: bool):
    count = 0
    for p in list(find_files(root)):
        if p.parent != root:            # 只整理根目录层，不递归
            continue
        if p.name in PROTECTED:
            continue
        name = p.name.lower()
        for cat, rules in CATEGORY_RULES:
            if any(r.search(name) for r in rules):
                dest = root / cat
                print(f"{'📦 ' if apply else '🎯 '}{p.name}  ->  {cat}/")
                if apply:
                    dest.mkdir(exist_ok=True)
                    shutil.move(str(p), str(dest / p.name))
                count += 1
                break
    print(f"\n{'已整理' if apply else '待整理'} {count} 个文件。")


def cmd_archive(root: Path, days: int, apply: bool):
    cutoff = time.time() - days * 86400
    archive_dir = root / '归档'
    count = 0
    for p in list(find_files(root)):
        if p.parent != root:
            continue
        if p.name in PROTECTED:
            continue
        if p.stat().st_mtime < cutoff:
            print(f"{'📚 ' if apply else '🎯 '}{p.name}  ->  归档/  （{days} 天未动）")
            if apply:
                archive_dir.mkdir(exist_ok=True)
                shutil.move(str(p), str(archive_dir / p.name))
            count += 1
    print(f"\n{'已归档' if apply else '待归档'} {count} 个文件。")


def cmd_cleanup(root: Path, apply: bool):
    count = 0
    for p in list(find_files(root)):
        if is_temp(p.name):
            print(f"{'🗑️ ' if apply else '🎯 '}{p.relative_to(root)}")
            if apply:
                p.unlink()
            count += 1
    print(f"\n{'已清理' if apply else '待清理'} {count} 个文件。")


def cmd_dedup(root: Path, apply: bool):
    groups = defaultdict(list)
    for p in find_files(root):
        try:
            if p.stat().st_size > 0:
                groups[file_hash(p)].append(p)
        except OSError:
            continue
    total_removed = 0
    for files in groups.values():
        if len(files) > 1:
            print(f"🔁 重复组（内容相同，{len(files)} 份）:")
            print(f"   保留: {files[0].relative_to(root)}")
            for dup in files[1:]:
                print(f"   {'🗑️ ' if apply else '   '}删除: {dup.relative_to(root)}")
                if apply:
                    dup.unlink()
                total_removed += 1
    print(f"\n{'已删除' if apply else '待删除'} {total_removed} 个重复文件。")


# ---------- 主入口 ----------

def main():
    parser = argparse.ArgumentParser(description='智能体输出治理引擎')
    parser.add_argument('command',
                        choices=['scan', 'rename', 'organize', 'archive', 'cleanup', 'dedup'],
                        help='要执行的治理动作')
    parser.add_argument('path', nargs='?', default='.', help='目标目录（默认当前目录）')
    parser.add_argument('--apply', action='store_true', help='真正执行（默认只预览）')
    parser.add_argument('--days', type=int, default=ARCHIVE_DAYS, help='归档阈值天数（默认 30）')
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"❌ 目录不存在：{root}")
        sys.exit(1)

    if not args.apply:
        print("🔍 DRY-RUN 模式（只预览，不修改任何文件）。加 --apply 才真正执行。\n")

    cmds = {
        'scan': lambda: cmd_scan(root),
        'rename': lambda: cmd_rename(root, args.apply),
        'organize': lambda: cmd_organize(root, args.apply),
        'archive': lambda: cmd_archive(root, args.days, args.apply),
        'cleanup': lambda: cmd_cleanup(root, args.apply),
        'dedup': lambda: cmd_dedup(root, args.apply),
    }
    cmds[args.command]()

    if not args.apply:
        print("\n（以上为预览，未做任何修改。）")


if __name__ == '__main__':
    main()
