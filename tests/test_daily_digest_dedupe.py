import importlib
import sys
import unittest
from types import ModuleType
from unittest.mock import Mock, patch

with patch.dict(sys.modules, {
    "dotenv": ModuleType("dotenv"),
    "openai": ModuleType("openai"),
}):
    sys.modules["dotenv"].load_dotenv = Mock()
    sys.modules["openai"].OpenAI = Mock(side_effect=AssertionError("no model calls"))
    digest = importlib.import_module("agents.daily-digest.main")
    github_search = sys.modules[digest.search_repos.__module__]
history = digest.history


def candidate(name, stars):
    return dict(full_name=name, html_url=f"https://github.com/{name}", stargazers_count=stars)


class DigestDedupeTest(unittest.TestCase):
    def test_archived_rows_not_description(self):
        rows = "- Foo/Bar | https://github.com/Foo/Bar | star=1 | See https://github.com/Other/Project"
        self.assertEqual(history.find_archived_repo_names(rows), {"foo/bar"})

    def test_search_dedupes_casing_and_preserves_default_limit(self):
        first = candidate("Foo/Bar", 3)
        newer = candidate("foo/bar", 4)
        other = candidate("other/new", 1)
        with patch.object(github_search, "_search_repo", side_effect=[[first], [other, newer]]):
            self.assertEqual([r["full_name"] for r in github_search.search_repos(["a", "b"], top_n=1)], ["foo/bar"])

    def test_all_history_including_old_archives(self):
        archives = history.load_data(digest.TAG, "resp-list")
        self.assertGreater(len(archives), digest.DEDUPE_HISTORY_LIMIT)
        archived = set().union(*(history.find_archived_repo_names(body) for _, body in archives))
        novel = candidate("example/demo-novel-control", 1)
        with patch("builtins.print"):
            self.assertEqual(digest.filter_known_repos(
                [candidate(name.upper(), 10) for name in sorted(archived)] + [novel]), [novel])

    def test_main_before_cap(self):
        duplicate = "affaan-m/ECC"
        novel = candidate("example/demo-novel-control", 1)
        known = [f"seen/project{i}" for i in range(9)] + [duplicate]
        ranked = [candidate(name, 100-i) for i, name in enumerate(known)] + [novel]
        archive = "\n".join(f"- {name.upper()} | https://github.com/{name} | star=1" for name in known)
        with (
            patch.object(github_search, "_search_repo", return_value=ranked),
            patch.object(history, "load_data", return_value=[("archived", archive)]) as read,
            patch.object(digest, "build_daily_report", return_value="<p>Fixture</p>") as build,
            patch.object(digest, "dedupe_with_llm", return_value={}),
            patch.object(digest, "send_email") as send,
            patch.object(digest, "save_history_record") as save,
            patch.object(sys, "argv", ["digest", "--dry-run"]),
            patch("builtins.print"),
        ):
            digest.main()
        self.assertEqual(read.call_args.args, (digest.TAG, "resp-list"))
        self.assertEqual([r["full_name"] for r in build.call_args.args[0]], [novel["full_name"]])
        save.assert_not_called()
        send.assert_not_called()

    def test_main_skips_november_23_duplicates_without_sending(self):
        path = history.DATA_ROOT / "daily-digest/2026-11/23-resp-list.md"
        names = [
            line.split("|", 1)[0].strip()[2:]
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.startswith("- ")
        ]
        self.assertEqual(len(names), 3)
        load = history.load_data
        # Simulate the archive state before this set of candidates was sent.
        with (
            patch.object(history, "load_data", side_effect=lambda *a: [(n, s) for n, s in load(*a) if n != path.name]),
            patch.object(github_search, "_search_repo", return_value=[candidate(name, 50) for name in names]),
            patch.object(digest, "build_daily_report") as build,
            patch.object(digest, "send_email") as send,
            patch.object(digest, "save_history_record") as save,
            patch.object(sys, "argv", ["digest"]),
            patch("builtins.print"),
        ):
            digest.main()
        build.assert_not_called()
        save.assert_not_called()
        send.assert_not_called()
