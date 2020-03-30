import logging, os, platform
from tqdm import tqdm

from ..command import Cmd
from ..item import ItemList

logger = logging.getLogger(__name__)

"""
    Convert each pdf page into an image file, using ghostrscript calls
"""
class Plugin(Cmd):

    name = 'ghostscript'
    desc = 'Convert each pdf page into an image file using ghostscript'
    stage = 'image'
    inputs_from = ["setup", "analyze"]
    
    options = ['--ghostscript-program=PROGRAM    path to Ghostscript program [default: gs]']

    async def run(self, item_list, analysis_item_list):
        assert len(item_list) == 1
        logger.debug('Inside imaging')

        # Load the resolutions
        with analysis_item_list as items:
            for item in items:
                resolutions = await self.read_yaml_from_file(item)
        page_list = sorted(resolutions.keys())
            
        logger.debug(f'resolutions: {resolutions}')

        with item_list as items:
            item = items[0]
            filename, filext = os.path.splitext(item)
            for page in page_list:
                res_x, res_y = resolutions[page][0:2]
                output_filename = f'{filename}_{page}.png'
                await self.add_to_queue(output_filename, self.call_ghostscript, 
                                            item, page, output_filename, res_x, res_y)
 
            return await self.run_queue()


    async def call_ghostscript(self, item, page, output_filename, res_x, res_y):
        cmd = f'{self.executable} -q -dNOPAUSE -dFirstPage={page} -dLastPage={page} -sOutputFile="{output_filename}" -sDEVICE=png16m -r{res_x}x{res_y} "{item}" -c quit'
        await self._run_command(cmd)