import logging, os
import yaml

from ..command import Cmd
from ..item import ItemList

logger = logging.getLogger(__name__)
"""
    Read in each tsv file and return the text and locations
"""

class Plugin(Cmd):

    name = 'ocr_tsv_parse'
    desc = 'Process output of tesseract tsv file into text'
    stage = 'text_process'
    inputs_from = ['ocr']

    options = []

    def _find_executable(self):
        return 

    async def run(self, item_list):
        logger.info(f'About to parse TSV {item_list}')
        
        next_items = ItemList()
        with item_list as items:
            for item in self.iterate_with_progress(items):
                logger.debug(f'Processing tsv {item}')
                next_file = self._change_ext(item, 'loc')

                if not self.skip:
                    with open(item, 'r', encoding='utf8') as f:
                        tsv_contents = f.readlines()
                    text_locations = await self.process_tsv(tsv_contents)
                    logger.debug(text_locations)
                    # Create a file to store each text in a separate file with yaml
                    with open(next_file, 'w') as loc_file:
                        yaml.dump(text_locations, loc_file)
                next_items.append(next_file)
        return next_items
                
    async def process_tsv(self, tsv):
        """
        """
        
        # 
        text_locations = {}  # (Xl, Yl, Xr, Yr) => text
        header = tsv[0].strip().split('\t')
        indices = { k:i for i,k in enumerate(header) }
        # level, page_num, block_num, par_num, line_num, word_num, left, top, width, height, conf, text

        for line in tsv[1:]:
            line = line.strip()
            fields = line.split('\t')
            confidence = int(fields[indices['conf']])
            try: 
                if confidence > 0:
                    col_names = ['block_num', 'par_num', 'line_num', 'word_num', 'left', 'top', 'width', 'height']
                    field_values = [int(fields[indices[col_name]]) for col_name in col_names]
                    text = fields[indices['text']]
                    text_locations[ tuple(field_values) ] = text
            except IndexError:
                logger.debug('Cannot parse line in tsv: ')
                logger.debug(line)

        return text_locations



