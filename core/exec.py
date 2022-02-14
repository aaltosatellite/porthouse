"""
    This module contains Exec module.

    .. config:: cmd: string

"""

import shlex
import subprocess

from porthouse.core.static_basemodule import BaseModule

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


    def run(self):
        """
        Run the process aka fork a child process.
        """
        try:
            proc = subprocess.Popen(self.cmd)
            ret = proc.wait()
            print("%s exited with code %d!" % (self.cmd[0], ret))
            self.log.error("%s exited with code %d!", self.cmd[0], ret)

        except AttributeError:
            # Log object has been destroyed!
            pass

        except ProcessLookupError:
            pass  # Child process was killed by somebody else

        finally:
            proc.kill()


if __name__ == "__main__":
    Exec("ls -l").run()
