import tempfile
import unittest

from Downloader_GUI import DownloaderApp
from tronclass_client import BatchResult


class GuiTests(unittest.TestCase):
    def test_widgets_and_worker_events(self):
        with tempfile.TemporaryDirectory() as directory:
            app = DownloaderApp(settings_directory=directory)
            app.withdraw()
            try:
                self.assertEqual(app.mode.get(), "整門課教材")
                app.events.put(("progress", (2, 3)))
                app.events.put(("result", BatchResult(downloaded=2, failures=[{"error": "test"}], directory=directory)))
                app.events.put(("done", None))
                app.poll_events()
                self.assertAlmostEqual(app.progress.get(), 2 / 3)
                self.assertIn("部分失敗", app.status.cget("text"))
                self.assertEqual(app.retry_btn.cget("state"), "normal")
                self.assertEqual(app.log_box.cget("state"), "disabled")
                app.cancel_download()
                self.assertTrue(app.cancel_event.is_set())
                self.assertEqual(app.entry_pwd.get(), "")
            finally:
                app.destroy()


if __name__ == "__main__":
    unittest.main()
