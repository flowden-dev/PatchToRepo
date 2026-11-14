import pytest
from conftest import run

from patchtorepo.patch import MAX_PATCH_BYTES, Patch, PatchError, safe_path, unquote


@pytest.mark.parametrize(
    "name",
    [
        "../outside",
        "/absolute",
        "a/../../x",
        "C:/outside",
        ".git/config",
        "a/.GiT/config",
        "a\\b",
        "NUL.txt",
        "a/COM1",
        "a/../x",
        "trailing.",
        "trailing ",
        "bad:ads",
        "a//b",
        "a/\nfile",
    ],
)
def test_unsafe_paths_are_refused(name):
    with pytest.raises(PatchError):
        safe_path(name)


def test_quoted_octal_utf8_path():
    assert unquote(b'"caf\\303\\251.txt"') == "café.txt"
    assert safe_path("한국어/日本語.txt") == "한국어/日本語.txt"


@pytest.mark.parametrize("mode", [b"120000", b"160000", b"100600"])
def test_special_modes_are_refused(mode):
    with pytest.raises(PatchError):
        Patch.parse(
            b"diff --git a/link b/link\nnew file mode "
            + mode
            + b"\n--- /dev/null\n+++ b/link\n@@ -0,0 +1 @@\n+target\n"
        )


def test_duplicate_changes_and_case_collisions(patch):
    with pytest.raises(PatchError, match="Repeated"):
        Patch.parse(patch.data + patch.data)
    with pytest.raises(PatchError, match="Repeated"):
        Patch.parse(patch.data + patch.data.replace(b"hello.cpp", b"HELLO.cpp"))


def test_case_only_rename_is_refused():
    with pytest.raises(PatchError, match="Case-only"):
        Patch.parse(
            b"diff --git a/foo b/Foo\nsimilarity index 100%\nrename from foo\nrename to Foo\n"
        )


def test_binary_without_payload_is_refused():
    with pytest.raises(PatchError, match="no payload"):
        Patch.parse(b"diff --git a/x.bin b/x.bin\nBinary files a/x.bin and b/x.bin differ\n")


def test_missing_or_oversize_input():
    for raw in (b"", b"not a patch", b"x" * (MAX_PATCH_BYTES + 1)):
        with pytest.raises(PatchError):
            Patch.parse(raw)


def test_format_patch_email(engine, repo):
    (repo / "hello.cpp").write_text("int main() {\n    return 7;\n}\n")
    run(repo, "commit", "-qam", "change")
    raw = run(repo, "format-patch", "-1", "--stdout")
    run(repo, "reset", "--hard", "HEAD^")
    patch = Patch.parse(raw)
    assert engine.apply(engine.review(repo, patch)).verified


def test_malformed_hunk_inventory_refuses_missing_changes(engine, repo, patch):
    with pytest.raises(PatchError):
        malformed = Patch.parse(patch.data.replace(b"@@ -1,3 +1,3 @@", b"@@ -1,8 +1,3 @@"))
        engine.review(repo, malformed)


def test_filenames_with_git_separator_text(engine, repo):
    # Git does not quote ordinary spaces, including the separator's text
    (repo / "has b").mkdir()
    file = repo / "has b/space name.txt"
    file.write_bytes(b"old\n")
    run(repo, "add", ".")
    run(repo, "commit", "-qm", "path")
    file.write_bytes(b"new\n")
    patch = Patch.parse(run(repo, "diff"))
    run(repo, "checkout", "--", ".")
    assert engine.apply(engine.review(repo, patch)).verified
