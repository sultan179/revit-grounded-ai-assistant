"""Pre-push check: refuse a push that contains a word from a private list.

The list holds names that must never appear in this public repository. It lives
outside the repository and is never committed. Tell Git where it is, once per clone:

    git config guard.wordlist /path/to/private-words.txt

One word or phrase per line. Matching ignores case. Lines starting with # are comments.
Git runs this through .githooks/pre-push and passes the pushed refs on standard input.

Checked for every ref being pushed: the ref names, the authors, the commit and tag
messages, the file names and the changed lines. A branch that the remote does not
have yet is checked in full, back to its first commit.

A listed phrase of several words is also found when it is split across lines or
written with other spacing or punctuation ("Acme Towers", "acme-towers").

Known limits:
- a phrase written as one word ("AcmeTowers"), or glued to a longer word with other
  punctuation ("MyAcme-Towers"), is found only if that spelling is listed too;
- compressed files (zip, docx, images) are not opened;
- of a tag that points at another tag, only the outer message is checked.
"""

import re
import subprocess
import sys
import unicodedata
from pathlib import Path

LOG = (
    *("log", "-p", "-m", "--text", "--no-textconv", "--no-ext-diff", "--no-color"),
    *("--encoding=UTF-8", "--format=commit %H%n%an <%ae>%n%cn <%ce>%n%B"),
)
# Characters that take no space on screen: soft hyphen, zero-width marks, byte order mark.
INVISIBLE = re.compile("[­​-‏⁠﻿]")


class CheckError(Exception):
    """The check could not run, so the push is refused."""


def fold(text: str) -> str:
    """Lower case, one Unicode form, no invisible characters: none of these may hide a word."""
    return INVISIBLE.sub("", unicodedata.normalize("NFKC", text)).casefold()


def spaced(text: str) -> str:
    """The letters and digits of text, as words with one space in front of each."""
    return "".join(f" {word}" for word in re.findall(r"[^\W_]+", fold(text)))


def read_words(path: Path) -> list[str]:
    """Return the listed words, folded. Refuse a list that cannot protect anything."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as error:
        raise CheckError(f"cannot read the word list as UTF-8 text ({error})") from error
    if "\x00" in text:
        raise CheckError("the word list is not UTF-8 text (was it saved as UTF-16?)")
    lines = [fold(line.strip()) for line in text.splitlines()]
    words = [line for line in lines if line and not line.startswith("#")]
    if not words:
        raise CheckError("the word list is empty")
    return words


def find_words(text: str, words: list[str]) -> list[str]:
    """Return one message for every place where text contains a listed word."""
    hits = []
    found = set()
    for number, line in enumerate(text.splitlines(), start=1):
        folded = fold(line)
        in_line = [word for word in words if word in folded]
        if in_line:
            found.update(in_line)
            hits.append(f"line {number} of the checked text: {line}")
    # Second pass, for phrases only: line breaks, spacing and punctuation are ignored.
    whole = spaced(text)
    for word in words:
        phrase = spaced(word)
        if word not in found and phrase.count(" ") > 1 and phrase in whole:
            hits.append(f"the phrase {word!r}, split across lines or written with other marks")
    return hits


def git(*args: str) -> bytes:
    """Run a git command and return its raw output. A failing command stops the check."""
    # quotePath=false makes git print accented file names as they are, not as escapes.
    done = subprocess.run(
        ["git", "-c", "core.quotePath=false", *args], capture_output=True, check=False
    )
    if done.returncode != 0:
        reason = done.stderr.decode("utf-8", "replace").strip()
        raise CheckError(f"git {args[0]} failed ({reason})")
    return done.stdout


def pushed_bytes(local_ref: str, local_sha: str, remote_ref: str, remote_sha: str) -> bytes:
    """Everything a reader of the push would see, as raw bytes."""
    # A branch the remote does not have yet is read in full. Reading only "the commits
    # no remote has" would trust every other remote this clone knows.
    commits = local_sha if set(remote_sha) == {"0"} else f"{remote_sha}..{local_sha}"
    # In LOG, -m shows what a merge changed and --text shows files git would call binary.
    log = git(*LOG, commits)
    pushed_object = git("cat-file", "-p", local_sha)  # holds the message of an annotated tag
    refs = f"{local_ref}\n{remote_ref}\n".encode()
    # Without its NUL bytes, text saved as UTF-16 reads like ordinary text.
    return (refs + pushed_object + b"\n" + log).replace(b"\x00", b"")


def say(message: str) -> None:
    """Print to the terminal. Characters it may not be able to show are written as escapes."""
    print(f"pre-push: {message}".encode("ascii", "backslashreplace").decode(), file=sys.stderr)


def main(pushed_refs: list[str]) -> int:
    """Return 0 when the push may go ahead and 1 when it is refused."""
    hits: list[str] = []
    try:
        list_path = git("config", "--default", "", "--get", "guard.wordlist").decode().strip()
        if not list_path:
            raise CheckError("no word list is set (git config guard.wordlist <path>)")
        words = read_words(Path(list_path).expanduser())
        for line in pushed_refs:
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) != 4:
                raise CheckError(f"cannot read this line from git: {line!r}")
            local_ref, local_sha, remote_ref, remote_sha = parts
            if set(local_sha) == {"0"}:  # deleting a remote branch pushes nothing
                continue
            raw = pushed_bytes(local_ref, local_sha, remote_ref, remote_sha)
            # Read as UTF-8 and, if that finds nothing, as Latin-1: a file saved in an older
            # Windows encoding or as UTF-16 shows its accented letters only that way.
            found = find_words(raw.decode("utf-8", "replace"), words)
            found = found or find_words(raw.decode("latin-1"), words)
            hits += [f"{local_ref}: {hit}" for hit in found]
    except (CheckError, OSError, UnicodeDecodeError) as error:
        say(f"{error}. Push refused.")
        return 1
    for hit in hits:
        say(hit)
    if hits:
        say("a word from the private list is in this push. Refused.")
        return 1
    return 0


if __name__ == "__main__":
    # Git writes ref names as UTF-8, whatever the terminal's own encoding is.
    sys.exit(main(sys.stdin.buffer.read().decode("utf-8", "replace").splitlines()))
