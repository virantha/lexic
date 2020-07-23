import logging, os, platform, yaml, math
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus.paragraph import Paragraph
from PyPDF2 import PdfFileMerger, PdfFileReader, PdfFileWriter, utils
import curio
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

    async def run_new(self, item_list, orig_pdf_filename_list):
        # First, create a pdf of merged text pages from items
        logger.info("Creating a single PDF file containing all pages of just the text")
        next_items = ItemList()

        with orig_pdf_filename_list as items:
            assert len(items) == 1
            orig_pdf_filename = items[0]


        output_pdf_filename = self._change_ext(orig_pdf_filename, 'ocr.pdf')
        if not self.skip:
            orig_page_filenames = self._split_into_pages(orig_pdf_filename)
            with item_list as items:
                for i, (text_pdf_page_filename, orig_pdf_page_filename) in enumerate(zip(items, orig_page_filenames)):
                    merged_page_filename = self._change_ext(text_pdf_page_filename, 'merged.pdf')
                    await self.add_to_queue(merged_page_filename, self.merge_overlay_page_wrapper, i, text_pdf_page_filename, orig_pdf_page_filename, merged_page_filename)

                merged_filenames = await self.run_queue()
            await self._merge_text_pdfs(merged_filenames, output_pdf_filename)
            for fn in merged_filenames+orig_page_filenames:
                os.remove(fn)
        next_items.append(output_pdf_filename)
        return next_items

    def _split_into_pages(self, pdf_filename):
        """Take a pdf and make separate PDF files for each page
        """
        pdf = PdfFileReader(pdf_filename)
        output_filenames = []
        for page_num in range(pdf.getNumPages()):
            pdf_writer = PdfFileWriter()
            pdf_writer.addPage(pdf.getPage(page_num))

            output_filename = self._change_ext(pdf_filename, f'_{page_num}.orig.pdf')
            output_filenames.append(output_filename)
            with open(output_filename, 'wb') as f:
                pdf_writer.write(f)
        return output_filenames
            

    async def merge_overlay_page_wrapper(self, page_num, text_pdf_page_filename, orig_pdf_filename, merged_page_filename):
        await curio.run_in_thread(self.merge_overlay_page, page_num, text_pdf_page_filename, orig_pdf_filename, merged_page_filename)

    def merge_overlay_page(self, page_num, text_pdf_page_filename, orig_pdf_page_filename, merged_page_filename):

        with open(text_pdf_page_filename, 'rb') as text_pdf_page_file, \
             open(orig_pdf_page_filename, 'rb') as orig_pdf_page_file:
            text_page = self._get_first_page(text_pdf_page_file)
            orig_page = self._get_first_page(orig_pdf_page_file)
            # merge the two files
            self._write_merged_single_page(orig_page, text_page, merged_page_filename)
            #await curio.run_in_thread(self._write_merged_single_page,orig_page, text_page, merged_page_filename)

    def _get_first_page(self, pdf_file):
        all_pages = PdfFileReader(pdf_file)
        first_page = all_pages.getPage(0)
        return first_page

    def _write_merged_single_page(self, orig_page, text_page, merged_filename):
        # Call _get_merged_single_page and write it to a file
        writer = PdfFileWriter()
        writer.addPage(self._get_merged_single_page(orig_page, text_page))
        with open(merged_filename, 'wb') as f:
            writer.write(f)

    async def _merge_text_pdfs(self, items, output_filename):
        merger = PdfFileMerger()
        for item in items:
            logger.debug(f'Concatenating {item}')
            merger.append(PdfFileReader(item))
        logger.debug(f'Writing merged pdf {output_filename}')
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
