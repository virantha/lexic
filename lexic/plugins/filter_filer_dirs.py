import logging, os, sys, shutil, datetime

from pathlib import Path

from ..command import Cmd
from ..item import ItemList
from ..keyword_filer import KeywordFiler

logger = logging.getLogger(__name__)

"""
    File pdfs into a directory structure
"""
class DirFiler(KeywordFiler):
    # Need to augment the validator to create directories,
    # as well as store originals

    def _load_yaml_and_validate(self, keyword_filename):
        super()._load_yaml_and_validate(keyword_filename)

        file_folders = list(self.yaml_config['folders'].keys())
        self.root_path = Path(self.yaml_config['root'])

        # Check all folders are present
        if self._check_folder_exists(self.root_path):
            for folder in file_folders+[self.yaml_config['default']]+[self.yaml_config.get('originals', '')]:
                folder_path = self.root_path / Path(folder)
                if not self._check_folder_exists(folder_path):
                    print(f'Creating filing folder {folder_path}')
                    os.makedirs(folder_path)
        else:
            print(f'Root filing folder {self.root_path} does not exist. Please create it first')
            sys.exit(-1)

        # If the originals is specified, then create an variable to use later
        if 'originals' in self.yaml_config:
            self.originals_path = self.root_path / Path(self.yaml_config['originals'])
        else:
            self.originals_path = None


    def _check_folder_exists(self, foldername):
        path = Path(foldername)
        if not path.is_dir():
            return False
        else:
            return True


        
class Plugin(Cmd):

    name = 'filedirs'
    desc = 'File PDFs into directories'
    stage = 'filter'
    filter_on_output = ['clean']
    inputs_from = ['clean','setup']
    
    options = ['--filedirs-keywords=FILE     Keyword files']

    """ yaml file input:

        folders:
            folder_name:  
                - keyword/phrase
                - keyword/phrase
            folder_name:
                - 
    """
    def _find_executable(self):
        return

    async def run(self, item_list, original_pdf_list):
        logger.info(f'About to file into directories {item_list}')

        yaml_filename = self.config['keywords']

        # Read in the keyword files
        with item_list as items:
            item = items[0]
            filer = DirFiler(yaml_filename, item)
            folder = filer.find_matching_folder()
            folder = Path(filer.root_path) / Path(folder)
            logger.debug(f'Filing to folder {folder}')
            # Don't overwrite anything.  Just increment a suffix on the filename
            basename = self._get_filename_base(item)
            ext      = self._get_filename_ext(item)

            tgt_path = folder / Path(f'{basename}{ext}')
            i = 2
            while tgt_path.exists():
                tgt_path = folder / Path(f'{basename}.{i}{ext}')
                i += 1
            shutil.copy2(item, tgt_path)
            await self.add_message(f'Copied OCR pdf {item} to {tgt_path}')

            # Now, file the original if needed
            if filer.originals_path:
                tgt_path = Path(filer.originals_path)
                dt = filer.find_closest_date()
                year = dt.year
                tgt_path = tgt_path / Path(f'{year}')
                if not filer._check_folder_exists(tgt_path):
                    os.makedirs(tgt_path)
                shutil.copy2(self.original_pdf_filename, tgt_path)
                await self.add_message(f'Copied original to {tgt_path}')

        return item_list
    