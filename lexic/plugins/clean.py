import logging, os, shutil

from ..command import Cmd
from ..item import ItemList

logger = logging.getLogger(__name__)

"""
    Cleanup files
"""

class Plugin(Cmd):

    name = 'cleanup'
    desc = 'Clean up temporary files'
    stage = 'clean'
    inputs_from = ['merge_overlay', 'setup', 'analyze', 'image', 'orient', 'ocr', 'text_process', 'create_overlay']
    
    options = ['--cleanup-preserve          do not delete temporary files']

    def _find_executable(self):
        return

    async def run(self, final_pdf_list, *item_lists):

        # Move the ocr file back to the original directory
        cwd = os.getcwd()

        try:
            with final_pdf_list as final_items:
                assert len(final_items) == 1, 'Something went wrong with final pdf generation (more than one output file found)'
                final_pdf_filename = final_items[0]
                shutil.copy2(final_pdf_filename, cwd)
                pdf_base = self._get_filename_base(final_pdf_filename)
                pdf_ext = self._get_filename_ext(final_pdf_filename)
                output_filename = os.path.join(cwd, f'{pdf_base}{pdf_ext}')
                if not self.config['preserve']:
                    os.remove(final_pdf_filename)

            for item_list in self.iterate_with_progress(item_lists):
                with item_list as items:
                    for item in items:
                        logging.debug(f'Cleanup - {item}')
                        if not self.config['preserve']:
                            os.remove(item)
            if not self.config['preserve']:
                os.removedirs(item_lists[0].common_dir)
        except OSError as e:
            self.error(f'Could not do cleanup step - {e}')
        
        await self.add_message('done')
        return ItemList([output_filename])
    