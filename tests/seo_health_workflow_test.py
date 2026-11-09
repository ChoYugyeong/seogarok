"""Offline regression tests for the exact shell step used by seo-health.yml."""

import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/seo-health.yml"
MOCK_CURL = r"""
curl() {
  local output='' url='' write_code=0
  while [ "$#" -gt 0 ]; do
    case "$1" in
      -o) output="$2"; shift 2 ;;
      -w) write_code=1; shift 2 ;;
      --max-time) shift 2 ;;
      -sS) shift ;;
      https://*) url="$1"; shift ;;
      *) echo "Unexpected curl argument: $1" >&2; return 2 ;;
    esac
  done
  case "$url" in
    */robots.txt) cp "$FIXTURE_DIR/robots.txt" "$output" ;;
    */books?page=1) cp "$FIXTURE_DIR/books.html" "$output" ;;
    */book/yes24%3A197068949) cp "$FIXTURE_DIR/book.html" "$output" ;;
    *) printf 'ok\n' > "$output" ;;
  esac
  if [ "$write_code" = 1 ]; then
    if [ "$url" = "$FAIL_URL" ]; then printf '503'; else printf '200'; fi
  fi
}
"""


class SeoHealthWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The workflow has one inline shell step. Keep tests tied to that source
        # rather than copying the counting commands into a separate test helper.
        workflow = WORKFLOW.read_text(encoding="utf-8")
        marker = "        run: |\n"
        if workflow.count(marker) != 1:
            raise AssertionError("Expected one inline SEO health-check step")
        cls.script = textwrap.dedent(workflow.split(marker, 1)[1])

    def run_check(self, books=60, related=6, jsonld=2, separator="", fail_url="",
                  robots="Content-Signal: search=yes\nUser-agent: GPTBot\n"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixtures = root / "fixtures"
            fixtures.mkdir()
            (fixtures / "books.html").write_text(
                separator.join(f'<a href="/book/{i}">Book</a>' for i in range(books)),
                encoding="utf-8",
            )
            (fixtures / "book.html").write_text(
                separator.join(
                    ['<a class="rel-card" href="/book/related">Related</a>'] * related
                    + ['<script type="application/ld+json">{}</script>'] * jsonld
                ),
                encoding="utf-8",
            )
            (fixtures / "robots.txt").write_text(robots, encoding="utf-8")
            summary = root / "summary.md"
            env = dict(os.environ, FIXTURE_DIR=str(fixtures), FAIL_URL=fail_url,
                       GITHUB_STEP_SUMMARY=str(summary))
            # Isolate the workflow's scratch files while preserving its commands.
            script = MOCK_CURL + self.script.replace("/tmp/", f"{root}/")
            result = subprocess.run(
                ["bash", "--noprofile", "--norc", "-e", "-u", "-o", "pipefail", "-c", script],
                capture_output=True, text=True, env=env, timeout=10,
            )
            self.assertTrue(summary.exists(), result.stdout + result.stderr)
            self.assertIn(f"- 관련 책 링크: {related}", summary.read_text(encoding="utf-8"))
            self.assertIn(f"- JSON-LD 블록: {jsonld}", summary.read_text(encoding="utf-8"))
            self.assertIn(f"- /books 내부 링크: {books}", summary.read_text(encoding="utf-8"))
            return result

    def test_compact_html_counts_every_occurrence(self):
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_multiline_html_counts_every_occurrence(self):
        result = self.run_check(separator="\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_exact_thresholds_pass(self):
        result = self.run_check(books=30, related=3, jsonld=2)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_each_below_threshold_count_fails(self):
        for counts in ({"books": 29}, {"related": 2}, {"jsonld": 1}):
            with self.subTest(counts=counts):
                result = self.run_check(**counts)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("::error::SEO health check failed", result.stdout)

    def test_each_zero_count_is_reported_without_aborting(self):
        for counts in ({"books": 0}, {"related": 0}, {"jsonld": 0},
                       {"books": 0, "related": 0, "jsonld": 0}):
            with self.subTest(counts=counts):
                result = self.run_check(**counts)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("::error::SEO health check failed", result.stdout)
                self.assertNotIn("integer expression expected", result.stderr)

    def test_http_failure_still_fails(self):
        result = self.run_check(fail_url="https://seogarok.com/sitemap.xml")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("sitemap: HTTP 503", result.stdout)

    def test_missing_robots_signals_still_fails(self):
        result = self.run_check(robots="User-agent: *\nAllow: /\n")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("robots-content-signal: 0 / ai-groups: 0", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
