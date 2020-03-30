import logging, os

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
    
    options = ["--ocr_tesseract-program=PROGRAM    path to Tesseract program [default: tesseract]"]

    async def run(self, item_list):
        logger.info(f'About tesseract {item_list}')

        with item_list as items:
            for item in items:
                basename = self._get_filename_base(item)
                tsv_filename = self._change_ext(item, 'tsv')
                await self.add_to_queue(tsv_filename, self.call_tesseract, item, basename)

            return await self.run_queue()
    
    async def call_tesseract(self, item, basename):
        try:
            cmd = f'{self.executable} {item} {basename} --psm 1 tsv'
            await self._run_command(cmd)
        except (subprocess.CalledProcessError, IOError):
            self.error("Tesseract OCR could not be executed")