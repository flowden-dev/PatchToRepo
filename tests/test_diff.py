from patchtorepo.diff import decode, render, utf16_length
from patchtorepo.engine import FileState


def test_alignment_preserves_real_line_numbers_and_empty_placeholders():
    result = render(
        FileState("x.py", b"a\nb\nc\n", 420), FileState("x.py", b"a\nnew\nb\nc\n", 420), "x.py"
    )
    assert len(result.left) == len(result.right)
    assert [r.number for r in result.left] == [1, None, 2, 3]
    assert [r.number for r in result.right] == [1, 2, 3, 4]
    assert result.left[1].kind == "gap"
    assert result.changes == (1,)


def test_multiline_syntax_and_non_bmp_characters():
    a = FileState("x.py", 'text = "😀"\n# before\n'.encode())
    b = FileState("x.py", 'text = "😀 new"\n# before\n'.encode())
    result = render(a, b, "x.py")
    assert any(line.syntax for line in result.left)
    assert utf16_length("😀") == 2
    for line in result.right:
        assert all(span.start + span.length <= utf16_length(line.text) for span in line.syntax)


def test_binary_and_large_files_are_labeled_without_fake_text_diff():
    for content in (b"\0binary", b"x" * (2 * 1024 * 1024 + 1)):
        result = render(FileState("x", b"old"), FileState("x", content), "x")
        assert result.limited
        assert result.changes == ()
        assert "SHA-256" in result.right[-1].text


def test_display_encoding_does_not_change_bytes():
    raw = b"caf\xe9"
    assert decode(raw, "Auto")[0] == "café"
    assert raw == b"caf\xe9"


def test_eof_only_change_has_visible_explanation():
    result = render(FileState("x", b"abc"), FileState("x", b"abc\n"), "x")
    assert "Byte-level" in result.note
