"""Flat field correction."""
import sys
import logging
from gi.repository import Ufo
from tofu.util import (get_filenames, set_node_props, make_subargs,
                       determine_shape, setup_read_task)
from tofu.tasks import get_task, get_writer


LOG = logging.getLogger(__name__)


def create_flat_correct_pipeline(args, graph, processing_node=None):
    """
    Create flat field correction pipeline. All the settings are provided in
    *args*. *graph* is used for making the connections. Returns the flat field
    correction task which can be used for further pipelining.
    """
    pm = Ufo.PluginManager()

    if args.projections is None or args.flats is None or args.darks is None:
        raise RuntimeError("You must specify --projections, --flats and --darks.")

    reader = get_task(pm, 'read')
    dark_reader = get_task(pm, 'read')
    flat_before_reader = get_task(pm, 'read')

    ffc = get_task(pm, 'flat-field-correct', processing_node=processing_node,
                   dark_scale=args.dark_scale,
                   absorption_correct=args.absorptivity,
                   fix_nan_and_inf=args.fix_nan_and_inf)
    mode = args.reduction_mode.lower()
    roi_args = make_subargs(args, ['y', 'height', 'y_step'])
    set_node_props(reader, args)
    set_node_props(dark_reader, roi_args)
    set_node_props(flat_before_reader, roi_args)

    for r, path in ((reader, args.projections), (dark_reader, args.darks), (flat_before_reader, args.flats)):
        setup_read_task(r, path, args)

    LOG.debug("Doing flat field correction using reduction mode `{}'".format(mode))

    if args.flats2:
        flat_after_reader = get_task(pm, 'read')
        setup_read_task(flat_after_reader, args.flats2, args)
        set_node_props(flat_after_reader, roi_args)
        num_files = len(get_filenames(args.projections))
        can_read = len(range(args.start, num_files, args.step))
        number = args.number if args.number else num_files
        num_read = min(can_read, number)
        flat_interpolate = get_task(pm, 'interpolate', processing_node=processing_node, number=num_read)

    if args.resize:
        LOG.debug("Resize input data by factor of {}".format(args.resize))
        proj_bin = get_task(pm, 'bin', processing_node=processing_node, size=args.resize)
        dark_bin = get_task(pm, 'bin', processing_node=processing_node, size=args.resize)
        flat_bin = get_task(pm, 'bin', processing_node=processing_node, size=args.resize)
        graph.connect_nodes(reader, proj_bin)
        graph.connect_nodes(dark_reader, dark_bin)
        graph.connect_nodes(flat_before_reader, flat_bin)

        reader, dark_reader, flat_before_reader = proj_bin, dark_bin, flat_bin

        if args.flats2:
            flat_bin = get_task(pm, 'bin', processing_node=processing_node, size=args.resize)
            graph.connect_nodes(flat_after_reader, flat_bin)
            flat_after_reader = flat_bin

    if mode == 'median':
        dark_stack = get_task(pm, 'stack', processing_node=processing_node,
                              number=len(get_filenames(args.darks)))
        dark_reduced = get_task(pm, 'flatten', processing_node=processing_node, mode='median')
        flat_before_stack = get_task(pm, 'stack', processing_node=processing_node,
                                     number=len(get_filenames(args.flats)))
        flat_before_reduced = get_task(pm, 'flatten', processing_node=processing_node, mode='median')

        graph.connect_nodes(dark_reader, dark_stack)
        graph.connect_nodes(dark_stack, dark_reduced)
        graph.connect_nodes(flat_before_reader, flat_before_stack)
        graph.connect_nodes(flat_before_stack, flat_before_reduced)

        if args.flats2:
            flat_after_stack = get_task(pm, 'stack', processing_node=processing_node,
                                        number=len(get_filenames(args.flats2)))
            flat_after_reduced = get_task(pm, 'flatten', processing_node=processing_node,
                                          mode='median')
            graph.connect_nodes(flat_after_reader, flat_after_stack)
            graph.connect_nodes(flat_after_stack, flat_after_reduced)
    elif mode == 'average':
        dark_reduced = get_task(pm, 'average', processing_node=processing_node)
        flat_before_reduced = get_task(pm, 'average', processing_node=processing_node)
        graph.connect_nodes(dark_reader, dark_reduced)
        graph.connect_nodes(flat_before_reader, flat_before_reduced)

        if args.flats2:
            flat_after_reduced = get_task(pm, 'average', processing_node=processing_node)
            graph.connect_nodes(flat_after_reader, flat_after_reduced)
    else:
        raise ValueError('Invalid reduction mode')

    graph.connect_nodes_full(reader, ffc, 0)
    graph.connect_nodes_full(dark_reduced, ffc, 1)

    if args.flats2:
        graph.connect_nodes_full(flat_before_reduced, flat_interpolate, 0)
        graph.connect_nodes_full(flat_after_reduced, flat_interpolate, 1)
        graph.connect_nodes_full(flat_interpolate, ffc, 2)
    else:
        graph.connect_nodes_full(flat_before_reduced, ffc, 2)

    return ffc


def run_flat_correct(args):
    graph = Ufo.TaskGraph()
    sched = Ufo.Scheduler()
    pm = Ufo.PluginManager()

    out_task = pm.get_task('write')
    out_task.props.filename = args.output
    flat_task = create_flat_correct_pipeline(args, graph)
    graph.connect_nodes(flat_task, out_task)
    sched.run(graph)


def create_sinogram_pipeline(args, graph):
    """Create sinogram generating pipeline based on arguments from *args*."""
    pm = Ufo.PluginManager()
    sinos = pm.get_task('transpose-projections')

    if args.number:
        region = (args.start, args.start + args.number, args.step)
        num_projections = len(range(*region))
    else:
        num_projections = len(get_filenames(args.projections))

    sinos.props.number = num_projections

    if args.darks and args.flats:
        start = create_flat_correct_pipeline(args, graph)
    else:
        start = get_task(pm, 'read')
        start.props.path = args.projections
        set_node_props(start, args)

    graph.connect_nodes(start, sinos)

    return sinos


def run_sinogram_generation(args):
    """Make the sinograms with arguments provided by *args*."""
    if not args.height:
        args.height = determine_shape(args, args.projections)[1] - args.y

    step = args.y_step * args.pass_size if args.pass_size else args.height
    starts = range(args.y, args.y + args.height, step) + [args.y + args.height]

    def generate_partial(append=False):
        pm = Ufo.PluginManager()
        graph = Ufo.TaskGraph()
        sched = Ufo.Scheduler()

        writer = get_task(pm, 'write')
        writer.props.filename = args.output
        writer.props.append = append

        sinos = create_sinogram_pipeline(args, graph)
        graph.connect_nodes(sinos, writer)
        sched.run(graph)

    for i in range(len(starts) - 1):
        args.y = starts[i]
        args.height = starts[i + 1] - starts[i]
        generate_partial(append=i != 0)
