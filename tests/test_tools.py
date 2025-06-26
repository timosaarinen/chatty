import os
import pytest
from agentlib import tools

@pytest.fixture
def test_file(tmp_path):
    file_path = tmp_path / "test.txt"
    file_path.write_text("Hello, world!\nThis is a test file.")
    return str(file_path)

def test_read_file(test_file):
    content = tools.read_file(test_file)
    assert content == "Hello, world!\nThis is a test file."

def test_list_files(tmp_path):
    (tmp_path / "file1.txt").touch()
    (tmp_path / "file2.txt").touch()
    files = tools.list_files(str(tmp_path))
    assert sorted(files) == ["file1.txt", "file2.txt"]

def test_glob_files(tmp_path):
    (tmp_path / "a.txt").touch()
    (tmp_path / "b.py").touch()
    patterns = tools.glob_files(str(tmp_path / "*.txt"))
    assert len(patterns) == 1
    assert os.path.basename(patterns[0]) == "a.txt"

def test_search_file(test_file):
    results = tools.search_file(test_file, "world")
    assert len(results) == 1
    assert results[0] == "1: Hello, world!"

def test_write_file(tmp_path):
    file_path = tmp_path / "new_file.txt"
    tools.write_file(str(file_path), "New content")
    assert file_path.read_text() == "New content"

def test_edit_file(test_file):
    tools.edit_file(test_file, "world", "pytest")
    content = tools.read_file(test_file)
    assert content == "Hello, pytest!\nThis is a test file."

def test_shell_command():
    result = tools.shell_command("echo 'hello'", dry_run=True)
    assert result == "Dry run: echo 'hello'"

