import logging, os, sys, shutil, hashlib, time
import functools

import yaml
from pathlib import Path
from PyPDF2 import PdfFileReader
from dateparser.search import search_dates
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

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
        self.root_path = self.yaml_config['root']

        self.folders_to_keywords = self.yaml_config['folders']
        logger.debug(f'keywords file: {self.folders_to_keywords}')
        self.keywords_to_folders = self.reverse_keyword_dict(self.folders_to_keywords)

    def iter_page_text(self):
        num_pages = self.reader.getNumPages()
        logger.debug(f'Found {num_pages} pages to scan in {self.pdf_filename}')
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

        default_folder = self.yaml_config['default']
        folder = None
        for page in self.iter_page_text():
            for keyword in keywords:
                if keyword in page.lower():
                    folder = self.keywords_to_folders[keyword]
                    logger.debug(f'Found matching keyword: {keyword} -> folder:{folder}') 
                    return folder
        # No match for folder so we need to set it to the default
        return default_folder         

    def find_closest_date(self):
        # Go through every page and search for dates using dateparser
        # At the end, select the date closest to (and older) than the current date
        # If no dates found (with full day month year), just use today's date
        dates = []
        for page_num, page in enumerate(self.iter_page_text()):
            page_dates = search_dates(page)
            logger.debug(f'Found dates on page {page_num}')
            logger.debug(page_dates)
            for text, dt in page_dates:
                if dt.year == 1900:
                    pass
                else:
                    dates.append(pytz.utc.localize(dt))
                    #dates.append(dt.replace(tzinfo=None)))
        # Sort date list
        dates = sorted(dates)
        # Now, iterate through list until we're at or above today's date
        now = pytz.utc.localize(datetime.now())
        if len(dates) == 0:
            newest_date = now
        else:
            newest_date = dates[0]
            for dt in dates:
                if dt <= now:
                    newest_date = dt
                else:
                    break
        return newest_date