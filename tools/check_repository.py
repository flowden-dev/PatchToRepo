#!/usr/bin/env python3
"""Check release metadata, local documentation links, and icon containers (stdlib only)."""
from __future__ import annotations

import binascii
import json
from pathlib import Path
import re
import struct
import sys
from urllib.parse import unquote, urlsplit
import zlib

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "README.md", "LICENSE", "VERSION", "CHANGELOG.md", "CREDITS.md",
    "THIRD_PARTY_NOTICES.md", "CONTRIBUTING.md", "SECURITY.md", "AGENTS.md", "CLAUDE.md",
    ".editorconfig", ".gitattributes", ".gitignore", ".github/workflows/ci.yml",
    ".github/dependabot.yml", ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/feature_request.yml", ".github/ISSUE_TEMPLATE/config.yml",
    ".github/pull_request_template.md", "PatchToRepo.au3", "Compile-Windows.cmd",
    "Verify-Windows.cmd", "assets/PatchToRepo.ico", "assets/PatchToRepo.png", "assets/ICON.md",
    "scripts/Toolchain.psm1", "scripts/Build.ps1", "scripts/Verify.ps1",
    "scripts/Setup-AutoIt.ps1", "scripts/Package.ps1", "packaging/README.md",
    "tools/autoit-toolchain.json", "tests/test_git_workflow.py", "docs/user-guide.md",
    "docs/development.md", "docs/architecture.md", "docs/testing.md", "docs/publishing.md",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def check_metadata() -> None:
    for name in REQUIRED:
        require((ROOT / name).is_file(), f"Missing file: {name}")
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    require(bool(re.fullmatch(r"\d+\.\d+\.\d+", version)), "Invalid VERSION")
    source = (ROOT / "PatchToRepo.au3").read_text(encoding="utf-8-sig")
    for expression in (
        r"(?m)^#pragma compile\(FileVersion, ([\d.]+)\)\r?$",
        r"(?m)^#pragma compile\(ProductVersion, ([\d.]+)\)\r?$",
        r"(?m)^#AutoIt3Wrapper_Res_Fileversion=([\d.]+)\r?$",
    ):
        match = re.search(expression, source)
        require(match is not None and match[1] == version + ".0", "Source version differs from VERSION")
    require(f"## {version}" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), "Version missing from changelog")
    pin = json.loads((ROOT / "tools/autoit-toolchain.json").read_text(encoding="utf-8"))
    require(bool(re.fullmatch(r"\d+\.\d+\.\d+\.\d+", pin["version"])), "Invalid AutoIt version")
    require(bool(re.fullmatch(r"[a-f0-9]{64}", pin["sha256"])), "AutoIt SHA-256 must be explicit")
    expected = f"https://www.autoitscript.com/autoit3/files/archive/autoit/autoit-v{pin['version']}.zip"
    require(pin["url"] == expected and pin["extractedRoot"] == "install", "Unexpected AutoIt archive location")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    uses = re.findall(r"(?m)^\s*(?:-\s*)?uses:\s*(\S+)", workflow)
    require(bool(uses), "No workflow action dependencies found")
    for action in uses:
        require(bool(re.fullmatch(r"[\w-]+/[\w-]+@[a-f0-9]{40}", action)), f"Action is not commit-pinned: {action}")
    require("pull_request_target" not in workflow, "Use the unprivileged pull_request event")
    require(bool(re.search(r"(?m)^permissions:\s*\n\s+contents: read\s*$", workflow)), "CI must have read-only contents permission")


def check_links() -> None:
    # packaging/README.md is validated at its eventual runtime location.
    runtime = {"README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "docs/user-guide.md"}
    for file in sorted(ROOT.rglob("*.md")):
        if any(part in {".git", ".tools", "build", "dist"} for part in file.relative_to(ROOT).parts):
            continue
        text = file.read_text(encoding="utf-8")
        targets = re.findall(r"!?\[[^\]\n]*\]\(([^\s)]+)\)", text)
        targets += re.findall(r'<img\b[^>]*\bsrc="([^"]+)"', text)
        for target in targets:
            uri = urlsplit(target)
            if uri.scheme or uri.netloc or not uri.path:
                continue
            path = unquote(uri.path)
            if file == ROOT / "packaging/README.md":
                require(path in runtime, f"Runtime README link is not packaged: {path}")
                resolved = ROOT / path
            else:
                resolved = (file.parent / path).resolve()
                require(resolved.is_relative_to(ROOT), f"Link escapes repository: {file.name}: {target}")
            require(resolved.is_file(), f"Broken local link: {file.relative_to(ROOT)}: {target}")
            if uri.fragment and resolved.suffix == ".md":
                headings = re.findall(r"(?m)^#{1,6}\s+(.+?)\s*$", resolved.read_text(encoding="utf-8"))
                slugs = {re.sub(r"[^\w\s-]", "", heading.lower()).replace(" ", "-") for heading in headings}
                require(unquote(uri.fragment) in slugs, f"Missing heading: {file.relative_to(ROOT)}: {target}")


def check_png(data: bytes, expected: tuple[int, int] | None = None) -> tuple[int, int]:
    require(data[:8] == b"\x89PNG\r\n\x1a\n", "Invalid PNG signature")
    offset, compressed, dimensions, ended = 8, bytearray(), None, False
    while offset < len(data):
        require(offset + 12 <= len(data), "Truncated PNG chunk")
        length = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset + 4:offset + 8]
        end = offset + 12 + length
        require(end <= len(data), "PNG chunk exceeds file")
        body = data[offset + 8:offset + 8 + length]
        crc = struct.unpack_from(">I", data, offset + 8 + length)[0]
        require(binascii.crc32(kind + body) & 0xFFFFFFFF == crc, "PNG CRC mismatch")
        if kind == b"IHDR":
            require(dimensions is None and offset == 8 and length == 13, "Invalid PNG header")
            width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", body)
            require(0 < width <= 4096 and 0 < height <= 4096, "Unexpected PNG dimensions")
            require((depth, color, compression, filtering, interlace) == (8, 6, 0, 0, 0), "Expected noninterlaced 32-bit RGBA PNG")
            dimensions = (width, height)
        elif kind == b"IDAT":
            compressed.extend(body)
        elif kind == b"IEND":
            require(length == 0 and end == len(data), "Invalid PNG end")
            ended = True
        offset = end
    require(dimensions is not None and ended and bool(compressed), "Incomplete PNG")
    if expected is not None:
        require(dimensions == expected, "PNG dimensions differ from ICO directory")
    width, height = dimensions
    raw = zlib.decompress(compressed)
    stride = width * 4 + 1
    require(len(raw) == height * stride, "PNG scanline data has wrong length")
    require(all(raw[i] <= 4 for i in range(0, len(raw), stride)), "Invalid PNG row filter")
    # For the first pixel of the first row every PNG predictor is zero.
    require(raw[4] == 0, "PNG top-left corner must remain transparent")
    return dimensions


def check_icon() -> None:
    expected = {16, 20, 24, 32, 40, 48, 64, 128, 256}
    data = (ROOT / "assets/PatchToRepo.ico").read_bytes()
    require(len(data) >= 6, "Truncated ICO")
    reserved, kind, count = struct.unpack_from("<HHH", data)
    require((reserved, kind, count) == (0, 1, len(expected)), "Unexpected ICO directory")
    sizes, regions = set(), []
    for index in range(count):
        entry = struct.unpack_from("<BBBBHHII", data, 6 + 16 * index)
        width, height, _, zero, planes, bits, size, offset = entry
        width, height = width or 256, height or 256
        require(width == height and width in expected and width not in sizes, "Unexpected or duplicate ICO size")
        require(zero == 0 and planes == 1 and bits == 32, "Expected 32-bit ICO entries")
        require(size > 0 and offset >= 6 + 16 * count and offset + size <= len(data), "ICO entry exceeds file")
        require(all(offset + size <= low or offset >= high for low, high in regions), "Overlapping ICO images")
        regions.append((offset, offset + size))
        sizes.add(width)
        image = data[offset:offset + size]
        if image.startswith(b"\x89PNG"):
            check_png(image, (width, height))
        else:
            require(len(image) >= 40, "Truncated ICO bitmap")
            header, bw, bh, bp, bb, compression = struct.unpack_from("<IiiHHI", image)
            require((header, bw, bh, bp, bb, compression) == (40, width, height * 2, 1, 32, 0), "Unexpected ICO bitmap format")
            pixel_end = header + width * height * 4
            mask_size = ((width + 31) // 32) * 4 * height
            require(len(image) >= pixel_end + mask_size, "Truncated ICO pixel or mask data")
            alpha = image[header + 3:pixel_end:4]
            require(min(alpha) == 0 and max(alpha) == 255, "ICO alpha must include transparent and opaque pixels")
        print(f"  ICO {width}x{height}: 32-bit image data verified")
    require(sizes == expected, "ICO is missing advertised sizes")
    dimensions = check_png((ROOT / "assets/PatchToRepo.png").read_bytes())
    require(dimensions[0] == dimensions[1], "Master icon must be square")


def main() -> int:
    try:
        check_metadata()
        print("PASS: repository files, version metadata, toolchain pin, and workflow pins")
        check_links()
        print("PASS: local documentation links and runtime README links")
        check_icon()
        print("PASS: icon container, PNG CRCs, decoded scanline lengths, and transparency")
    except (ValueError, OSError, KeyError, struct.error, zlib.error) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print("These repository checks do not execute AutoIt or validate Windows integration.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
