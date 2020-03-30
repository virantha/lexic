import logging, os, platform, yaml, math
from cgi import escape
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus.paragraph import Paragraph
from PyPDF2 import PdfFileMerger, PdfFileReader, PdfFileWriter, utils
from curio import subprocess

from ..command import Cmd
from ..item import ItemList

logger = logging.getLogger(__name__)

"""
    Merge the text pdf with the original pages
"""

class Plugin(Cmd):

    name = 'pdf_merge'
    desc = 'Merge text overlays with original pdf to generate final pdf'
    stage = 'merge_overlay'
    inputs_from = ['create_overlay', 'setup']
    
    options = []

    def _find_executable(self):
        return

    async def run(self, item_list, orig_pdf_filename_list):
        # First, create a pdf of merged text pages from items
        logger.info("Creating a single PDF file containing all pages of just the text")
        next_items = ItemList()

        with orig_pdf_filename_list as items:
            assert len(items) == 1
            orig_pdf_filename = items[0]


        output_pdf_filename = self._change_ext(orig_pdf_filename, 'ocr.pdf')
        if not self.skip:
            with item_list as items:
                merged_filename = self._change_ext(orig_pdf_filename, 'text.pdf')

                await self._merge_text_pdfs(items, merged_filename)
                writer = PdfFileWriter()
                with open(orig_pdf_filename, 'rb') as orig_pdf, \
                    open(merged_filename, 'rb') as text_pdf:

                    print(len(items))
                    for orig_page, text_page in   \
                        self.iterate_with_progress(zip(self.iter_pdf_page(orig_pdf),
                            self.iter_pdf_page(text_pdf)), total=len(items)):

                        orig_pg = self._get_merged_single_page(orig_page, text_page)
                        writer.addPage(orig_pg)
                
                    with open(output_pdf_filename, 'wb') as f:
                        writer.write(f)
                # remove the intermediate .text.pdf file
                os.remove(merged_filename)

        next_items.append(output_pdf_filename)
        return next_items
            

    async def _merge_text_pdfs(self, items, output_filename):
        merger = PdfFileMerger()
        for item in items:
            logger.debug(f'Concatenating {item}')
            merger.append(PdfFileReader(item))
        merger.write(output_filename)
        merger.close()
        del merger

    def _get_merged_single_page(self, original_page, ocr_text_page):
        """
            Take two page objects, rotate the text page if necessary, and return the merged page
        """
        orig_rotation_angle = int(original_page.get('/Rotate', 0))

        if orig_rotation_angle != 0:
            logger.info("Original Rotation: %s" % orig_rotation_angle)
            logger.debug(f'OCR page dimensions:  Width {ocr_text_page.mediaBox.getWidth()}, Height {ocr_text_page.mediaBox.getHeight()}')
            logger.debug(f'Org page dimensions:  Width {original_page.mediaBox.getWidth()}, Height {original_page.mediaBox.getHeight()}')

            # Some nasty code to do the translations when rotating
            w = ocr_text_page.mediaBox.getWidth()/2
            h = ocr_text_page.mediaBox.getHeight()/2
            transforms = { 270: (w,w),
                           180: (w,h),
                           90:  (h,h),
                         }

            original_page.mergeRotatedTranslatedPage(ocr_text_page, 
                         orig_rotation_angle, 
                         transforms[orig_rotation_angle][0],
                         transforms[orig_rotation_angle][1],
                         True)  # Change this to True to expand page (useful for debugging off margin placements)

        else:
            original_page.mergePage(ocr_text_page)
        original_page.compressContentStreams()
        return original_page

    def iter_pdf_page(self, f):
        reader = PdfFileReader(f)
        for pgnum in range(reader.getNumPages()):
            pg = reader.getPage(pgnum)
            yield pg