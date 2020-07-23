import logging, os, subprocess, traceback

from tenacity import retry

from ..command import Cmd
from ..item import ItemList

logger = logging.getLogger(__name__)

"""
    Run ocr
"""

class Plugin(Cmd):

    name = 'ocr_tesseract'
    desc = 'Run ocr using tesseract'
    stage = 'ocr'
    inputs_from = ['image']
    
    options = ["--ocr_tesseract-program=PROGRAM    path to Tesseract program [default: tesseract]",
               "--ocr_tesseract-aws                run in cloud",
               "--ocr_tesseract-awsurl=URL         endpoint to use for aws"
    ]

    async def run(self, item_list):
        logger.info(f'About tesseract {item_list}')

        with item_list as items:
            n_items = len(items)
            old_n_threads = self.N_THREADS
            if self.config['aws']:
                self.N_THREADS=n_items
                assert self.config['awsurl'] is not None, 'URL for AWS services not specified'

            for item in items:
                basename = self._get_filename_base(item)
                tsv_filename = self._change_ext(item, 'tsv')
                if self.config['aws']:
                    run_method = self.call_tesseract_aws
                else:
                    run_method = self.call_tesseract
                await self.add_to_queue(tsv_filename, run_method, item, basename)

            out_filenames = await self.run_queue()
            self.N_THREADS = old_n_threads
            
            return out_filenames

    async def call_tesseract(self, item, basename):
        try:
            cmd = f'{self.executable} {item} {basename} --psm 1 tsv'
            await self._run_command(cmd)
        except (subprocess.CalledProcessError, IOError):
            self.error("Tesseract OCR could not be executed")

    async def call_tesseract_aws(self, item, basename):
        try:
            #print(f"Calling aws! {item}")
            cmd = f'{self.executable} {os.path.basename(item)} {basename} --psm 1 tsv'
            await self.run_command_aws(cmd, [item], [f'{basename}.tsv'], self.config['awsurl'] )
        except Exception as e:
            print(str(e))
            print(f"ERROR: Tesseract OCR could not be executed on {item}")
            traceback.print_exc()