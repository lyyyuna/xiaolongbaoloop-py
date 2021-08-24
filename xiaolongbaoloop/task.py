__all__ = ['sleep']

from .traps import _sleep


class Task:
    _lastid = 1
    def __init__(self, coro, daemon=False):
        self.coro = coro
        self.id = Task._lastid
        Task._lastid += 1
        
        self.cycles = 0         # execution cycles completed
        self.state = 'INITIAL'  # execution state
        self.daemon = daemon
        self.timeout = None
        self.sleep = None
        self.cancel_func = None    # Cancellation function

        self._last_io = None    # last I/O operation performed
        self._send = coro.send
        self._throw = coro.throw

        self.exc_info = None        # exception info
        self.next_value = None      # next value to send on execution
        self.next_exc = None        # next exception to send on execution

    def send(self, value):
        return self._send(value)

    async def _task_runner(self, coro):
        try:
            return await coro
        finally:
            pass


async def sleep(seconds):
    await _sleep(seconds)