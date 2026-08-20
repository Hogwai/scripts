#!/usr/bin/env python3
"""Put one sentence per line in ordinary Markdown paragraphs."""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path


FENCE_RE = re.compile(r"^(?P<indent> {0,3})(?P<char>`|~)(?P<count>\2{2,})(?P<info>.*)$")
LIST_RE = re.compile(r"^(?P<indent>\s*)(?P<marker>(?:[-+*]|\d+[.)]))(?P<space>\s+)(?P<text>.*)$")
ATX_HEADING_RE = re.compile(r"^ {0,3}#{1,6}(?:\s|$)")
HORIZONTAL_RULE_RE = re.compile(
    r"^ {0,3}(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})$"
)
TABLE_SEPARATOR_CELL_RE = re.compile(r"^\s*:?-{3,}:?\s*$")
REFERENCE_RE = re.compile(r"^ {0,3}\[[^\]]+\]:\s+\S+")
STANDALONE_LINK_RE = re.compile(
    r"^\s*(?:!?\[.*\]\(.*\)|\[.*\]\[.*\]|<https?://[^>]+>)\s*$"
)
URL_RE = re.compile(r"(?i)(?:\bhttps?://|\bwww\.)[^\s<>()]+")
ABBREVIATION_RE = re.compile(
    r"(?i)(?:\b(?:e\.g|i\.e|etc|mr|mrs|ms|dr|prof|sr|jr|vs|no|fig|approx)\.)$"
)
INITIALS_RE = re.compile(r"(?:\b[A-Za-z]\.){2,}$")


def line_body(raw_line: str) -> tuple[str, str]:
    """Return a line without its ending and the original line ending."""
    if raw_line.endswith("\r\n"):
        return raw_line[:-2], "\r\n"
    if raw_line.endswith(("\n", "\r")):
        return raw_line[:-1], raw_line[-1]
    return raw_line, ""


def is_fence_start(line: str) -> re.Match[str] | None:
    match = FENCE_RE.match(line)
    if match is None:
        return None
    # Backticks cannot be used as a fence when the info string contains one.
    if match.group("char") == "`" and "`" in match.group("info"):
        return None
    return match


def is_fence_end(line: str, fence_char: str, fence_length: int) -> bool:
    return re.match(r"^ {0,3}" + re.escape(fence_char) + "{" + str(fence_length) + r",}\s*$", line) is not None


def is_table_separator(line: str) -> bool:
    stripped = line.strip()
    if "|" not in stripped:
        return False
    cells = stripped.strip("|").split("|")
    return len(cells) >= 1 and all(TABLE_SEPARATOR_CELL_RE.match(cell) for cell in cells)


def table_lines(lines: list[str]) -> set[int]:
    """Find rows belonging to pipe tables, including their non-separator rows."""
    protected: set[int] = set()
    for index, line in enumerate(lines):
        if not is_table_separator(line) or index == 0 or "|" not in lines[index - 1]:
            continue
        start = index - 1
        while start >= 0 and lines[start].strip() and "|" in lines[start]:
            start -= 1
        end = index + 1
        while end < len(lines) and lines[end].strip() and "|" in lines[end]:
            end += 1
        protected.update(range(start + 1, end))
    return protected


def is_standalone_markdown(line: str) -> bool:
    stripped = line.strip()
    return bool(
        STANDALONE_LINK_RE.match(stripped)
        or REFERENCE_RE.match(line)
        or (stripped.startswith("<") and stripped.endswith(">"))
    )


def is_special_line(line: str, index: int, protected_tables: set[int]) -> bool:
    if index in protected_tables:
        return True
    if ATX_HEADING_RE.match(line) or HORIZONTAL_RULE_RE.match(line):
        return True
    if is_standalone_markdown(line):
        return True
    # Four-space indented code is another Markdown code-block spelling.
    if line.startswith("    ") or line.startswith("\t"):
        return True
    return False


def mark_range(mask: list[bool], start: int, end: int) -> None:
    for position in range(max(0, start), min(len(mask), end)):
        mask[position] = True


def inline_protected_ranges(text: str) -> list[bool]:
    """Mark inline code, links, and URL bodies where punctuation is not prose."""
    mask = [False] * len(text)

    for match in re.finditer(r"(?<!\\)(`+)(.*?)(?<!`)\1", text, flags=re.DOTALL):
        mark_range(mask, match.start(), match.end())

    # Cover inline links/images, including a balanced destination such as
    # (https://example.test/path_(part)).
    link_start_re = re.compile(r"!?\[")
    for match in link_start_re.finditer(text):
        close_bracket = text.find("]", match.end())
        if close_bracket < 0:
            continue
        destination_start = close_bracket + 1
        if destination_start >= len(text) or text[destination_start] != "(":
            continue
        depth = 0
        escaped = False
        destination_end = None
        for position in range(destination_start, len(text)):
            char = text[position]
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    destination_end = position + 1
                    break
        if destination_end is not None:
            mark_range(mask, match.start(), destination_end)

    for match in URL_RE.finditer(text):
        end = match.end()
        while end > match.start() and text[end - 1] in ".,!?;:":
            end -= 1
        mark_range(mask, match.start(), end)

    for match in re.finditer(r"<https?://[^>]+>", text, flags=re.IGNORECASE):
        mark_range(mask, match.start(), match.end())
    return mask


def is_abbreviation(text: str, punctuation_index: int) -> bool:
    if text[punctuation_index] != ".":
        return False
    preceding = text[max(0, punctuation_index - 20) : punctuation_index + 1]
    return bool(ABBREVIATION_RE.search(preceding) or INITIALS_RE.search(preceding))


def split_sentences(text: str) -> list[str]:
    """Split only at likely sentence endings outside inline constructs."""
    protected = inline_protected_ranges(text)
    sentences: list[str] = []
    start = 0
    index = 0
    while index < len(text):
        if (
            text[index] in ".!?"
            and not protected[index]
            and index + 1 < len(text)
            and text[index + 1].isspace()
            and not is_abbreviation(text, index)
        ):
            next_text = index + 1
            while next_text < len(text) and text[next_text].isspace():
                next_text += 1
            if next_text < len(text):
                sentences.append(text[start : index + 1].strip())
                start = next_text
                index = next_text
                continue
        index += 1
    remainder = text[start:].strip()
    if remainder:
        sentences.append(remainder)
    return sentences or [text.strip()]


def join_paragraph(lines: list[str]) -> str:
    # Stripping each edge removes wrapping whitespace only; spacing within a
    # Markdown line (including inline code) is left untouched.
    return " ".join(line.strip() for line in lines)


def format_markdown(text: str) -> str:
    raw_lines = text.splitlines(keepends=True)
    if not raw_lines:
        return text
    lines = [line_body(raw)[0] for raw in raw_lines]
    protected_tables = table_lines(lines)
    output: list[str] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        fence = is_fence_start(line)
        if fence is not None:
            output.append(line)
            index += 1
            fence_char = fence.group("char")
            fence_length = 1 + len(fence.group("count"))
            while index < len(lines):
                output.append(lines[index])
                if is_fence_end(lines[index], fence_char, fence_length):
                    index += 1
                    break
                index += 1
            continue

        if not line.strip():
            output.append(line)
            index += 1
            continue

        list_match = LIST_RE.match(line)
        if list_match is not None and not HORIZONTAL_RULE_RE.match(line):
            continuation = [list_match.group("text")]
            next_index = index + 1
            while next_index < len(lines):
                candidate = lines[next_index]
                if not candidate.strip() or is_special_line(candidate, next_index, protected_tables):
                    break
                if LIST_RE.match(candidate):
                    break
                continuation.append(candidate)
                next_index += 1
            sentences = split_sentences(join_paragraph(continuation))
            prefix = list_match.group("indent") + list_match.group("marker") + list_match.group("space")
            output.append(prefix + sentences[0])
            continuation_indent = list_match.group("indent") + " " * (
                len(list_match.group("marker")) + len(list_match.group("space"))
            )
            output.extend(continuation_indent + sentence for sentence in sentences[1:])
            index = next_index
            continue

        if is_special_line(line, index, protected_tables):
            output.append(line)
            index += 1
            continue

        paragraph = [line]
        next_index = index + 1
        while next_index < len(lines):
            candidate = lines[next_index]
            if (
                not candidate.strip()
                or is_special_line(candidate, next_index, protected_tables)
                or LIST_RE.match(candidate)
                or is_fence_start(candidate) is not None
            ):
                break
            paragraph.append(candidate)
            next_index += 1
        output.extend(split_sentences(join_paragraph(paragraph)))
        index = next_index

    newline = "\r\n" if any(raw.endswith("\r\n") for raw in raw_lines) else "\n"
    result = newline.join(output)
    if raw_lines[-1].endswith(("\n", "\r")):
        result += newline
    return result


def read_file(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as stream:
        return stream.read()


def write_file(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        stream.write(content)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reformat Markdown paragraphs by putting each sentence on its own "
            "line without changing structured Markdown blocks."
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="write changes directly to the files")
    mode.add_argument(
        "--check",
        action="store_true",
        help="write nothing and return 1 if a file would change",
    )
    parser.add_argument(
        "paths",
        nargs="+",
        metavar="FILE",
        help="one or more Markdown files to check or reformat",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    changed = False
    for filename in args.paths:
        path = Path(filename)
        try:
            original = read_file(path)
        except OSError as error:
            print(f"format-markdown.py: {path}: {error}", file=sys.stderr)
            return 2
        formatted = format_markdown(original)
        if formatted == original:
            continue
        changed = True
        if args.write:
            try:
                write_file(path, formatted)
            except OSError as error:
                print(f"format-markdown.py: {path}: {error}", file=sys.stderr)
                return 2
        else:
            diff = difflib.unified_diff(
                original.splitlines(keepends=True),
                formatted.splitlines(keepends=True),
                fromfile=str(path),
                tofile=str(path),
            )
            sys.stdout.writelines(diff)
    return 1 if args.check and changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
