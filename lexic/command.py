
"""
    Base class to represent all the external commands we have to invoke
"""
import platform, logging, shutil, os, sys, io, base64
from pathlib import Path
from requests import Request, Session
import requests
from tenacity import retry, wait_random, wait_fixed, stop_after_attempt, wait_random_exponential, stop_after_delay
from curio import subprocess, spawn, Queue
from curio.file import aopen
import curio, asks
asks.init('curio')

import boto3

from tqdm import tqdm
import yaml
import json

logger = logging.getLogger(__name__)

from .exc import UnsupportedOSError, UnknownExecutableError
from .item import ItemList


session = Session()
session_adapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=100)
session.mount('https://', session_adapter)

asks_session = asks.Session(connections=100)

class Cmd:

    plugin_list = {}
    stage = ''
    pre_step = []
    post_step = []
    inputs_from = []
    N_THREADS = 1
    msg_queue = Queue()

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
    
    async def _get_aws_signed_url(self, url):
        response = await asks_session.get(url, retries=3)
        response.raise_for_status()
        return response.json()

    def _aws_post_file(self, filename, signed_response):
        # This is the requests version just for posterity (run it in curio.run_in_thread)
        upload_url = signed_response['url']
        upload_data = signed_response['fields']
        upload_filename = upload_data['key']
        with open(filename, 'rb') as f:
            files = {'file': (upload_filename, f)}
            req = Request('POST', upload_url, data=upload_data, files=files)
            prepared_req = req.prepare()
            http_response = session.send(prepared_req)
            http_response.raise_for_status()

    async def _aws_asks_post_file(self, filename, signed_response):
        upload_url = signed_response['url']
        upload_data = signed_response['fields']
        upload_filename = upload_data['key']

        data = upload_data
        data['file'] = Path(filename)
        http_response = await asks_session.post(upload_url, multipart=data)
        http_response.raise_for_status()

    @retry(sleep=curio.sleep, wait=wait_random_exponential(multiplier=1, max=60), stop=stop_after_delay(10))
    async def _aws_upload_file(self, url, filename):
        # Get signed URL for AWS S3
        # POst to signed URL
        #url_response = await curio.run_in_thread(self.get_aws_signed_url, url)
        url_response = await self._get_aws_signed_url(url)

        # Not sure why i can't use asks here to post the files
        #response = await curio.run_in_thread(self._aws_post_file, filename, url_response)
        response = await self._aws_asks_post_file(filename, url_response)
        return url_response

    @retry(sleep=curio.sleep, wait=wait_random_exponential(multiplier=1, max=60), stop=stop_after_delay(10))
    async def _aws_run_command(self, url, input_files, cmd, output_filenames):
        """Post to aws to run the specified commands with input files, and return
           the output files
        """
        json = {
            'input_files': input_files,
            'cmd': cmd,
            'output_files': [os.path.basename(fn) for fn in output_filenames],
        }
        response = await asks_session.post(url, json=json)
        response.raise_for_status()
        return response.json()

    async def run_command_aws(self, cmd, input_filenames, output_filenames, url):
        logger.debug(f'Running in aws: {cmd}')
        endpoint_run_ocr = f'{url}/ocr'
        endpoint_get_signed_url = f'{url}/geturl'

        # First, upload the input_files
        input_files = []
        for input_filename in input_filenames:
            logger.debug(f'Uploading file {input_filename} to S3')
            url_response = await self._aws_upload_file(endpoint_get_signed_url, input_filename)
            input_files.append((url_response['fields']['key'], os.path.basename(input_filename)))

        logging.info(f'Posting to aws {cmd}')
        response_dict = await self._aws_run_command(endpoint_run_ocr, input_files, cmd, output_filenames)
        logging.debug (response_dict['message'])

        #print (list(response_dict['output_files'].keys()))
        for output_filename in output_filenames:
            contents = response_dict['output_files'][os.path.basename(output_filename)]
            b64 = base64.b64decode(contents)
            async with aopen(str(output_filename), 'wb') as f:
                await f.write(b64)

            
    async def add_to_queue(self, output_filename, task_func, *task_args):
        self.queue[output_filename] = (task_func, *task_args)

    async def add_message(self, msg):
        #msg = f'{self.name}: {msg}'
        msg = (self.name, msg)
        await Cmd.msg_queue.put(msg)

    async def get_messages(self):
        msgs = []
        while not Cmd.msg_queue.empty():
            msg = await Cmd.msg_queue.get()
            msgs.append(msg)
            await Cmd.msg_queue.task_done()
        return msgs

    async def spawn_with_update(self, pbar, task):
        await task[0](*task[1:]) 
        pbar.update(1)

    async def run_queue(self):
        t_list = []  # All currently executing tasks
        output_filenames = []
        n = len(self.queue)
        if self.skip:
            desc = f'{self.name} [skipped]'
        else:
            desc = self.name

        with tqdm(total=n, desc=desc) as pbar:
            for output_filename, task in self.queue.items():
                output_filenames.append(output_filename)
                if not self.skip:
                    t = await spawn(self.spawn_with_update, pbar, task)
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


        
