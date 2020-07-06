import logging, os, sys, shutil, hashlib, time
import functools

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
from ..keyword_filer import KeywordFiler

logger = logging.getLogger(__name__)

"""
    File pdfs into a directory structure
"""

class EvernoteFiler(KeywordFiler):
    # We can use the generic keyword filer as is
    pass


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
    
    #options = ['--evernote-keywords=FILE     Keyword files']
    options = ['--evernote-root=NAME      Root notebook stack', 
               '--evernote-default=NAME   Default notebook name', 
               '--evernote-token          Evernote developer token',
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

        #yaml_filename = self.config['keywords']

        # Read in the keyword files
        with item_list as items:
            item = items[0]
            filer = EvernoteFiler(self.config, item)
            folder = filer.find_matching_folder()
            logger.debug(f'Filing to Evernote folder {folder}')

            dt = filer.find_closest_date()
            logger.debug(f'Closest date for document is {dt}')

            # Evernote
            #    Create note
            #    Push it to the note store
            En = Evernote(self.config['token'])
            En.connect_to_evernote()
            En.default_folder = folder
            En.target_folder= filer.root_path
            En.move_to_matching_folder(item, folder, dt)
            await self.add_message(f'filed to {folder} with date {dt.year}/{dt.month}/{dt.day}')
            await self.add_message('keywords - ' + ', '.join(filer.find_noun_phrases()[:10]))

        return item_list
    