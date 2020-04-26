import logging, os, platform

from curio import subprocess, spawn, run_in_process

from ..command import Cmd
from ..item import ItemList

logger = logging.getLogger(__name__)

"""
    Use to get the rotation angle of each page, returnd as a list
"""
class Plugin(Cmd):

    name = 'orientation'
    desc = 'Find page orientation using tesseract'
    stage = 'orient'
    inputs_from = ['image']
    
    options = ["--orientation-program=PROGRAM  path to Orientation detect program [default: tesseract]"]

    
    async def run(self, item_list):
        with item_list as items:
            for i, item in enumerate(items):
                angle_filename = self._change_ext(item, 'ang')
                await self.add_to_queue(angle_filename, self.call_tesseract_for_osd, i, item, angle_filename)
                    
            return await self.run_queue()
                
    async def call_tesseract_for_osd(self, i, item, angle_filename):
        """ Runs tesseract with just the orientation and script detection

            Returns the angle parsed from the output file if available, otherwise defaults to zero

            Tessearct OSD output file looks like this:
                Page number: 0
                Orientation in degrees: 0
                Rotate: 0
                Orientation confidence: 14.84
                Script: Latin
                Script confidence: 4.67
        """
        basename = self._get_filename_base(item)
        cmd = f'{self.executable} {item} {basename} -l osd --psm 0'
        logger.debug(cmd)
        try:
            osd_file = self._change_ext(item, 'osd')
            await self._run_command(cmd)
            with open(osd_file) as f:
                lines = f.readlines()
            angle = -1
            for line in lines:
                if line.startswith('Orientation in degrees'):
                    _, angle = line.split(':')
                    angle = int(angle.strip())
            if angle == -1:
                msg = f'page {i+1} - cannot parse angle from OSD detection, using 0 degrees as rotation angle'
                angle= 0
            else:
                msg = f'page {i+1} - parsed orientation as {angle} degrees'
            logger.debug(msg)
            await self.add_message(msg)
        except (subprocess.CalledProcessError, IOError):
            msg = f"page {i+1} - Tesseract OSD could not be executed; defaulting to 0 degrees"
            logger.debug(msg)
            await self.add_message(msg)
            angle=0
        finally:
            # Make sure we clean up the intermediate output from tesseract 
            # even if there was an error
            if os.path.exists(osd_file):
                os.remove(osd_file)

        await self.write_yaml_to_file(angle_filename, angle)