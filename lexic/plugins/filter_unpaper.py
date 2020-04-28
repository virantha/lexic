import logging, os, platform

from ..command import Cmd
from ..item import ItemList

logger = logging.getLogger(__name__)

"""
    Try to clean up input using unpaper
"""
class Plugin(Cmd):

    name = 'unpaper'
    desc = 'Clean up input using unpaper'
    stage = 'filter'
    filter_on_output = ['image']

    inputs_from = ['image']

    options = ["--unpaper-program=PROGRAM   path to unpaper preprocessor [default: unpaper]"]

    async def run(self, item_list):
        with item_list as items:
            for item in items:
                logger.debug(f'About to preprocess {item}')
                current_extension = self._get_filename_ext(item)
                out_filename = self._change_ext(item, f'pre{current_extension}')
                await self.add_to_queue(out_filename, self.run_unpaper, item, out_filename)
            return await self.run_queue()

    async def run_unpaper(self, item, out_filename):
        await self._run_command(f'{self.executable} --no-mask-center --no-border-align {item} {out_filename}')