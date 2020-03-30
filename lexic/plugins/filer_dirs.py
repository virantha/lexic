import logging, os, sys, shutil

import yaml
from pathlib import Path
from PyPDF2 import PdfFileReader


from ..command import Cmd
from ..item import ItemList

logger = logging.getLogger(__name__)

"""
    File pdfs into a directory structure
"""
class KeywordFiler:

    def __init__(self, keyword_filename, pdf_filename):
        self._load_yaml_and_validate(keyword_filename)
        self.pdf_filename = pdf_filename
        self.reader = PdfFileReader(pdf_filename)

    def _load_yaml_and_validate(self, keyword_filename):
        with open(keyword_filename) as f:
            self.yaml_config = yaml.load(f)
        file_desc = 'YAML keywod file {keyword_filename}'
        assert 'root' in self.yaml_config, f'{file_desc} must contain a root filing folder'
        assert 'default' in self.yaml_config, f'{file_desc} must contain a default folder'
        assert 'folders' in self.yaml_config, f'{file_desc} must contain a folders section'

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

        self.folders_to_keywords = self.yaml_config['folders']
        logger.debug(f'keywords file: {self.folders_to_keywords}')
        self.keywords_to_folders = self.reverse_keyword_dict(self.folders_to_keywords)

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

    def iter_page_text(self):
        num_pages = self.reader.getNumPages()
        logging.debug(f'Found {num_pages} pages to scan in {self.pdf_filename}')
        for page_num in range(num_pages):
            text = self.reader.getPage(page_num).extractText()
            text = text.encode('ascii', 'ignore')
            text = text.decode('utf-8')
            text = text.replace('\n', ' ')
            yield text
    
    def reverse_keyword_dict(self, folder_dict):
        keywords_to_folders = {}

        for folder, keyword_list in folder_dict.items():
            for keyword in keyword_list: 
                assert keyword not in keywords_to_folders
                keywords_to_folders[keyword] = folder
        return keywords_to_folders

    def find_matching_folder(self):
        # Iterate through each page and search for each
        keywords = list(self.keywords_to_folders.keys())

        default_folder = self.root_path / Path(self.yaml_config['default'])
        folder = None
        for page in self.iter_page_text():
            for keyword in keywords:
                if keyword in page:
                    folder = self.keywords_to_folders[keyword]
                    logger.debug(f'Found matching keyword: {keyword} -> folder:{folder}') 
                    return self.root_path / Path(folder)
        # No match for folder so we need to set it to the default
        return default_folder         


        
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
            filer = KeywordFiler(yaml_filename, item)
            folder = filer.find_matching_folder()
            logger.debug(f'Filing to folder {folder}')
            # Don't overwrite anything.  Just increment a suffix on the filename
            basename = self._get_filename_base(item)
            ext      = self._get_filename_ext(item)

            tgt_path = folder / Path(f'{basename}{ext}')
            i = 0
            while tgt_path.exists():
                tgt_path = folder / Path(f'{basename}.{i}{ext}')
                i += 1
            shutil.copy2(item, tgt_path)

            # Now, file the original if needed
            if filer.originals_path:
                shutil.copy2(self.original_pdf_filename, filer.originals_path)

        return item_list
    