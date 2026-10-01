import os
import tempfile
import unittest
from pathlib import Path

from flask import Flask

import app.draft_bp as draft_module


class EditorialAtlasRoutesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.research = Path(self.temp.name)
        (self.research / "wiki").mkdir()
        (self.research / "img").mkdir()
        (self.research / "post.md").write_text(
            "# Hyderabad, explained with data\n\n**A reusable story.**\n\n"
            "![Night lights](img/night-lights.svg)\n\n"
            "[See data](wiki/data-night-lights.md)\n",
            encoding="utf-8",
        )
        (self.research / "wiki" / "data-night-lights.md").write_text(
            "# Night-light growth\n\nWhat this measures.\n\n"
            "[Back](../post)\n",
            encoding="utf-8",
        )
        (self.research / "img" / "night-lights.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"></svg>',
            encoding="utf-8",
        )
        self.original_research_dir = draft_module.RESEARCH_DIR
        draft_module.RESEARCH_DIR = self.research
        os.environ.pop("DRAFT_PASSWORD", None)

        templates = Path(draft_module.__file__).parent / "templates"
        static = Path(draft_module.__file__).parent / "static"
        self.app = Flask(__name__, template_folder=str(templates), static_folder=str(static))
        self.app.secret_key = "test"
        self.app.register_blueprint(draft_module.draft_bp)
        self.client = self.app.test_client()

    def tearDown(self):
        draft_module.RESEARCH_DIR = self.original_research_dir
        os.environ.pop("DRAFT_PASSWORD", None)
        self.temp.cleanup()

    def test_story_renders_and_rewrites_research_links(self):
        response = self.client.get("/draft/atlas")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Hyderabad, explained with data", html)
        self.assertIn('src="/draft/img/night-lights.svg"', html)
        self.assertIn('href="/draft/data/night-lights"', html)
        self.assertEqual(response.headers["X-Robots-Tag"], "noindex, nofollow")

    def test_hub_discovers_dataset_pages(self):
        response = self.client.get("/draft/data")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Night-light growth", response.get_data(as_text=True))

    def test_analysis_and_unknown_slug(self):
        response = self.client.get("/draft/data/night-lights")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Data & method", html)
        self.assertIn("/draft/img/night-lights.svg", html)
        self.assertIn('href="/draft/atlas"', html)
        self.assertEqual(self.client.get("/draft/data/not-present").status_code, 404)

    def test_password_gate_still_applies(self):
        os.environ["DRAFT_PASSWORD"] = "secret"
        response = self.client.get("/draft/atlas")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/draft/login", response.headers["Location"])


if __name__ == "__main__":
    unittest.main()
