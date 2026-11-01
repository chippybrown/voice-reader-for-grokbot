import os
import shutil
import socket
import tempfile
import time
import unittest

import single_instance


class SingleInstanceTests(unittest.TestCase):
    def test_second_launch_wakes_the_first_and_does_not_stay(self):
        directory = tempfile.mkdtemp()
        try:
            seen = []
            first = single_instance.InstanceLock(directory)
            self.assertTrue(first.claim(lambda: seen.append("focus")))
            second = single_instance.InstanceLock(directory)
            self.assertFalse(second.claim(lambda: seen.append("second")))
            for _ in range(50):
                if seen:
                    break
                time.sleep(0.02)
            self.assertEqual(seen, ["focus"])
            first.release()
            third = single_instance.InstanceLock(directory)
            self.assertTrue(third.claim(lambda: None))
            third.release()
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_a_socket_left_by_a_crash_does_not_block_the_next_start(self):
        directory = tempfile.mkdtemp()
        try:
            stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            stale.bind(os.path.join(directory, "instance.sock"))
            stale.close()
            lock = single_instance.InstanceLock(directory)
            self.assertTrue(lock.claim(lambda: None))
            lock.release()
            self.assertFalse(os.path.exists(lock.path))
        finally:
            shutil.rmtree(directory, ignore_errors=True)
