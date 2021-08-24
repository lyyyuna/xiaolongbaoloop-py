import time, heapq
from typing import Dict, List
from selectors import EVENT_READ, EVENT_WRITE, DefaultSelector
from collections import deque
from .task import Task


class Kernel():
    def __init__(self) -> None:
        self._selector = DefaultSelector()
        self._readyq = deque()
        self._sleepq: List[(float, int, str),] = []    
        self._tasks = { } # task table

    def __enter__(self):
        return self

    def __exit__(self, ty, val, tb):
        pass

    def run(self, coro=None, *args):
        '''
        Run the kernel until no more non-daemonic tasks remain. If
        shutdown is True, the kernel cleans up after itself after all
        tasks complete
        '''

        # --- Kernel State
        current: Task = None
        selector = self._selector
        readyq = self._readyq
        tasks: Dict[Task] = self._tasks
        sleepq = self._sleepq

        # --- Number of non-daemonic tasks running
        njobs = sum(not task.daemon for task in tasks.values())

        # --- Bound methods
        selector_register = selector.register
        selector_unregister = selector.unregister
        selector_select = selector.select
        readyq_popleft = readyq.popleft
        readyq_append = readyq.append
        readyq_appendleft = readyq.appendleft
        time_monotonic = time.monotonic

        # --- Task support functions
        #
        # Create a new task, putting on the ready queue
        def _new_task(coro, daemon=False):
            nonlocal njobs
            task = Task(coro, daemon)
            tasks[task.id] = task
            if not daemon:
                njobs += 1
            _reschedule_task(task)
            return task
            
        # Reschedule a task, putting it back on the ready queue so that it can run.
        # value and exec specify a value or exeption to send into the underlying
        # coroutine when it is rescheduled.
        def _reschedule_task(task: Task, value=None, exc=None):
            readyq_append(task)
            task.state = 'READY'
            task.cancel_func = None

        # Cleaup task. This is called when the underlying coroutine is done.
        def _cleanup_task(task: Task, value=None, exc=None):
            nonlocal njobs
            task.next_value = value
            task.next_exc = exc
            task.timeout = None

            if not task.daemon:
                njobs -= 1
            
            del tasks[task.id]


        # Set a timeout or sleep event on the current task
        def _set_timeout(seconds: int, sleep_type='timeout'):
            timeout = time_monotonic() + seconds
            item = (timeout, current.id, sleep_type)
            heapq.heappush(sleepq, item)
            setattr(current, sleep_type, timeout)

        # --- Traps
        #
        # These implement the low-level functionality that is
        # triggered by coroutines. They are never invoked directly
        # and there is no public API outside the kernel. Instead,
        # coroutines use a statement such as
        #
        #  yield ('_trap_io', sock, EVENT_READ, 'READ_WAIT')
        #
        # to invoke a specific trap.

        # Wait for I/O
        def _trap_io(_, fileobj, event, state):
            pass

        # Add a new task to the kernel
        def _trap_spawn(_, coro, daemon):
            task = _new_task(coro, daemon)
            _reschedule_task(current, value=task)

        # Sleep for a specified period
        def _trap_sleep(_, seconds):
            if seconds > 0:
                _set_timeout(seconds, 'sleep')
                current.state = 'TIME_SLEEP'
                current.cancel_func = lambda task=current: setattr(task, 'sleep', None)
            else:
                _reschedule_task(current)

        # Set a timeout to be delivered to the calling task
        def _trap_set_timeout(_, seconds):
            old_timeout = current.timeout
            if seconds:
                _set_timeout(seconds)
            else:
                current.timeout = None
            readyq_appendleft(current)

        traps = { name: trap 
                    for name, trap in locals().items()
                    if name.startswith('_trap_') }

        # if a coro is given, add it as the first task
        maintask = _new_task(coro) if coro else None

        # ----------------
        # Main Kernel Loop
        # ----------------
        while njobs > 0:
            # ------
            # poll for I/O as long as there is nothing to run
            # ------
            while not readyq:
                # wait for an I/O event (or timeout)
                timeout: float = (sleepq[0][0] - time_monotonic()) if sleepq else None
                events = selector_select(timeout)

                # reschedule tasks with completed I/O
                for key, mask in events:
                    task: Task = key.data
                    task._last_io = (task.state, key.fileobj)
                    task.state = 'READY'
                    task.cancel_func = None
                    readyq_append(task)

                # process sleeping tasks
                if sleepq:
                    current_time = time_monotonic()
                    while sleepq and sleepq[0][0] <= current_time:
                        tm, taskid, sleep_type = heapq.heappop(sleepq)
                        if taskid in tasks:
                            task = tasks[taskid]
                            if sleep_type == 'sleep':
                                if tm == task.sleep:
                                    task.sleep = None
                                    _reschedule_task(task)
                            else:
                                 if tm == task.timeout:
                                     task.timeout = None
                
            # run ready tasks
            while readyq:
                current = readyq.popleft()
                try:
                    current.state = 'RUNNING'
                    current.cycles += 1
                    if current.next_exc is None:
                        trap = current._send(current.next_value)
                    else:
                        trap = current._throw(current.next_exc)
                        current.next_exc = None
                    
                    traps[trap[0]](*trap)

                except StopIteration as e:
                    _cleanup_task(task, value=e.value)
                
                except Exception as e:
                    pass

                finally:
                    if current._last_io:
                        selector_unregister(current._last_io[1])
                        current._last_io = None

        return maintask.next_value if maintask else None            


def run(coro):
    kernel = Kernel()
    return kernel.run(coro)


__all__ = ['Kernel', 'run']