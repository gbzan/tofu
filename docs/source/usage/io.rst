Input/Output
============


Image Reading
-------------

Tofu uses UFO's `Reader
<https://ufo-filters.readthedocs.io/en/master/generators.html#read-read>`_ which
can handle multiple file types, including single tif files and multi-page tif
files. If you specify a file, only that file will be read, if you specify a
directory, all files in the directory will be read. If you specify a pattern,
all files matching that pattern will be read. Available for all of the commands
mentioned in this page:

- ``--y``: Vertical coordinate from where to start reading the input image (default: 0);
- ``--height``: Number of rows which will be read (default: None);
- ``--bitdepth``: Bit depth of raw files (default: 32);
- ``--y-step``: Read every "step" row from the input (default: 1);
- ``--start``: Offset to the first read file (default: 0);
- ``--number``: Number of files to read (default: None);
- ``--step``: Read every "step" file (default: 1).


Image Writing
-------------

Tofu writes tif files by UFO's `Writer
<https://ufo-filters.readthedocs.io/en/master/sinks.html?highlight=write#write-write>`_
and they can be either single- or multi-page, which is controlled by the
``--output-bytes-per-file`` argument. If you set it to ``0`` or any number
smaller than the size of two images in bytes, the output will be singe-page. If
you specify a larger value, there will be multiple images in one tif file. On
the top of that, if the file size is larger than 4 GB the tif file will be in
the bigtiff format. In case you specify a file name to be something like
``output.tif``, you need to make sure you specify ``--output-bytes-per-file`` to
be large enough to facilitate all images which will be written. Alternatively,
you can specify the output in the format e.g. ``output-%04d.tif``, which will
create files ``output-0000.tif``, ``output-0001.tif`` and so on. A new file will
be created every time the amount of bytes written in the current file would
exceed the value specified by ``--output-bytes-per-file``.
