import yaml, sys
from collections import OrderedDict

def ordered_load(stream, Loader=yaml.Loader, object_pairs_hook=OrderedDict):
    """ Helper function to allow yaml load routine to use an OrderedDict instead of regular dict.
        This helps keeps things sane when ordering the runs and printing out routines
    """
    class OrderedLoader(Loader):
        pass
    def construct_mapping(loader, node):
        loader.flatten_mapping(node)
        return object_pairs_hook(loader.construct_pairs(node))
    OrderedLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        construct_mapping)
    return yaml.load(stream, OrderedLoader)


def merge_args(conf_args, orig_args):
    """ Return new dict with args, and then conf_args merged in.
        Make sure that any keys in conf_args are also present in args
    """
    args = {}
    # Need to convert things like:
    # plugin_name:
    #     option1: "blah"
    #     option2: "blah"
    # into something like:
    # --plugin_name-option1: "blah"
    # --plugin_name-option2: "blah"

    for plugin_name in list(conf_args.keys()):
        if plugin_name.startswith('-'):
            # Ignore any option that starts with a dash
            # We'll assume these are top-level options for now
            pass
        else:
            plugin_options = list(conf_args[plugin_name].keys())  # This should be a dict
            for option in plugin_options:  #
                # Only use a conf file arg if it hasn't been specified at the command line
                # (i.e. command line args supersede any in the conf file)
                expanded_option_name = f'--{plugin_name}-{option}'
                if expanded_option_name in orig_args or option == 'yaml':
                    conf_args[expanded_option_name] = conf_args[plugin_name][option]
                else:

                    print(f"ERROR: Configuration file has unknown option {expanded_option_name}")
                    sys.exit(-1)
            # Remove this entry so we don't pollute the main config that uses plugin_name=0/1 to
            # determine if a filter is specified
            del conf_args[plugin_name]
    args.update(orig_args)
    args.update(conf_args)
    return args
