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
    def __init__(self, config, pdf_filename):
        super().__init__(config, pdf_filename)
        # If the originals is specified, then create an variable to use later
        if 'originals' in config:
            self.originals_path = Path(config['originals'])
        else:
            self.originals_path = None
        self._validate_paths()

    def _validate_paths(self):
        file_folders = list(self.folders_to_keywords.keys())
        self.root_path = Path(self.root_path)

        # Check all folders are present
        if self._check_folder_exists(self.root_path):
            folders_to_check = file_folders + [self.default_path]
            if self.originals_path: folders_to_check.append(self.originals_path)
            for folder in folders_to_check:
                folder_path = self.root_path / Path(folder)
                if not self._check_folder_exists(folder_path):
                    print(f'Creating filing folder {folder_path}')
                    os.makedirs(folder_path)
        else:
            print(f'Root filing folder {self.root_path} does not exist. Please create it first')
            sys.exit(-1)



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
    
    #options = ['--filedirs-keywords=FILE     Keyword files']
    options = ['--filedirs-root=NAME       Root directory', 
               '--filedirs-default=NAME    Default directory to file in if no match', 
               '--filedirs-originals=NAME  Where to file original pdf', 
    ]

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

        # Read in the keyword files
        with item_list as items:
            item = items[0]
            filer = DirFiler(self.config, item)
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
                tgt_path = Path(filer.root_path) / Path(filer.originals_path)
                dt = filer.find_closest_date()
                year = dt.year
                tgt_path = tgt_path / Path(f'{year}')
                if not filer._check_folder_exists(tgt_path):
                    os.makedirs(tgt_path)
                shutil.copy2(self.original_pdf_filename, tgt_path)
                await self.add_message(f'Copied original to {tgt_path}')

        return item_list
    