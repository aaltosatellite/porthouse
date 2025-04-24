"""
    This module contains Exec module.

    .. config:: cmd: string

"""

import shlex
import asyncio

from porthouse.core.basemodule_async import BaseModule


class Exec(BaseModule):
    """
    Simple wrapper module to allow executing external programs as a module.
    """

    def __init__(self, cmd: str, **kwargs):
        """
        Initialize Exec module
        """
        super().__init__(**kwargs)
        self.cmd = shlex.split(cmd)


    async def run(self):
        """
        Run the process aka fork a child process.
        """
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *self.cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE)
            # stdout, stderr = await proc.communicate()
            await proc.wait()
            ret = proc.returncode
            if ret != 0:
                self.log.error("%s exited with code %d!", self.cmd[0], ret)
            else:
                self.log.info("%s exited with code %d", self.cmd[0], ret)

        except AttributeError:
            # Log object has been destroyed!
            pass

        except ProcessLookupError:
            pass  # Child process was killed by somebody else

        finally:
            if proc is not None:
                proc.kill()


if __name__ == "__main__":
    Exec("ls -l").run()
