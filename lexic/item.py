from collections import UserList
import os, logging
from tqdm import tqdm

logger = logging.getLogger(__name__)

class ItemList(UserList):

    """
        Represents all the collateral needed to locate and process an Item 

        Each item should be: 

            - Iterable to return all the files
            - Context manager to cd into location

    """

    def __init__(self, *items):
        self.common_dir = None
        super().__init__(*items)
        for item in self.data:
            self._check_common_dir(item)

    def _check_common_dir(self, filename):
        """ Check a filename's dir against the self.common_dir and make sure they are the same
        """
        abspath = os.path.abspath(filename)
        dirname = os.path.dirname(abspath)
        # Assert that this is a file
        assert os.path.isfile(abspath), f'Cannot find {abspath} to file list'

        if self.common_dir:
            assert self.common_dir == dirname, f'New item has dir {dirname} while earlier common dir is {self.common_dir}'
        else:
            logger.debug(f'Setting common dir to {dirname}')
            self.common_dir = dirname

    def __setitem__(self, index, value):
        self._check_common_dir(value)
        self.data[index] = value

    def append(self, value):
        self._check_common_dir(value)
        self.data.append(value)

    def __enter__(self):
        self.cwd = os.getcwd()
        assert self.common_dir is not None, f'Common dir is not defined!'
        os.chdir(self.common_dir)
        logger.debug(f'Changed dir in context manager to {self.common_dir}')
        return self.data


    def __exit__(self, exc_type, exc_value, exc_traceback):
        os.chdir(self.cwd)

