# Copyright 2019 Virantha N. Ekanayake  All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
How interesting!
-f for flow

Usage:
    lexic.py [options] PDFFILE default
    lexic.py [options] PDFFILE (%s)...
    lexic.py [options] PDFFILE filters (%s)... default
    lexic.py [options] PDFFILE filters (%s)... (%s)...
    lexic.py -h

Arguments:
    PDFFILE     PDF file to OCR
    default     Run default steps in the flow (%s)

Options:
    -h --help        show this message
    -v --verbose     show more information
    -d --debug       show even more information
    --conf=FILE      load options from file
    --threads=<THREADS>       number of parallel threads [default: max]

"""

"""
  Want something like

  lexic -f default
  lexic -f 
"""
from docopt import docopt
import yaml
import sys, os, logging, shutil
from collections import ChainMap
from schema import Schema, And, Optional, Or, Use, SchemaError
from pathlib import Path
import warnings

from curio import run, subprocess
import networkx as nx
import matplotlib.pyplot as plt
import psutil

from .version import __version__
from .utils import ordered_load, merge_args
from .command import Cmd
#from .imaging import ImageMagick
#from .tesseract import Tesseract, TsvParse
#from .pdf import PdfOverlay, PdfMerge
from .item import ItemList
#from .command import Setup


logger = logging.getLogger(__name__)


"""
   
Create a subdirectory called .convert
    Within it, another subdirectory of name file.pdf

Flow options:
    image, preprocess, ocr, pdf

Each flow step needs to be restartable

"""

class Lexic:
    """
        The main clas.  Performs the following functions:

    """

    def __init__ (self):
        """ 
        """
        self.args = None
        self.required_flow_steps = ['setup', 'analyze', 'image', 'orient', 'ocr', 'text_process', 'create_overlay', 'merge_overlay', 'clean']
        self.flow_actions = ['skip']
        warnings.simplefilter('ignore')   # get rid of stupid matplotlib warnings for now




    def get_options(self, argv):
        """
            Parse the command-line options and set the following object properties:

            :param argv: usually just sys.argv[1:]
            :returns: Nothing

            :ivar debug: Enable logging debug statements
            :ivar verbose: Enable verbose logging
            :ivar config: Dict of the config file

        """
        padding = max([len(x) for x in self.flow.keys()]) # Find max length of flow step names for padding with white space
        action_specifier_list = []
        docstring = __doc__ % ('|'.join(self.required_flow_steps),
                               '|'.join(self.filters),
                               '|'.join(self.filters),
                               '|'.join(self.required_flow_steps),
                               '|'.join(self.required_flow_steps)) # The desc in default
                              #'\n'.join(['    '+k+' '*(padding+4-len(k))+v for k,v  in self.flow.items()]))
        
        args = docopt(docstring, version=__version__)
        if args['--debug']:
            logging.basicConfig(level=logging.DEBUG, format='%(message)s')
        elif args['--verbose']:
            logging.basicConfig(level=logging.INFO, format='%(message)s')   

        # Load in default conf values from file if specified
        if args['--conf']:
            with open(args['--conf']) as f:
                conf_args = yaml.load(f)
        else:
            conf_args = {}
        args = merge_args(conf_args, args)
        #args = ChainMap(args, conf_args)
        logging.debug(args)

        threads = args.get('--threads', 1)
        if threads == 'max':
            Cmd.N_THREADS = psutil.cpu_count()
        else:
            Cmd.N_THREADS = int(threads)
        logger.info(f'Using {Cmd.N_THREADS} parallel threads')

        if args['default'] == 0:
            # TODO we don't really care about self.flow anymore, right?
            for f in list(self.flow):
                if args[f] == 0: del self.flow[f]
            logging.info("Doing flow steps: %s" % (','.join(self.flow.keys())))
        else:
            for f in self.required_flow_steps:
                args[f] = 1
            logging.info("Doing flow steps: %s" % (','.join(self.flow.keys())))

        if True or args['filters']:
            # if any filters have been specified
            for filter_name in list(self.filters.keys()):
                if args[filter_name] == 0: 
                    del self.filters[filter_name]
                del args[filter_name]
            logging.info("Doing filter steps: %s" % (','.join(self.filters.keys())))

            # we also need to remove this from the config dict, because
            # filters are referred to by name, so any filter-specific options 
            # will be stored under the filter name as a dict in the next parsing section

        # Now, go through all options with  hyphen and split into subdirs
        new_args = {}
        for arg, val in args.items():
            if arg.startswith('--'):
                if '-' in arg[2:]:
                    flowstep, option = arg[2:].split('-')
                    assert '-' not in option   # Can't have an option with more than one hypen in the name!
                    flowstep_dir = new_args.setdefault(flowstep, {})
                    flowstep_dir[option] = val
                else:
                    new_args[arg] = val
            else:
                new_args[arg] = val   # Just copy non-hypened options over

        self.args = new_args # Just save this for posterity
        logging.debug(self.args)


    def go(self, argv):
        """ 
            The main entry point into Lexic

            #. Do something
            #. Do something else
        """
        # Preliminary option parse to get the --verbose and --debug flags parsed
        # for the load_plugins method.  We will reparse args again in the get_options to get
        # the full set of arguments
        if '--verbose' in argv or '-v' in argv:
            logging.basicConfig(level=logging.INFO, format='%(message)s')   
        if '--debug' in argv or '-d' in argv:
            logging.basicConfig(level=logging.DEBUG, format='%(message)s')

        self.load_plugins()  # Plugins need to be loaded to append plugin specific options
        self.get_options(argv)
        run(self.system)

    def load_plugins(self):
        import importlib
        plugin_dir = Path(__file__).parent / 'plugins'
        logger.debug(f'Looking for plugins in {plugin_dir}')
        self.flow = {}
        self.filters = {}
        for plugin_file in plugin_dir.iterdir():
            if plugin_file.suffix == '.py':
                # Let's import this!
                logger.debug(f'Found plugin {plugin_file.stem}')
                pkg = importlib.import_module(f'.plugins.{plugin_file.stem}', 'lexic')
                plugin = pkg.Plugin
                # Gets imported as lexic.plugins.plugin_name
                # Now we need to insert the doc strings
                new_options = plugin.options
                global __doc__
                __doc__ = __doc__ + '\n'.join([f'    {opt}' for opt in new_options])
                if len(new_options) != 0:
                    __doc__ += '\n'
                Cmd.register_plugin(plugin)
                
                if plugin.stage != 'filter': 
                    self.flow[plugin.stage] = plugin.desc
                else:
                    self.filters[plugin.name] = plugin.desc
                


    async def system(self):

        """ First, construct the graph of all the required steps

            The required flow steps are:
                - setup
                - analyze
                - image
                - orient
                - ocr
                - text_process
                - create_overlay
                - merge_overlay
                - clean
        """
        required_flow_steps = self.required_flow_steps
        filters = self.filters

        # automatically construct flow 
        #   error out if more than one choice at each step
        logger.debug(f'flow steps available from plugiins')
        logger.debug(Cmd.plugin_list)
        G = nx.DiGraph()
        prev_step = None
        for step in required_flow_steps:
            logger.debug(f'Setting up flow step {step}')
            if step not in Cmd.plugin_list:
                logger.debug(f'  error: There is no plugin for {step} step!')
                sys.exit(-1)
            plugin_class = list(Cmd.plugin_list[step].values())[0]  #TODO: needs to be fixed for cases of multiiple classes of stages
            skip = (self.args[plugin_class.stage]==0)
            plugin = plugin_class(self.args.get(plugin_class.name, {}), skip=skip)
            G.add_node(plugin)
            if prev_step: 
                G.add_edge(prev_step, plugin)
            prev_step = plugin
            logger.debug(f'  done')
                
        # Now, add filters that are specified into the graph
        for i, step in enumerate(reversed(list(filters.keys()))):
            logger.debug(f'Adding {step} to flow')
            plugin_class = Cmd.plugin_list["filter"][step]
            logger.debug(f'PLUGIN CLASS {plugin}')
            plugin = plugin_class(self.args.get(plugin_class.name, {}))
            G.add_node(plugin)
            # Set the original pdf file pointer (really only needed in the filing step)
            plugin.original_pdf_filename = self.args['PDFFILE']
            if len(plugin.filter_on_output) > 0:
                logger.debug(f'Going to add {step} after a stage')
                for stage in plugin.filter_on_output:
                    logger.debug(f'Checking stage {stage}')
                    node = self._find_stage(G, stage)
                    if node:
                        # Add new plugin node after this node
                        logger.debug(f'Adding {step} after {stage}')
                        self.insert_node_after(G, node, plugin, i)
                        break   # not sure how to handle more than one possible place for this filter
                else:
                    print("Could not find a step to insert into")
                    sys.exit(-1)

            else:
                print("ERROR: could not find a place for the filter")
                sys.exit(-1)

        if self.args['--debug']:
            nx.draw(G, with_labels=True, labels={ n: f'{n.name}[{n.stage}]' for n in G.nodes()})
            plt.show()

        results = {}
        # Find starting setup step
        node = self._find_stage(G, 'setup')
        logger.info(f'Processing setup step')
        results[node.stage] = await node.run(self.args['PDFFILE'])

        for next_nodes in nx.dfs_successors(G, node).values():
            for next_node in next_nodes:
                logger.info(f'Processing step {next_node.name}[{next_node.stage}], with inputs from {next_node.inputs_from}')
                results[next_node.stage] = await next_node.run(*[results[r] for r in next_node.inputs_from])

        print(f'Successfully generated OCR file: {results[next_node.stage]}')
        return

    def _find_stage(self, G, stage):
        for  n in G.nodes():
            if n.stage == stage:
                return n
        return None

    def insert_node_after(self, G, node, new_node, rename_index):
        G.add_node(new_node)
        # For every successor of stage, make the new_stage point to it
        next_nodes = list(G.successors(node))
        for next_node in next_nodes:
            logger.debug(f'Removing edge from {node.name} to {next_node.name}')
            G.remove_edge(node, next_node)
            logger.debug(f'Adding edge from {new_node.name} to {next_node.name}')
            G.add_edge(new_node, next_node)
        logger.debug(f'Adding edge from {node.name} to {new_node.name}')
        G.add_edge(node, new_node)

        # Now, rename the .stage to be the original node's stage
        new_node.stage = node.stage
        node.stage = f'_{node.stage}_{rename_index}'

        # Now, update where new_node gets its inputs from to the renamed previous node
        for i, input_from in enumerate(new_node.inputs_from):
            if input_from == new_node.stage:
                new_node.inputs_from[i] = node.stage


    async def _system(self):
        """
            Pipeline steps must include the following:

            setup
            analyze   (pdfimages)
            image     (ghostscript)
            orient    (tesseract)
            ocr       (tesseract)
            text_process 
            create_overlay
            merge_overlay

            Each plugin can identify as either:
            1. replacing one of thise pipeline stages
            2. filter before a stage
            3. filter after a stage

            Build up a graph from networkx and then traverse it

            Each stage and filter must be skippable
                - In order to be skippable, that means it must be able to return the
                  output it would normally have produced without actually doing the work
        """
        setup = Setup(self.args.get('setup', {}))
        #pdfrotations = PdfRotations(self.args.get('pdfrotations', {}))
        orientation = PdfOrientations(self.args.get('orientation', {}))
        pdfimages = PdfImages(self.args.get('pdfimages', {}))
        gs = Ghostscript(self.args.get('gs', {}))
        pre = ImageMagick(self.args.get('imagemagick', {}))
        ts = Tesseract(self.args.get('tesseract', {}))
        tsv = TsvParse(self.args.get('tsv', {}))
        pdfoverlay = PdfOverlay(self.args.get('pdfoverlay', {}))
        pdfmerge = PdfMerge(self.args.get('pdfmerge', {}))


        gs_in = setup.initialize(self.args['PDFFILE'])

        logger.info('About to pdfimage')
        resolutions = await pdfimages.get_res(gs_in)
        logging.debug(resolutions)

        logger.info('About to ghostscript')
        gs_out = await gs.image(gs_in, resolutions)

        logger.debug('About to preprocess image files')
        #Ipre_out = await pre.preprocess(gs_out)

        logger.info('About to get rotation angles')
        rotation_angles = await orientation.get_rotation_angles(gs_out)
        logger.debug(f'Rotation angles: {rotation_angles}')

        logger.info('About to tesseract')
        ts_out = await ts.process(gs_out)

        logger.info('About to parse tsv')
        tsv_out = await tsv.parse(ts_out)
        
        logger.info('About to create overlay files with ext')
        pdfoverlay_out = await pdfoverlay.create_overlay(tsv_out, resolutions, rotation_angles)

        logger.info('About to merge pdfs')
        pdfmerge_out = await pdfmerge.merge_pdfs(pdfoverlay_out, self.args['PDFFILE'])

        print(f'Successfully generated OCR file: {pdfmerge_out}')



def main():
    script = Lexic()
    script.go(sys.argv[1:])

if __name__ == '__main__':
    main()


