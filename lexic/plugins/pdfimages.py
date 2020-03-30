import logging, os, platform

from ..command import Cmd
from ..item import ItemList

logger = logging.getLogger(__name__)

"""
    Convert each pdf page into an image file, using ghostrscript calls
"""
class Plugin(Cmd):

    name = 'pdfimages'
    desc = 'Analyze images to find DPI and dimensions using pdfimages'
    stage = 'analyze'
    inputs_from = ["setup"]
    
    options = ["--pdfimages-program=PROGRAM           path to the PdfImages program [default: pdfimages]"]

    async def run(self, item_list):
        assert len(item_list) == 1
        logger.debug('Inside pdfimages')
        next_items = ItemList()
        with item_list as items:
            item = items[0]
            cmd = f'pdfimages -list {item}'
            # Now store each resolution to file
            resolutions_filename = self._change_ext(item, 'res')

            if not self.skip:
                out = await self._run_command(cmd)
                resolutions = self._get_resolutions(out)
                await self.write_yaml_to_file(resolutions_filename, resolutions)
            next_items.append(resolutions_filename)
        
        return next_items


    def _get_resolutions(self, pdfimage_output):
        lines = [l.decode('utf-8') for l in pdfimage_output.splitlines()]
        logger.debug('\n'.join(lines))
        resolutions = {}
        if len(lines) < 3:
            return resolutions # Noting to do here
        else:
            header_line = lines[0]
            if lines[1].startswith('---'):
                image_lines = lines[2:]  # Actual image listing starts at line 3
            else:
                image_lines = lines[1:]  # Image listing starts here
            # Now, split up the header line and find x-ppi and y-ppi
            header = header_line.split()
            indices = { k:i for i,k in enumerate(header) }  # Dict of 'column_name' to column number
            for image_line in self.iterate_with_progress(image_lines):
                image = image_line.split()
                image_type = image[indices['type']]
                if image_type == 'image' or image_type == 'stencil':
                    try:
                        page = int(image[indices['page']])
                        xdpi = int(image[indices['x-ppi']])
                        ydpi = int(image[indices['y-ppi']])
                        width = int(image[indices['width']])
                        height = int(image[indices['height']])
                    except ValueError or IndexError:
                        logging.debug(f'Error Processing |{image}|')
                    else:
                        if page not in resolutions: 
                            resolutions[page] = (xdpi, ydpi, width, height)
                        else:
                            # If there's already an image on that page, keep upping the resolution
                            # if necessary
                            x, y, w, h = resolutions[page]
                            old_area = w / x * h / y
                            new_area = width / xdpi * height / ydpi
                            if old_area < new_area:
                                resolutions[page] = (xdpi, ydpi, width, height)

            return resolutions
                
            