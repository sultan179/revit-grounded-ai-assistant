"""Tests of the pre-push word check (tools/check_push.py). All names here are invented."""

import subprocess
import sys
from pathlib import Path

import check_push
import pytest

ZERO = "0" * 40
WORDS = "# invented names\nAcme Towers\nP-1234\nCafé Nord\n"
CLEAN = "nothing private here\n"


def write_list(folder: Path, text: str, encoding: str = "utf-8") -> Path:
    path = folder / "words.txt"
    path.write_bytes(text.encode(encoding))
    return path


def run_git(*args: str) -> str:
    done = subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True, encoding="utf-8"
    )
    return done.stdout.strip()


def commit(name: str, content: str | bytes, message: str) -> str:
    """Commit one file in the current folder and return the new commit's id."""
    data = content.encode("utf-8") if isinstance(content, str) else content
    Path(name).write_bytes(data)
    run_git("add", name)
    run_git("commit", "--quiet", "-m", message)
    return run_git("rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty Git repository, made the current folder, with the word list set.

    Git is cut off from this machine's own settings and from any repository the
    tests were started in, so the test commits can only land in the temporary folder.
    """
    for name in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE"):
        monkeypatch.delenv(name, raising=False)
    no_settings = tmp_path / "gitconfig"
    no_settings.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(no_settings))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    folder = tmp_path / "repo"
    folder.mkdir()
    monkeypatch.chdir(folder)
    run_git("init", "--quiet", "--initial-branch=main")
    run_git("config", "user.name", "Test Author")
    run_git("config", "user.email", "test@example.com")
    run_git("config", "guard.wordlist", str(write_list(tmp_path, WORDS)))
    return folder


def new_branch(sha: str, name: str = "refs/heads/main") -> list[str]:
    """What Git passes to the hook when a ref is pushed for the first time."""
    return [f"{name} {sha} {name} {ZERO}"]


# --- reading the list ---------------------------------------------------------------


def test_words_are_read_without_comments_blanks_or_case(tmp_path: Path) -> None:
    path = write_list(tmp_path, "# people\r\nAcme Towers\r\n\r\n  P-1234  \r\n")
    assert check_push.read_words(path) == ["acme towers", "p-1234"]


def test_a_list_with_a_byte_order_mark_is_read(tmp_path: Path) -> None:
    path = write_list(tmp_path, "\ufeffAcme Towers\n")
    assert check_push.read_words(path) == ["acme towers"]


@pytest.mark.parametrize("encoding", ["utf-16", "utf-16-le"])
def test_a_list_saved_as_utf16_is_refused(tmp_path: Path, encoding: str) -> None:
    path = write_list(tmp_path, WORDS, encoding=encoding)
    with pytest.raises(check_push.CheckError):
        check_push.read_words(path)


def test_an_empty_list_is_refused(tmp_path: Path) -> None:
    with pytest.raises(check_push.CheckError, match="empty"):
        check_push.read_words(write_list(tmp_path, "# only a comment\n\n"))


def test_a_missing_list_is_refused(tmp_path: Path) -> None:
    with pytest.raises(check_push.CheckError):
        check_push.read_words(tmp_path / "no-such-file.txt")


# --- matching -----------------------------------------------------------------------


def test_matching_ignores_case_and_reports_the_line() -> None:
    text = "line one\nbuilt for ACME towers\nline three"
    hits = check_push.find_words(text, ["acme towers"])
    assert hits == ["line 2 of the checked text: built for ACME towers"]


def test_a_word_inside_a_longer_word_is_found() -> None:
    assert check_push.find_words("see the AcmeLocal folder", ["acme"])


@pytest.mark.parametrize("mark", ["­", "​"], ids=["soft hyphen", "zero-width space"])
def test_an_invisible_character_does_not_hide_a_word(mark: str) -> None:
    assert check_push.find_words(f"see the Ac{mark}me plans", ["acme"])


@pytest.mark.parametrize(
    "text",
    [
        "built for Acme\nTowers",
        "+built for Acme\n+Towers",
        "refs/heads/acme-towers",
        "Acme   Towers",
        "ACME_TOWERS",
    ],
    ids=["wrapped", "wrapped in a diff", "hyphen", "wide spacing", "underscore"],
)
def test_a_phrase_is_found_however_it_is_spaced(text: str) -> None:
    assert check_push.find_words(text, ["acme towers"])


def test_clean_text_has_no_hits() -> None:
    assert check_push.find_words(CLEAN, ["acme towers"]) == []


def test_a_phrase_does_not_match_across_the_middle_of_a_word() -> None:
    words = [check_push.fold("x:\\vault")]
    assert check_push.find_words("the box vault is open", words) == []
    assert check_push.find_words("saved in X:\\Vault\\plans", words)


# --- whole pushes, in a temporary repository ----------------------------------------


def test_a_clean_push_goes_ahead(repo: Path) -> None:
    sha = commit("notes.txt", CLEAN, "add notes")
    assert check_push.main(new_branch(sha)) == 0


@pytest.mark.parametrize(
    ("name", "content", "message"),
    [
        ("notes.txt", "survey of acme towers\n", "add notes"),
        ("notes.txt", CLEAN, "notes for job P-1234"),
        ("acme towers.txt", CLEAN, "add notes"),
        ("café nord.txt", CLEAN, "add notes"),
        ("notes.txt", "survey of acme towers\n".encode("utf-16"), "add notes"),
        ("notes.txt", "visit to Café Nord\n".encode("utf-16"), "add notes"),
        ("notes.txt", "visit to Café Nord\n".encode("cp1252"), "add notes"),
    ],
    ids=[
        "file",
        "commit message",
        "file name",
        "accented file name",
        "file saved as utf-16",
        "accented word saved as utf-16",
        "accented word in an old Windows encoding",
    ],
)
def test_a_listed_word_stops_the_push(
    repo: Path, name: str, content: str | bytes, message: str
) -> None:
    sha = commit(name, content, message)
    assert check_push.main(new_branch(sha)) == 1


def test_a_listed_word_in_the_branch_name_stops_the_push(repo: Path) -> None:
    sha = commit("notes.txt", CLEAN, "add notes")
    assert check_push.main(new_branch(sha, name="refs/heads/acme-towers")) == 1


def test_a_listed_word_in_a_tag_message_stops_the_push(repo: Path) -> None:
    commit("notes.txt", CLEAN, "add notes")
    run_git("tag", "-a", "v1", "-m", "release for acme towers")
    assert check_push.main(new_branch(run_git("rev-parse", "v1"), name="refs/tags/v1")) == 1


def test_text_added_while_merging_is_checked(repo: Path) -> None:
    base = commit("notes.txt", "one\n", "start")
    run_git("checkout", "--quiet", "-b", "side")
    commit("side.txt", CLEAN, "side work")
    run_git("checkout", "--quiet", "main")
    commit("main.txt", CLEAN, "main work")
    run_git("merge", "--quiet", "--no-ff", "--no-commit", "side")
    merged = commit("notes.txt", "one\nsurvey of acme towers\n", "merge side")
    assert check_push.main([f"refs/heads/main {merged} refs/heads/main {base}"]) == 1


def test_on_a_known_branch_only_the_new_commits_are_checked(repo: Path) -> None:
    already_pushed = commit("old.txt", "survey of acme towers\n", "add old notes")
    new = commit("new.txt", CLEAN, "add new notes")
    assert check_push.main([f"refs/heads/main {new} refs/heads/main {already_pushed}"]) == 0


def test_a_new_branch_is_checked_in_full_whatever_other_remotes_hold(repo: Path) -> None:
    sha = commit("notes.txt", "survey of acme towers\n", "add notes")
    run_git("update-ref", "refs/remotes/backup/main", sha)
    assert check_push.main(new_branch(sha)) == 1


def test_deleting_a_remote_branch_goes_ahead(repo: Path) -> None:
    assert check_push.main([f"(delete) {ZERO} refs/heads/old {ZERO}"]) == 0


# --- when the check cannot run, the push is refused ---------------------------------


def test_no_configured_list_stops_the_push(repo: Path) -> None:
    sha = commit("notes.txt", CLEAN, "add notes")
    run_git("config", "--unset", "guard.wordlist")
    assert check_push.main(new_branch(sha)) == 1


def test_a_range_git_cannot_read_stops_the_push(repo: Path) -> None:
    sha = commit("notes.txt", CLEAN, "add notes")
    unknown = "1" * 40
    assert check_push.main([f"refs/heads/main {sha} refs/heads/main {unknown}"]) == 1


def test_a_line_that_is_not_from_git_stops_the_push(repo: Path) -> None:
    assert check_push.main(["not a line from git"]) == 1


def test_run_as_a_command_it_reads_git_input_as_utf8_and_refuses(repo: Path) -> None:
    sha = commit("notes.txt", CLEAN, "add notes")
    line = new_branch(sha, name="refs/heads/café-nord")[0] + "\n"
    done = subprocess.run(
        [sys.executable, check_push.__file__],
        input=line.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    assert done.returncode == 1
    assert b"Refused" in done.stderr


# --- the hook files -----------------------------------------------------------------


def test_committed_hooks_are_executable() -> None:
    """Git on Linux and macOS skips a hook that is not executable, and says so only quietly."""
    root = Path(__file__).parent.parent
    done = subprocess.run(
        ["git", "ls-files", "--stage", ".githooks"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    committed = done.stdout.splitlines()
    if done.returncode != 0 or not committed:
        pytest.skip("the hooks are not in a Git index here")
    assert [line for line in committed if not line.startswith("100755")] == []
