import logging, os, platform, shutil

from ..command import Cmd
from ..item import ItemList

logger = logging.getLogger(__name__)

"""
    Setup temp directories
"""
class Plugin(Cmd):

    name = 'setup_ocr'
    desc = 'Setup work directories and copy files'
    stage = 'setup'
    inputs_from = []
    
    options = []

    def _find_executable(self):
        return 

    async def run(self, filename):

        # Copy the pdf file over
        # return an ItemList with the pdf file
        abspath = os.path.abspath(filename)
        dirname = os.path.dirname(abspath)
        filename = os.path.basename(abspath)

        base_filename, extension = os.path.splitext(filename)

        # Create the temp directory

        base_tgtdir = os.path.join(dirname, base_filename)
        tgtdir = base_tgtdir


        # Keep searching for the first increment path that doesn't exist
        #  This will be stored in new_tgtdir
        # The last path that exists will be in tgtdir
        inc = 0
        new_tgtdir = base_tgtdir + f'_{inc}'
        while True:
            if not os.path.exists(new_tgtdir): 
                break
            inc += 1 
            tgtdir = new_tgtdir
            new_tgtdir = base_tgtdir + f'_{inc}'
        # 
        if self.skip:
            pass  # Use the existing path on disk
        else:
            # Go to a new directory
            tgtdir = new_tgtdir
            logger.debug(f'Making directory {tgtdir} for processing')
            os.mkdir(tgtdir)
            logger.debug(f'Copying pdf file {abspath} to {tgtdir}')
            shutil.copy2(abspath, tgtdir)

        logger.debug(f'{tgtdir} is ready')

        copied_filename = os.path.join(tgtdir, filename)
        item_list = ItemList([copied_filename])
        logging.info(f'Using {tgtdir} as work directory')
        return item_list
