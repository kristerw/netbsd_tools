#!/usr/bin/env python

# This script finds unused functions and global variables in the kernel by
# processing the output from running nm and objdump on the kernel and object
# files. The script is run in the kernel's build directory, e.g.
#   src/sys/arch/sun3/compile/GENERIC
# after the kernel has been built, and the script assumes the source code is
# available at
#   ../../../../..
# The path to the source code cant be explicitly provided by a sun-time option
#   find_unused_kern_syms.py -s /path/to/src
#
# Limitations:
#  * Symbols are reported as unused if they are used and have been inlined
#    at all uses.
#  * The mechanism for finding the source files is very ad-hoc, and does often
#    fail. The object file is reported instead of the source file in this case.
#  * The script is very slow. It may need more than a minute to process the
#    kernel on a slow disk, when many symbols are unused.
#  * The script does not understand STRONG_ALIAS etc., so it may incorrectly
#    report such symbols as unused.

import argparse
import collections
import os
import subprocess
import sys


def get_obj_file_names():
    """Return a list of all object files."""
    proc = subprocess.Popen(['find', '.', '-name', '*.o'],
                            stdout=subprocess.PIPE)
    file_names = [line[2:-1] for line in  proc.stdout]

    # Filter out libkern.o as it contain the same symbols as the other
    # object files in lib/kern.
    file_names = [file_name for file_name in file_names
                  if file_name != 'lib/kern/libkern.o']

    return file_names


def read_symbols(filenames):
    """Return a symbol/object file mapping for all global symbols."""
    symbols = {}
    for filename in filenames:
        proc = subprocess.Popen(['nm', filename], stdout=subprocess.PIPE)
        for line in proc.stdout:
            # The line from nm have two or three fields, e.g.
            #          U sunmon_abort
            # 000005c8 T zs_abort
            item = line.split()
            if len(item) == 3:
                item.pop(0)
            sym_type, sym_name = item
            if sym_type in "TDB":
                symbols[sym_name] = filename
    return symbols


def read_kernel_symbols():
    """Return the kernel's global symbols."""
    symbols = set()
    proc = subprocess.Popen(['nm', 'netbsd'], stdout=subprocess.PIPE)
    for line in proc.stdout:
        # The line from nm have two or three fields, e.g.
        #          U sunmon_abort
        # 000005c8 T zs_abort
        item = line.split()
        if len(item) == 3:
            item.pop(0)
        sym_type, sym_name = item
        if sym_type in "TDB":
            symbols.add(sym_name)
    return symbols


def eliminate_used_symbols(filenames, symbols):
    """Remove symbols mentioned in relocation entries."""
    for filename in filenames:
        proc = subprocess.Popen(['objdump', '-r', filename],
                                stdout=subprocess.PIPE)
        for line in proc.stdout:
            # The relevant lines of the output have three fields, e.g.
            #   00007a6 UNKNOWN           zs_conschan
            # There are also some documentation lines
            #   OFFSET   TYPE              VALUE
            # that we ignore.
            item = line.split()
            if item and len(item) == 3 and item[0] != 'OFFSET':
                sym_name = item[-1]
                if sym_name in symbols:
                    del symbols[sym_name]


def find_source_file(objfile_name, sys_dir):
    """Find the source file corresponding to the object file.

    We use the heuristics that if there is exactly one file with the same
    name, but with a .c, .s, or .S suffix, then it is probably the correct
    source file."""
    pathlen = len(sys_dir) - 3
    name = os.path.basename(objfile_name)
    proc = subprocess.Popen(['find', sys_dir, '-name', name[:-1] + '[csS]'],
                            stdout=subprocess.PIPE)
    file_names = [line[pathlen:-1] for line in  proc.stdout]
    if len(file_names) == 1:
        return file_names[0]
    else:
        return objfile_name


def print_result(symbols, sys_dir, keep_libkern):
    """Print the result."""
    # Create dictionary from source file name to list of symbols.
    file_to_syms = collections.defaultdict(set)
    for sym_name, file_name in symbols.iteritems():
        if keep_libkern or file_name[:9] != 'lib/kern/':
            file_name = find_source_file(file_name, sys_dir)
            file_to_syms[file_name].add(sym_name)

    # Create a list of files to print. This is the files in file_to_syms,
    # where we have filtered out the files whose symbols are not present
    # in the kernel (this happens for unused files in archives).
    kernel_symbols = read_kernel_symbols()
    file_names = []
    for file_name in file_to_syms:
        symbols = list(file_to_syms[file_name])
        if symbols[0] in kernel_symbols:
            file_names.append(file_name)
    file_names.sort()

    # Print the result.
    for file_name in file_names:
        symbol_names = list(file_to_syms[file_name])
        symbol_names.sort()
        print file_name
        for sym_name in symbol_names:
            print '  ' + sym_name
        if file_name != file_names[-1]:
            print


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-k', help='include lib/kern in the result',
                        action='store_true')
    parser.add_argument('-s', help='top of the NetBSD source tree',
                        metavar='src_dir')
    args = parser.parse_args()

    if args.s:
        src_dir = args.s
    else:
        src_dir = '../../../../..'
    sys_dir = os.path.normpath(src_dir + '/sys')
    if not os.path.exists(sys_dir):
        sys.stderr.write(sys_dir + ': No such directory\n')
        sys.exit(1)

    file_names = get_obj_file_names()
    symbols = read_symbols(file_names)
    eliminate_used_symbols(file_names, symbols)
    print_result(symbols, sys_dir, args.k)


if __name__ == '__main__':
    main()
