import logging, os, sys, shutil, hashlib, time
import functools

import yaml
from pathlib import Path
from PyPDF2 import PdfFileReader
from dateparser.search import search_dates
from datetime import datetime

from evernote.api.client import EvernoteClient
import evernote.edam.type.ttypes as Types
import evernote.edam.userstore.constants as UserStoreConstants
from evernote.edam.error.ttypes import EDAMUserException
from evernote.edam.error.ttypes import EDAMSystemException
from evernote.edam.error.ttypes import EDAMNotFoundException
from evernote.edam.error.ttypes import EDAMErrorCode

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
                    dates.append(dt)
        # Sort date list
        dates = sorted(dates)
        # Now, iterate through list until we're at or above today's date
        now = datetime.now()
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




class en_handle(object):
    """ Generic exception handler for Evernote actions
    """
    def __init__(self, f):
        # f is the method being decorated, so save it so we can call it later!
        self.f = f
        functools.update_wrapper(self, f)

    def __get__(self, instance, owner):
        # Save a ptr to the object being decorated
        self.cls = owner
        self.obj = instance
        return self.__call__

    def __call__(self, *args, **kwargs):
        # The actual meat of the decorator
        retries = 3
        result = None
        for retry in range(retries):
            try:
                # Call the original method being decorated
                result = self.f.__call__(self.obj, *args, **kwargs)
                return result
            except EDAMUserException as e:
                if e.errorCode in [EDAMErrorCode.AUTH_EXPIRED, EDAMErrorCode.DATA_REQUIRED]:
                    logger.debug(f'Evernote authorization expired, retrying {retry} out of {retries}')
                    self.obj.connect_to_evernote()
                else:
                    logger.debug(f'Evernote error {EDAMErrorCode._VALUES_TO_NAMES[e.errorCode]}: {e.parameter}')
                    logger.debug(f'retrying {retry} of {retries}')
                time.sleep(3)
        # Retries failed, what to do here?  Just error out?
        print(f'ERROR connecting to Evernote')
        sys.exit(-1)

class Evernote:
    def __init__(self, dev_token):
        self.dev_token = dev_token
    
    def connect_to_evernote(self):
        logger.info('Authenticating to Evernote')
        logger.debug(f'Using dev token: {self.dev_token}')
        try:
            self.client = EvernoteClient(token=self.dev_token, sandbox=False)
            self.user_store = self.client.get_user_store()
            user = self.user_store.getUser()
        except EDAMUserException as e:
            err = e.errorCode
            print("Error attempting to authenticate to Evernote: %s - %s" % (EDAMErrorCode._VALUES_TO_NAMES[err], e.parameter))
        except EDAMSystemException as e:
            err = e.errorCode
            print("Error attempting to authenticate to Evernote: %s - %s" % (EDAMErrorCode._VALUES_TO_NAMES[err], e.message))
            sys.exit(-1)
        if user:
            print("Authenticated to evernote as user %s" % user.username)
        return True
    
    @en_handle
    def _get_notebooks(self):
        note_store = self.client.get_note_store()
        notebooks = note_store.listNotebooks()
        return {n.name:n for n in notebooks}

    @en_handle
    def _create_notebook(self, notebook):
        note_store = self.client.get_note_store()
        return note_store.createNotebook(notebook)

    def _update_notebook(self, notebook):
        note_store = self.client.get_note_store()
        note_store.updateNotebook(notebook)
        return

    @en_handle
    def _check_and_make_notebook(self, notebook_name):
        """
            Weird.
            :returns notebook: New or existing notebook object
            :rtype Types.Notebook:
        """
        # Get the noteStore
        notebooks = self._get_notebooks()
        if notebook_name in notebooks:
            notebook = notebooks[notebook_name]
            if notebook.stack != self.target_folder:
                notebook.stack = self.target_folder
                self._update_notebook(notebook)
            return notebook
        else:
            # Need to create a new notebook
            notebook = Types.Notebook()
            notebook.name = notebook_name
            notebook.stack = self.target_folder
            notebook = self._create_notebook(notebook)
            #notebook = note_store.createNotebook(notebook)
            return notebook

    @en_handle
    def _create_evernote_note(self, notebook, filename):
        # Create the new note
        note = Types.Note()
        note.title = os.path.basename(filename)
        note.notebookGuid = notebook.guid
        note.content = '<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE en-note SYSTEM "http://xml.evernote.com/pub/enml2.dtd">'
        note.content += '<en-note>Uploaded by Lexic <br/>'
       

        logger.debug("Loading PDF")
        md5 = hashlib.md5()
        with open(filename,'rb') as f: 
            pdf_bytes = f.read()

        logger.debug("Calculating md5 checksum of pdf")
        md5.update(pdf_bytes)
        md5hash = md5.hexdigest()

        logger.debug("Uploading note")
        
        # Create the Data type for evernote that goes into a resource
        pdf_data = Types.Data()
        pdf_data.bodyHash = md5hash
        pdf_data.size = len(pdf_bytes) 
        pdf_data.body = pdf_bytes

        # Add a link in the evernote boy for this content
        link = '<en-media type="application/pdf" hash="%s"/>' % md5hash
        logger.debug(link)
        note.content += link
        note.content += '</en-note>'
        
        resource_list = []
        pdf_resource = Types.Resource()
        pdf_resource.data = pdf_data
        pdf_resource.mime = "application/pdf"
        # TODO: Enable filename
        # Make a attributes for this resource
        pdf_resource.attributes = Types.ResourceAttributes()
        pdf_resource.attributes.fileName = os.path.basename(filename)
        resource_list.append(pdf_resource)

        note.resources = resource_list

        return note

        
    def move_to_matching_folder(self, filename, foldername, created_datetime):
        """
            Use the evernote API to create a new note:

            #. Make the notebook if it doesn't exist (:func:`_check_and_make_notebook`)
            #. Create the note (:func:`_create_evernote_note`)
            #. Upload note using API

        """
        assert self.default_folder != None

        if not foldername:
            logger.info("[DEFAULT] %s --> %s" % (filename, self.default_folder))
            foldername = self.default_folder
        else:   
            logger.info("[MATCH] %s --> %s" % (filename, foldername))

        # Check if the evernote notebook exists
        print ("Checking for notebook named %s" % foldername)
        notebook = self._check_and_make_notebook(foldername)
        print("Uploading %s to %s" % (filename, foldername))
        
        note = self._create_evernote_note(notebook, filename)
        logger.debug(f'Datetime is: {created_datetime}, timestamp is: {created_datetime.timestamp()}')
        note_timestamp = int(created_datetime.timestamp())* 1000 # evernote expects time in milliseconds
        note.created = note_timestamp
        #note.updated = note_timestamp

        # Store the note in evernote
        note_store = self.client.get_note_store()
        note = note_store.createNote(note)

        return "%s/%s" % (notebook.name, note.title)

class Plugin(Cmd):

    name = 'evernote'
    desc = 'File PDFs into evernote'
    stage = 'filter'
    filter_on_output = ['clean']
    inputs_from = ['clean','setup']
    
    options = ['--evernote-keywords=FILE     Keyword files']

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
            logger.debug(f'Filing to Evernote folder {folder}')

            dt = filer.find_closest_date()
            logger.debug(f'Closest date for document is {dt}')

            # Evernote
            #    Create note
            #    Push it to the note store
            En = Evernote(filer.yaml_config['EVERNOTE_TOKEN'])
            En.connect_to_evernote()
            En.default_folder = folder
            En.target_folder= filer.yaml_config['root']
            En.move_to_matching_folder(item, folder, dt)

        return item_list
    