import logging, os, platform, yaml, math
from html import escape
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
    Create the overlay PDF with OCR'ed text.
"""
class RotatedPara(Paragraph):
    """ Subclass of ReportLab's Paragraph class:
        Used for rotating text, since the low-level rotate method in textobject's don't seem to 
        do anything
    """

    def __init__ (self, text, style, angle, width, height, visible):
        Paragraph.__init__(self, text, style)
        self.my_width = width
        self.my_height = height
        self.visible = visible

        if angle == 90:
            self.angle = 270
        elif angle == 270:
            self.angle = 90
        else:
            self.angle = angle

    def draw(self):
        # Don't forget the angles have been transposed from CW (pypdf2) to CCW (reportlab) here in the __init__ method!
        if self.angle == 0:
            tx, ty = 0, self.my_height/2.0
        elif self.angle == 180:
            tx, ty = self.width, -self.my_height
        elif self.angle == 270:
            tx, ty = self.my_width, 0
        elif self.angle == 90:
            tx, ty = -self.my_width/2.0, -self.width
        else:
            tx, ty = 0, 0

        self.canv.saveState()
        self.canv.translate(tx, ty)
        self.canv.rotate(self.angle)
        Paragraph.draw(self)
        self.canv.restoreState()

    def beginText(self, x, y):
        t = self.canv.beginText(x,y)
        if self.visible:
            t.setTextRenderMode(0)  
        else:
            t.setTextRenderMode(3)  # Set to zero if you want the text to appear
        return t


class Plugin(Cmd):

    name = 'pdfoverlay'
    desc = 'Create pdf overlay using text locations'
    stage = 'create_overlay'
    inputs_from = ['text_process', 'analyze', 'orient']
    
    options = ["--pdfoverlay-visible           whether the OCR'ed text is overlayed visibily [default: False]"]

    def _find_executable(self):
        return

    async def run(self, item_list, analysis_item_list, orient_item_list):
        logger.info(f'About to generate PDF overlay')
        self.is_visible = self.config['visible']
        logger.info(f'Overlaying with visible text: {self.is_visible}')

        # Read in the page resolutions
        with analysis_item_list as items:
            assert len(items) == 1
            page_res_and_dims = await self.read_yaml_from_file(items[0])

        rotation_angles = []
        with orient_item_list as items:
            #assert len(items) == 1
            for item in items:
                rotation_angles.append(await self.read_yaml_from_file(item))

        assert len(item_list) == len(page_res_and_dims)

        with item_list as items:
            for i, loc_filename in enumerate(items):
                next_item = self._change_ext(loc_filename, 'ov.pdf')
                await self.add_to_queue(next_item, self.create_pdf_with_text, loc_filename, next_item, page_res_and_dims[i+1], rotation_angles[i])
                        #await self.create_pdf_with_text(text_locations, next_item, page_res_and_dims[i+1], rotation_angles[i])
            return await self.run_queue()
                
    async def create_pdf_with_text(self, loc_filename, pdf_filename, page_res_and_dims, rotation_angle):

        with open(loc_filename) as loc_file:
            text_locations = yaml.load(loc_file)

        with open(pdf_filename, 'wb') as f:

            logger.debug(f'Creating overlay pdf {pdf_filename}')
            pdf = Canvas(f, pageCompression=1)
            pdf.setCreator('lexic')
            pdf.setTitle(os.path.basename(pdf_filename))
            pdf.setPageCompression(1)

            #width, height, dpi_jpg = self._get_img_dims(img_basename)
            xdpi, ydpi, w, h = page_res_and_dims
            width = w * 72.0 / xdpi
            height = h * 72.0 / ydpi
            logger.debug("Prerotation: Page width=%f, height=%f" % (width, height))

            pdf.setPageSize((width,height))
            logger.debug("Page width=%f, height=%f" % (width, height))

            logger.debug("Adding text to page %s" % pdf_filename)
            #self.add_text_layer(text_locations, pdf, xdpi, ydpi, height, rotation_angle)

            # Run this cpu-intensive section in a thread so we don't block curio
            await curio.run_in_thread(self.add_text_layer, text_locations, pdf, xdpi, ydpi, height, rotation_angle)
            pdf.showPage()
            pdf.save()

    def add_text_layer(self, text_locations, pdf, xdpi, ydpi, page_height, rotation_angle):

        assert rotation_angle in [0,90,180,270], f'Rotation angle {rotation_angle} is not supported (only 0, 90, 180, 270 work)'

        prev_font_size = -10
        font_size_change_threshold = 5 

        #for loc, text in text_locations.items():
        logger.debug(f'Adding text_layer: xdpi: {xdpi} ydpi: {ydpi} page_height: {page_height}')
        # Get stylesheet to set font properties
        style = getSampleStyleSheet()
        normal = style['BodyText']
        normal.alignment = TA_LEFT
        normal.leading = 0
        normal.fontName = 'Helvetica'

        dpi_factor = 72.0*72.0/xdpi/ydpi

        for loc, text in sorted(text_locations.items(), key=lambda kv: kv[0]):
            block, par, line, word, x, y, w, h = loc
            logger.debug(f'Text "{text}" at ({x}, {y}) : w {w} h {h}')

            length = len(text)
            # Hack to figure out what approximate font size to use for overlay text
            area = w * h * dpi_factor
            new_font_size = math.sqrt(area/length*2.5)
            if new_font_size < 1: 
                new_font_size = 1
            normal.fontSize = new_font_size

            assert normal.fontSize >= 1

            # Set up paragraph with text
            text_angle = rotation_angle
            para = RotatedPara(escape(text), normal, text_angle, w*72.0/xdpi, h*72.0/ydpi, self.is_visible)
            para.wrapOn(pdf, para.minWidth(), 100)

            px = int(x*72.0/xdpi)
            py = int(page_height - ((y)*72.0/ydpi))
            para.drawOn(pdf, px, py)
