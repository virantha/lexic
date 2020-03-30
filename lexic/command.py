
"""
    Base class to represent all the external commands we have to invoke
"""
import platform, logging, shutil, os, sys
from curio import subprocess, spawn
from tqdm import tqdm
import yaml

logger = logging.getLogger(__name__)

from .exc import UnsupportedOSError, UnknownExecutableError
from .item import ItemList

class Cmd:

    plugin_list = {}
    stage = ''
    pre_step = []
    post_step = []
    inputs_from = []
    N_THREADS = 1

    def __init__(self, config, skip=False):
        self.config = config
        self._find_executable()
        self.skip = skip
        self.queue = {}
        logging.debug(f'{self.name} skip={skip}')


    @staticmethod
    def register_plugin(new_plugin):
        # First do the registration of this flow step with the registry
        stage_plugins = Cmd.plugin_list.setdefault(new_plugin.stage, {})
        stage_plugins[new_plugin.name] = new_plugin
        logger.debug(f'registered {new_plugin} to plugin_list')

    def _find_executable(self):
        os_ = platform.system()
        
        if os_ == 'Linux':
            logging.debug('linux')
            #raise UnsupportedOSError
        elif os_ == 'Windows':
            logging.debug('Windows')
            raise UnsupportedOSError
        elif os_ == 'Darwin':
            logging.debug('Mac')
        else:
            raise UnsupportedOSError

        if 'program' in self.config:
            self.executable = self.config['program']
        else:
            #raise UnknownExecutableError(f'Could not find executable for {self.__class__.__name__}')
            raise UnknownExecutableError(f'Could not find executable for {self.__class__.name}')

    def _get_filename_base(self, path):
        """ Return the base name without the extension
        """
        basename, ext = os.path.splitext(os.path.basename(path))
        return basename

    def _get_filename_ext(self, path):
        """ Return the extension without anything else 
        """
        basename, ext = os.path.splitext(os.path.basename(path))
        return ext

    def _change_ext(self, path, new_ext):
        """Take the file name as is and return an abspath with the extension changed
        """
        assert not new_ext.startswith('.'), 'New extension must not start with a period'
        directory = os.path.dirname(os.path.abspath(path))
        basename = self._get_filename_base(path)

        return os.path.abspath(os.path.join(directory, f'{basename}.{new_ext}'))

    def iterate_with_progress(self, items, total=None):
        """

        """
        if not total: total = len(items) 
        if self.skip:
            desc = f'{self.name} [skipped]'
        else:
            desc = self.name
        with tqdm(total=total, desc=desc) as pbar:
            for item in items:
                yield item
                pbar.update(1)

    async def _run_command(self, cmd):
        logger.debug(cmd)
        output = await subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)
        return output

    async def run_in_parallel(self, tasks):
        t_list = []  # All currently executing tasks
        for task in self.iterate_with_progress(tasks):
            if not self.skip:
                t = await spawn(task[0], *task[1:])  
                t_list.append(t)
                if len(t_list) == self.N_THREADS:
                    for t in t_list:
                        await t.join()
                    t_list = []
        if not self.skip:
            for t in t_list:
                await t.join()
            
    async def add_to_queue(self, output_filename, task_func, *task_args):
        self.queue[output_filename] = (task_func, *task_args)

    async def run_queue(self):
        t_list = []  # All currently executing tasks
        output_filenames = []
        for output_filename, task in self.iterate_with_progress(self.queue.items()):
            output_filenames.append(output_filename)
            if not self.skip:
                t = await spawn(task[0], *task[1:])  
                t_list.append(t)
                if len(t_list) == self.N_THREADS:
                    for t in t_list:
                        await t.join()
                    t_list = []
        if not self.skip:
            # Flush out any remaining jobs in the queue (when N_THREADS is not an int factor of the task count)
            for t in t_list:
                await t.join()
        self.queue = {}  # Empty all the jobs
        return ItemList([os.path.abspath(p) for p in output_filenames])

    def error(self, msg):
        print(f'ERROR: {msg}')
        sys.exit(-1)

    async def write_yaml_to_file (self, filename, python_dict):
        with open(filename, 'w') as f:
            yaml.dump(python_dict,f)
    
    async def read_yaml_from_file(self, filename):
        with open(filename) as f:
            d = yaml.load(f)
        return d


        
