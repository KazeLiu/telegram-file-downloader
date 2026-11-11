"""Background image-index checks using temporary data only."""
import asyncio
import tempfile
import unittest
from pathlib import Path

from telegram_file_downloader.image_library import ImageLibrary


class ImageBackgroundTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.library = ImageLibrary(root, root)

    async def asyncTearDown(self):
        await self.library.close()
        self.directory.cleanup()

    async def test_changes_during_scan_are_coalesced_into_another_pass(self):
        started, release = asyncio.Event(), asyncio.Event()
        passes = []

        async def scan():
            passes.append(len(passes))
            if len(passes) == 1:
                started.set()
                await release.wait()

        self.library._scan = scan
        self.library.start_scan()
        task = self.library.task
        await started.wait()
        self.library.start_scan()
        self.library.start_scan()
        self.assertIs(self.library.task, task)
        release.set()
        await task
        self.assertEqual(len(passes), 2)
        self.assertFalse(self.library.state["running"])

    async def test_pending_images_do_not_block_ready_image_pagination(self):
        self.library.db.executemany("""INSERT INTO images(name,size,mtime_ns,sort_time,time_source,monochrome)
            VALUES (?,?,?,?,?,?)""", [
                (f"ready-{index}.jpg", 1, index * 1000000, index, "modified", 1) for index in range(65)
            ] + [("pending.jpg", 1, 999000000, 999, None, None)])
        self.library.db.commit()
        self.library.state["running"] = True
        first = self.library.listing()
        self.assertEqual(len(first["items"]), 60)
        self.assertEqual(first["total"], 65)
        self.assertEqual(first["counts"]["total"], 66)
        self.assertEqual(first["counts"]["ready"], 65)
        second = self.library.listing(after=first["next_cursor"])
        self.assertEqual(len(second["items"]), 5)
        self.assertIsNone(second["next_cursor"])
        self.assertEqual(self.library.status(search="pending")["total"], 0)


if __name__ == "__main__":
    unittest.main()
