import logging, os, platform

from ..command import Cmd
from ..item import ItemList

logger = logging.getLogger(__name__)

"""
    Try to clean up input
"""
class Plugin(Cmd):

    name = 'imagemagick'
    desc = 'Clean up input using manual imagemagick (convert) run'
    stage = 'filter'
    filter_on_output = ['image']
    inputs_from = ["image"]

    options = ["--imagemagick-program=PROGRAM   path to ImageMagick preprocessor [default: convert]"]

    async def run(self, item_list):
        next_items = ItemList()
        with item_list as items:
            for item in self.iterate_with_progress(items):
                logger.debug(f'About to preprocess {item}')
                next_item = await self.run_image_magick(item)
                next_items.append(next_item)
        return next_items

    async def run_image_magick(self, item):
        current_extension = self._get_filename_ext(item)
        out_filename = self._change_ext(item, f'pre{current_extension}')
        if str(os.name) == 'nt':
            backslash = ''
        else:
            backslash = '\\'

        c = ['convert',
                '"%s"' % item,
                '-respect-parenthesis',
                #'\\( $setcspace -colorspace gray -type grayscale \\)',
                backslash+'(',
                '-clone 0',
                '-colorspace gray -negate -lat 15x15+5% -contrast-stretch 0',
                backslash+') -compose copy_opacity -composite -opaque none +matte -modulate 100,100',
                #'-adaptive-blur 1.0',
                '-blur 1x1',
                #'-selective-blur 4x4+5%',
                '-adaptive-sharpen 0x2',
                '-negate -define morphology:compose=darken -morphology Thinning Rectangle:1x30+0+0 -negate ',  # Removes vertical lines >=60 pixes, reduces widht of >30 (oherwise tesseract < 3.03 completely ignores text close to vertical lines in a table)
                '"%s"' % (out_filename)
                ]
        await self._run_command(' '.join(c))
        return out_filename