"""Bounded IO tasks with callbacks drained by the Tk main thread."""

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import CancelledError
import logging
import queue
import threading


class Dispatcher:

    def __init__(self, root):
        self.root = root
        self.owner = threading.get_ident()
        self.callbacks = queue.Queue()
        self.pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="desktop-io")
        self.closed = False
        self.root.after(50, self.drain)

    def post(self, callback):
        if not self.closed:
            self.callbacks.put(callback)

    def submit(self, function):
        if self.closed:
            return
        future = self.pool.submit(function)
        future.add_done_callback(self._report)
        return future

    def _report(self, future):
        if future.cancelled():
            return
        try:
            error = future.exception()
        except CancelledError:
            return
        if error is not None:
            logging.error("Desktop background action failed: %s", type(error).__name__)
            self.post(lambda: self.root.event_generate("<<BackgroundActionFailed>>"))

    def drain(self):
        if threading.get_ident() != self.owner:
            raise RuntimeError("GUI callbacks must run on the main thread")
        while not self.callbacks.empty():
            callback = self.callbacks.get_nowait()
            try:
                callback()
            except Exception:
                logging.exception("Desktop callback failed")
        if not self.closed:
            self.root.after(50, self.drain)

    def close(self):
        self.closed = True
        self.pool.shutdown(wait=False, cancel_futures=True)
