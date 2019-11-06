#!/usr/bin/env python
# -*- coding: latin-1 -*-

# fs_shapeDNA
#
# script to compute ShapeDNA of FreeSurfer structures
#
# Original Author: Martin Reuter, Kersten Diers
# Date: Oct-18-2017

# ------------------------------------------------------------------------------
# TODO

# - was ist mit boundary conditions fuer python?

# ------------------------------------------------------------------------------
# imports

from __future__ import print_function
from builtins import str
from builtins import range

import warnings
import os
import sys
import shlex
import optparse
import subprocess
import tempfile
import uuid
import errno
import glob

# ------------------------------------------------------------------------------
# settings

warnings.filterwarnings('ignore', '.*negative int.*')
os.environ['OMP_NUM_THREADS'] = '1' # setenv OMP_NUM_THREADS 1

# ------------------------------------------------------------------------------
# help

HELPTEXT = """

SUMMARY
=======

Computes surface (and volume) models of FreeSurfer's subcortical and cortical 
structures and computes a spectral shape descriptor (ShapeDNA [1]).

Input can be one of the following:
--asegid  : an aseg label id to construct a surface of that ROI
--hsfid   : a hippocampal subfields id to construct a surface of that ROI
            (also pass --hemi)
--surf    : a surface, e.g. lh.white
--label   : a label file to cut out a surface patch (also pass --surf)
--aparcid : an aparc id to cut out that cortical ROI (also pass --surf)

If "meshfix" and "gmsh" are in the path, and shapeDNA-tetra is available in the 
$SHAPEDNA_HOME directory, it can also create and process tetrahedral meshes 
from closed surfaces, such as lh.white ( --dotet ).

Note that FreeSurfer needs to be sourced for this program to run. Unless the 
--python argument is used, the $SHAPEDNA_HOME environment variable needs to be 
set to point to the shapeDNA executables and key file.

REFERENCES
==========

Always cite [1] as it describes the method. If you use topological features of 
eigenfunctions, also cite [2]. [3] compares different discretizations of 
Laplace-Beltrami operators and shows that the used FEM appraoch performs best. 
If you do statistical shape analysis you may also want to cite [4] as it 
discusses medical applications.

[1] M. Reuter, F.-E. Wolter and N. Peinecke.
Laplace-Beltrami spectra as "Shape-DNA" of surfaces and solids.
Computer-Aided Design 38 (4), pp.342-366, 2006.
http://dx.doi.org/10.1016/j.cad.2005.10.011

[2] M. Reuter. Hierarchical Shape Segmentation and Registration
via Topological Features of Laplace-Beltrami Eigenfunctions.
International Journal of Computer Vision, 2009.
http://dx.doi.org/10.1007/s11263-009-0278-1

[3] M. Reuter, S. Biasotti, D. Giorgi, G. Patane, M. Spagnuolo.
Discrete Laplace-Beltrami operators for shape analysis and
segmentation. Computers & Graphics 33 (3), pp.381-390, 2009.
http://dx.doi.org/10.1016/j.cag.2009.03.005

[4] M. Reuter, F.-E. Wolter, M. Shenton, M. Niethammer.
Laplace-Beltrami Eigenvalues and Topological Features of
Eigenfunctions for Statistical Shape Analysis.
Computer-Aided Design 41 (10), pp.739-755, 2009.
http://dx.doi.org/10.1016/j.cad.2009.02.007
"""

CURRENTLYNOTNEEDEDTXT="""

ARGUMENTS
=========

REQUIRED ARGUMENTS

--sid <name>      Subject ID

One of the following:

--asegid <int>    Segmentation ID of structure in aseg.mgz (e.g. 17 is 
                  Left-Hippocampus), for ID's check <sid>/stats/aseg.stats 
                  or $FREESURFER_HOME/FreeSurferColorLUT.txt.

--hsfid <int>     Segmentation ID of structure in 
                  [lr]h.<segmentation>Labels-<label>.<version><suffix>
                  For ID's (e.g. 206 is CA1) check compressionLookupTable.txt 
                  in $FREESURFER_HOME/average/HippoSF/atlas. Also specify 
                  --hemi if using this argument.

--surf <name>     lh.pial, rh.pial, lh.white, rh.white etc. to select a 
                  surface from the <sid>/surfs directory.

REQUIRED ARGUMENT if using --hsfid

--hemi <name>     'lh' or 'rh' hemisphere

OPTIONAL ARGUMENTS

--sdir <name>     Subjects directory (or set via environment $SUBJECTS_DIR)

--outdir <name>   Output directory (default: <sdir>/<sid>/brainprint/)

--outsurf <name>  Name for surface output (with --asegid)
                  (default: aseg.<asegid>.surf )

--outev <name>    Name for eigenvalue output
                  (default: <(out)surf>.<shapedna_parametrs>.ev)

--hsflabel <name> Label of hippocampal subfield segmentation, e.g. T1 or 
                  T1-T1T2_HC_segmentation (default: T1)

--hsfver <name>   Version of hippocampal subfield segmentation, e.g v10 or 
                  v20 (default: v10)

--hsfseg <name>   Name of segmentation, e.g. hippoSf or hippoAmyg (default: 
                  hippoSf)

--hsfsfx <name>   Suffix of segmenation, e.g. FSvoxelSpace or none (specify 
                  as '') (default: FSvoxelSpace)

--python          Use Python version instead of the binary shapeDNA scripts

ShapeDNA parameters (see shapeDNA-tria --help for details):

--num <int>       Number of eigenvalues/vectors to compute (default: 50)

--degree <int>    FEM degree (default 1)

--bcond <int>     Boundary condition (0=Dirichlet, 1=Neumann default)

--evec            Additionally compute eigenvectors

--ignorelq        Ignore low quality in input mesh

--sparam "<str>"  Additional parameters for shapeDNA-tria

"""

# ------------------------------------------------------------------------------
# auxiliary functions

# custom split function
def split_callback(option, opt, value, parser):
  setattr(parser.values, option.dest, value.split(','))

# custom print function
def my_print(message):
    """
    print message, then flush stdout
    """
    print(message)
    sys.stdout.flush()

# function to check if fileis executable; will also return full path
def which(program):
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file
        if is_exe(os.path.join(os.getenv('SHAPEDNA_HOME'),program)):
            return os.path.join(os.getenv('SHAPEDNA_HOME'),program)
        if is_exe(os.path.join('.',program)):
            return os.path.join('.',program)

    return None

# function to run commands
def run_cmd(cmd,err_msg):
    """
    execute the comand
    """
    clist = cmd.split()
    progname=which(clist[0])
    if (progname) is None:
        my_print('ERROR: '+ clist[0] +' not found in path!')
        sys.exit(1)
    clist[0]=progname
    cmd = ' '.join(clist)
    my_print('#@# Command: ' + cmd+'\n')

    args = shlex.split(cmd)
    try:
        subprocess.check_call(args)
    except subprocess.CalledProcessError as e:
        my_print('ERROR: '+err_msg)
        #sys.exit(1)
        raise
    my_print('\n')

# ------------------------------------------------------------------------------
# parse options

def options_parse():
    """
    Command Line Options Parser:
    initiate the option parser and return the parsed object
    """
    parser = optparse.OptionParser(version='$Id: fs_shapeDNA,v 1.21 2013/05/17 15:14:08 mreuter Exp $', usage=HELPTEXT)

    # help text
    h_sid       = '(REQUIRED) subject ID (FS processed directory inside the subjects directory)'
    h_sdir      = 'FS subjects directory (or set environment $SUBJECTS_DIR)'

    h_asegid    = 'segmentation ID of structure in aseg.mgz (e.g. 17 is Left-Hippocampus), for ID\'s check <sid>/stats/aseg.stats or $FREESURFER_HOME/FreeSurferColorLUT.txt'
    h_hsfid     = 'segmentation ID of structure in [lr]h.<segmentation>Labels-<label>.<version>.<suffix> (e.g. 206 is CA1), for ID\'s check $FREESURFER_HOME/average/HippoSF/atlas/compressionLookupTable.txt; also specify --hemi if using this argument'
    h_hsflabel  = 'Label of hippocampal subfield segmentation, e.g. T1 or T1-T1T2_HC_segmentation (default: T1)'
    h_hsfver    = 'Version of hippocampal subfield segmentation, e.g v10 or v20 (default: v10)'
    h_hsfseg    = 'Label of segmentation, e.g hippoSf or hippoAmyg (default: hippoSf)'
    h_hsfsfx    = 'Suffix of segmentation, e.g FSvoxelSpace or none (default: FSvoxelspace)'
    h_hemi      = '\'lh\' or \'rh\' hemisphere; required when using --hsfid'
    h_surf      = 'surface name, e.g. lh.pial, rh.pial, lh.white, rh.white etc. to select a surface from the <sid>/surfs directory'
    h_aparcid   = 'segmentation ID of structure in aparc (e.g. 24 is precentral), requires --surf (including the hemi prefix), for ID\'s check $FREESURFER_HOME/average/colortable_desikan_killiany.txt'
    h_label     = 'full path to label file, to create surface patch, requires --surf (including the hemi prefix)'
    h_source    = 'specify source subject with --label (to map label e.g. from fsaverage space)'

    h_dotet     = 'construct a tetrahedra volume mesh and compute spectra of solid'
    h_fixiter   = 'iterations of meshfix (default=4), only with --dotet'

    h_outdir    = 'Output directory (default: <sdir>/<sid>/brainprint/ )'
    h_outsurf   = 'Full path for surface output in VTK format (with --asegid default: <outdir>/aseg.<asegid>.vtk )'
    h_outtet    = 'Full path for tet output (with --dotet) (default: <outdir>/<(out)surf>.msh )'
    h_outev     = 'Full path for eigenvalue output (default: <outdir>/<(out)surf or outtet>.ev )'

    h_num       = 'number of eigenvalues/vectors to compute (default: 50)'
    h_degree    = 'degree for FEM computation (1=linear default, 3=cubic)'
    h_bcond     = 'boundary condition (1=Neumann default, 0=Dirichlet )'
    h_evec      = 'bool to switch on eigenvector computation'
    h_ignorelq  = 'ignore low quality in input mesh'
    h_refmin    = 'mesh refinement so that DOF is at least <int>'
    h_tsmooth   = 'tangential smoothing iterations (after refinement)'
    h_gsmooth   = 'geometry smoothing iterations (after refinement)'
    h_param2d   = 'additional parameters for shapeDNA-tria'
    h_python    = 'use Python version of the shapeDNA scripts instead of binary version'

    # Add options

    # Sepcify inputs
    parser.add_option('--sdir', dest='sdir', help=h_sdir)

    group = optparse.OptionGroup(parser, "Required Options", "Specify --sid and select one of the other options")
    group.add_option('--sid',     dest='sid',      help=h_sid)
    group.add_option('--asegid',  dest='asegid' ,  help=h_asegid,  type='string', action='callback', callback=split_callback)
    group.add_option('--hsfid',   dest='hsfid' ,   help=h_hsfid,   type='string', action='callback', callback=split_callback)
    group.add_option('--hemi',    dest='hemi' ,    help=h_hemi)
    group.add_option('--aparcid', dest='aparcid' , help=h_aparcid, type='string', action='callback', callback=split_callback)
    group.add_option('--surf' ,   dest='surf' ,    help=h_surf)
    group.add_option('--label' ,  dest='label' ,   help=h_label)
    parser.add_option_group(group)

    group = optparse.OptionGroup(parser, "Additional Flags", )
    group.add_option('--source' ,  dest='source',   help=h_source)
    group.add_option('--dotet' ,   dest='dotet',    help=h_dotet,    default=False, action='store_true')
    group.add_option('--fixiter',  dest='fixiter',  help=h_fixiter,  default=4, type='int')
    group.add_option('--hsflabel', dest='hsflabel', help=h_hsflabel, default='T1')
    group.add_option('--hsfver',   dest='hsfver',   help=h_hsfver,   default='v10')
    group.add_option('--hsfseg',   dest='hsfseg',   help=h_hsfseg,   default='hippoSf')
    group.add_option('--hsfsfx',   dest='hsfsfx',   help=h_hsfsfx,   default='FSvoxelSpace')
    group.add_option('--python' ,  dest='python',   help=h_python,   default=False, action='store_true' )
    parser.add_option_group(group)

    #output switches
    group = optparse.OptionGroup(parser, "Output Parameters" )
    group.add_option('--outdir',  dest='outdir',   help=h_outdir)
    group.add_option('--outsurf', dest='outsurf',  help=h_outsurf)
    group.add_option('--outtet',  dest='outtet',   help=h_outtet)
    group.add_option('--outev',   dest='outev',    help=h_outev)
    parser.add_option_group(group)

    #shapedna switches
    group = optparse.OptionGroup(parser, "ShapeDNA Parameters","See shapeDNA-tria --help for details")
    group.add_option('--num' ,     dest='num',      help=h_num,      default=50, type='int')
    group.add_option('--degree' ,  dest='degree',   help=h_degree,   default=1,  type='int')
    group.add_option('--bcond' ,   dest='bcond',    help=h_bcond,    default=1,  type='int')
    group.add_option('--evec' ,    dest='evec',     help=h_evec,     default=False, action='store_true' )
    group.add_option('--ignorelq', dest='ignorelq', help=h_ignorelq, default=False, action='store_true')
    group.add_option('--refmin',   dest='refmin',   help=h_refmin,   default=0,  type='int')
    group.add_option('--tsmooth',  dest='tsmooth',  help=h_tsmooth,  default=0,  type='int')
    group.add_option('--gsmooth',  dest='gsmooth',  help=h_gsmooth,  default=0,  type='int')
    group.add_option('--param2d',  dest='param2d',  help=h_param2d)
    parser.add_option_group(group)

    (options, args) = parser.parse_args()
    #if len(args) == 0:
    #    parser.print_help()
    #    my_print('\n')
    #    sys.exit(1)

    # WITHOUT FREESURFER DO NOTHING
    fshome = os.getenv('FREESURFER_HOME')
    if fshome is None:
        parser.print_help()
        my_print('\nERROR: Environment variable FREESURFER_HOME not set. \n')
        my_print('       Make sure to source your FreeSurfer installation.\n')
        sys.exit(1)

    # shapeDNA environment variable needs to be present unless using python version
    sdnahome = os.getenv('SHAPEDNA_HOME')
    if not options.python and sdnahome is None:
        parser.print_help()
        my_print('\nERROR: Environment variable SHAPEDNA_HOME not set.\n')
        my_print('       Set SHAPEDNA_HOME to point to the shapeDNA-tria installation.\n')
        sys.exit(1)

    # shapeDNA-tria binary must exist unless using python version
    sdna = os.path.join(sdnahome,"shapeDNA-tria")
    if not options.python and not os.path.exists(sdna) and not options.dotet:
        parser.print_help()
        my_print('\nERROR: Cannot find shapeDNA-tria\n')
        my_print('       Make sure that binary is at $SHAPEDNA_HOME \n')
        sys.exit(1)

    # shapeDNA-tetra binary must exist unless using python version
    if not options.python and which("shapeDNA-tetra") is None and options.dotet:
        parser.print_help()
        my_print('\nERROR: Cannot find shapeDNA-tetra\n')
        my_print('       Make sure that binary is at $SHAPEDNA_HOME \n')
        sys.exit(1)

    # subjects dir needs to be present, at least as an environment variable
    if options.sdir is None:
        options.sdir = os.getenv('SUBJECTS_DIR')

    if options.sdir is None:
        parser.print_help()
        my_print('\nERROR: specify subjects directory via --sdir or $SUBJECTS_DIR\n')
        sys.exit(1)

    # subject id must be given and exist in subjects dir
    if options.sid is None:
        parser.print_help()
        my_print('\nERROR: Specify --sid\n')
        sys.exit(1)

    subjdir = os.path.join(options.sdir,options.sid)
    if not os.path.exists(subjdir):
        my_print('ERROR: cannot find sid in subjects directory\n')
        sys.exit(1)

    # surface file must exist when using label or parcellation files
    if options.label is not None and options.surf is None:
        parser.print_help()
        my_print('\nERROR: Specify --surf with --label\n')
        sys.exit(1)

    if options.aparcid is not None and options.surf is None:
        parser.print_help()
        my_print('\nERROR: Specify --surf with --aparc\n')
        sys.exit(1)

    # input needs to be either a surf or aseg or hipposf label(s)
    if options.asegid is None and options.surf is None and options.hsfid is None:
        parser.print_help()
        my_print('\nERROR: Specify either --asegid or --hsfid or --surf\n')
        sys.exit(1)

    # and it cannot be more than one of them
    if sum((options.asegid is not None, options.surf is not None, options.hsfid is not None))>1:
        parser.print_help()
        my_print('\nERROR: Specify either --asegid or --hsfid or --surf (not more than one of them)\n')
        sys.exit(1)

    # if --hsfid is used, then also --hemi needs to be specified
    if options.hsfid is not None and options.hemi is None:
        parser.print_help()
        my_print('\nERROR: Specify --hemi\n')
        sys.exit(1)

    # hemi needs to be either lh or rh
    if options.hemi is not None and options.hemi!="lh" and options.hemi!="rh":
        parser.print_help()
        my_print('\nERROR: Specify either --hemi=lh or --hemi=rh\n')
        sys.exit(1)

    if options.hemi is not None and options.hemi!="lh" and options.hemi!="rh":
        parser.print_help()
        my_print('\nERROR: Specify either --hemi=lh or --hemi=rh\n')
        sys.exit(1)

    # check suffix to start with a point
    if len(options.hsfsfx)>0 and options.hsfsfx[0] is not ".":
        options.hsfsfx="."+options.hsfsfx
        print(options.hsfsfx)

    # check if required files are present for --hsfid
    if options.hsfid is not None and options.hemi=="lh" and not os.path.isfile(os.path.join(options.sdir,options.sid,'mri','lh.'+options.hsfseg+'Labels-'+options.hsflabel+'.'+options.hsfver+options.hsfsfx+'.mgz')):
        parser.print_help()
        my_print('\nERROR: could not find '+os.path.join(options.sdir,options.sid,'mri','lh.'+options.hsfseg+'Labels-'+options.hsflabel+'.'+options.hsfver+options.hsfsfx+'.mgz')+'\n')
        sys.exit(1)

    if options.hsfid is not None and options.hemi=="rh" and not os.path.isfile(os.path.join(options.sdir,options.sid,'mri','rh.'+options.hsfseg+'Labels-'+options.hsflabel+'.'+options.hsfver+options.hsfsfx+'.mgz')):
        parser.print_help()
        my_print('\nERROR: could not find '+os.path.join(options.sdir,options.sid,'mri','rh.'+options.hsfseg+'Labels-'+options.hsflabel+'.'+options.hsfver+options.hsfsfx+'.mgz')+'\n')
        sys.exit(1)

    # set default output dir (maybe this should be ./ ??)
    if options.outdir is None:
        options.outdir = os.path.join(subjdir,'brainprint')
    try:
        os.mkdir(options.outdir)
    except OSError as e:
        if e.errno != os.errno.EEXIST:
            raise e
        pass

    # check if we have write access to output dir
    try:
        testfile = tempfile.TemporaryFile(dir = options.outdir)
        testfile.close()
    except OSError as e:
        if e.errno != errno.EACCES:  # 13
            e.filename = options.outdir
            raise
        my_print('\nERROR: '+options.outdir+' not writeable (check access)!\n')
        sys.exit(1)

    # initialize outsurf
    if options.outsurf is None:
        # for aseg stuff, we need to create a surface (and we'll keep it around)
        if options.asegid is not None:
            astring  = '_'.join(options.asegid)
            #surfname = 'aseg.'+astring+'.surf'
            surfname = 'aseg.'+astring+'.vtk'
            options.outsurf = os.path.join(options.outdir,surfname)
        elif options.hsfid is not None:
            astring  = str(options.hemi)+'-'+'_'.join(options.hsfid)
            #surfname = 'hsf.'+astring+'.surf'
            surfname = 'hsf.'+astring+'.vtk'
            options.outsurf = os.path.join(options.outdir,surfname)
        elif options.label is not None:
            surfname = os.path.basename(options.surf)+'.'+os.path.basename(options.label)+'.vtk'
            options.outsurf = os.path.join(options.outdir,surfname)
        elif options.aparcid is not None:
            astring  = '_'.join(options.aparcid)
            surfname = os.path.basename(options.surf)+'.aparc.'+astring+'.vtk'
            options.outsurf = os.path.join(options.outdir,surfname)
        else:
            # for surfaces, a refined/smoothed version could be written
            surfname = os.path.basename(options.surf)+'.vtk'
            options.outsurf = os.path.join(options.outdir,surfname)
    else:
        # make sure it is vtk ending
        if (os.path.splitext(options.outsurf)[1]).upper() != '.VTK':
            my_print('ERROR: outsurf needs vtk extension (VTK format)')
            sys.exit(1)

    # for 3d processing, initialize outtet:
    if options.dotet and options.outtet is None:
        surfname = os.path.basename(options.outsurf)
        options.outtet = os.path.join(options.outdir,surfname+'.msh')

    # set source to sid if empty
    if options.source is None:
        options.source = options.sid

    # if label does not exist, search in subject label dir
    if options.label is not None and not os.path.isfile(options.label):
        ltemp = os.path.join(options.sdir,options.source,'label',options.label)
        if os.path.isfile(ltemp):
            options.label = ltemp
        else:
            parser.print_help()
            my_print('\nERROR: Specified --label not found\n')
            sys.exit(1)

    # initialize outev
    if options.outev is None:
        if options.dotet:
            options.outev = options.outtet+'.ev'
        else:
            options.outev = options.outsurf+'.ev'

    return options

# ------------------------------------------------------------------------------
# image and surface processing functions

# gets global path to surface input (if it is a FS surf)
def get_surf_surf(sdir,sid,surf):
    return os.path.join(sdir,sid,'surf',surf)

# creates tria surface from label (and specified surface)
# maps the label first if source is different from sid
def get_label_surf(sdir,sid,label,surf,source,outsurf):
    subjdir  = os.path.join(sdir,sid)
    outdir   = os.path.dirname( outsurf )
    stlsurf  = os.path.join(outdir,'label'+str(uuid.uuid4())+'.stl')

    # get hemi from surf
    splitsurf = surf.split(".",1)
    hemi = splitsurf[0]
    surf = splitsurf[1]
    # map label if necessary
    mappedlabel = label
    if (source != sid):
        mappedlabel = os.path.join(outdir,os.path.basename(label)+'.'+str(uuid.uuid4())+'.label')
        cmd = 'mri_label2label --sd '+sdir+' --srclabel '+label+' --srcsubject '+ source+' --trgsubject '+sid+' --trglabel '+mappedlabel+' --hemi '+hemi+' --regmethod surface'
        run_cmd(cmd,'mri_label2label failed?')
    # make surface path (make sure output is stl, this currently needs fsdev, will probably be in 6.0)
    cmd = 'label2patch -writesurf -sdir '+sdir+' -surf '+ surf + ' ' +sid+' '+hemi+' '+mappedlabel+' '+stlsurf
    run_cmd(cmd,'label2patch failed?')
    cmd = 'mris_convert '+stlsurf+' '+outsurf
    run_cmd(cmd,'mris_convert failed.')

    # cleanup map label if necessary
    if (source != sid):
        cmd ='rm '+mappedlabel
        run_cmd(cmd,'rm mapped label '+mappedlabel+' failed.')
    cmd = 'rm '+stlsurf
    run_cmd(cmd,'rm stlsurf failed.')
    # return surf name
    return outsurf

# creates a surface from the aseg and label info and writes it to the outdir
def get_aseg_surf(sdir,sid,asegid,outsurf):
    astring2 = ' '.join(asegid)
    subjdir  = os.path.join(sdir,sid)
    aseg     = os.path.join(subjdir,'mri','aseg.mgz')
    norm     = os.path.join(subjdir,'mri','norm.mgz')
    outdir   = os.path.dirname( outsurf )
    tmpname  = 'aseg.'+str(uuid.uuid4())
    segf     = os.path.join(outdir,tmpname+'.mgz')
    segsurf  = os.path.join(outdir,tmpname+'.surf')
    # binarize on selected labels (creates temp segf)
    ptinput = aseg
    ptlabel = str(asegid[0])
    #if len(asegid) > 1:
    # always binarize first, otherwise pretess may scale aseg if labels are larger than 255 (e.g. aseg+aparc, bug in mri_pretess?)
    cmd ='mri_binarize --i '+aseg+' --match '+astring2+' --o '+segf
    run_cmd(cmd,'mri_binarize failed.')
    ptinput = segf
    ptlabel = '1'
    # if norm exist, fix label (pretess)
    if os.path.isfile(norm):
        cmd ='mri_pretess '+ptinput+' '+ptlabel+' '+norm+' '+segf
        run_cmd(cmd,'mri_pretess failed.')
    else:
        if not os.path.isfile(segf):
            # cp segf if not exist yet
            # (it exists already if we combined labels above)
            cmd = 'cp '+ptinput+' '+segf
            run_cmd(cmd,'cp segmentation file failed.')
    # runs marching cube to extract surface
    cmd ='mri_mc '+segf+' '+ptlabel+' '+segsurf
    run_cmd(cmd,'mri_mc failed?')
    # convert to stl
    cmd ='mris_convert '+segsurf+' '+outsurf
    run_cmd(cmd,'mris_convert failed.')
    # cleanup temp files
    cmd ='rm '+segf
    run_cmd(cmd,'rm temp segf failed.')
    cmd ='rm '+segsurf
    run_cmd(cmd,'rm temp segsurf failed.')
    # return surf name
    return outsurf

# creates a surface from the hsf and label info and writes it to the outdir
def get_hsf_surf(sdir,sid,hsfid,outsurf,options):
    astring2 = ' '.join(hsfid)
    subjdir  = os.path.join(sdir,sid)
    if options.hemi=="lh":
        hsf      = os.path.join(options.sdir,options.sid,'mri','lh.'+options.hsfseg+'Labels-'+options.hsflabel+'.'+options.hsfver+options.hsfsfx+'.mgz')
        my_print('Creating surfaces from '+hsf)
    elif options.hemi=="rh":
        hsf      = os.path.join(options.sdir,options.sid,'mri','rh.'+options.hsfseg+'Labels-'+options.hsflabel+'.'+options.hsfver+options.hsfsfx+'.mgz')
        my_print('Creating surfaces from '+hsf)
    if not os.path.isfile(hsf):
        my_print('ERROR: could not open '+hsf)
        sys.exit(1)
    norm     = os.path.join(subjdir,'mri','norm.mgz')
    outdir   = os.path.dirname( outsurf )
    tmpname  = 'hsf.'+str(uuid.uuid4())
    segf     = os.path.join(outdir,tmpname+'.mgz')
    segsurf  = os.path.join(outdir,tmpname+'.surf')
    # binarize on selected labels (creates temp segf)
    ptinput = hsf
    ptlabel = str(hsfid[0])
    #if len(hsfid) > 1:
    # always binarize first, otherwise pretess may scale aseg if labels are larger than 255 (e.g. aseg+aparc, bug in mri_pretess?)
    cmd ='mri_binarize --i '+hsf+' --match '+astring2+' --o '+segf
    run_cmd(cmd,'mri_binarize failed.')
    ptinput = segf
    ptlabel = '1'
    # if norm exist, fix label (pretess)
    if os.path.isfile(norm):
        cmd ='mri_pretess '+ptinput+' '+ptlabel+' '+norm+' '+segf
        run_cmd(cmd,'mri_pretess failed.')
    else:
        if not os.path.isfile(segf):
            # cp segf if not exist yet
            # (it exists already if we combined labels above)
            cmd = 'cp '+ptinput+' '+segf
            run_cmd(cmd,'cp segmentation file failed.')
    # runs marching cube to extract surface
    cmd ='mri_mc '+segf+' '+ptlabel+' '+segsurf
    run_cmd(cmd,'mri_mc failed?')
    # convert to stl
    cmd ='mris_convert '+segsurf+' '+outsurf
    run_cmd(cmd,'mris_convert failed.')
    # cleanup temp files
    cmd ='rm '+segf
    run_cmd(cmd,'rm temp segf failed.')
    cmd ='rm '+segsurf
    run_cmd(cmd,'rm temp segsurf failed.')
    # return surf name
    return outsurf

# creates a surface from the aparc and label number and writes it to the outdir
def get_aparc_surf(sdir,sid,surf,aparcid,outsurf):
    astring2 = ' '.join(aparcid)
    subjdir  = os.path.join(sdir,sid)
    outdir   = os.path.dirname( outsurf )
    rndname = str(uuid.uuid4())
    # get hemi from surf
    hemi = surf.split(".",1)[0]
    # convert annotation id to label:
    alllabels = ''
    for aid in aparcid:
        # create label of this id
        outlabelpre = os.path.join(outdir,hemi+'.aparc.'+rndname)
        cmd = 'mri_annotation2label --sd '+sdir+' --subject '+sid+' --hemi '+hemi+' --label '+str(aid)+' --labelbase '+outlabelpre
        run_cmd(cmd,'mri_annotation2label failed?')
        alllabels = alllabels+'-i '+outlabelpre+"-%03d.label" % int(aid)+' '
    # merge labels (if more than 1)
    mergedlabel = outlabelpre+"-%03d.label" % int(aid)
    if len(aparcid) > 1:
        mergedlabel = os.path.join(outdir,hemi+'.aparc.all.'+rndname+'.label')
        cmd = 'mri_mergelabels '+alllabels+' -o '+mergedlabel
        run_cmd(cmd,'mri_mergelabels failed?')
    # make to surface (call subfunction above)
    get_label_surf(sdir,sid,mergedlabel,surf,sid,outsurf)
    # cleanup
    if len(aparcid) > 1:
        cmd ='rm '+mergedlabel
        run_cmd(cmd,'rm '+mergedlabel+' failed?')
    for aid in aparcid:
        outlabelpre = os.path.join(outdir,hemi+'.aparc.'+rndname+"-%03d.label" % int(aid))
        cmd ='rm '+outlabelpre
        run_cmd(cmd,'rm '+outlabelpre+' failed?')
    # return surf name
    return outsurf

# get tetmesh using gmsh and meshfix
def get_tetmesh(surf,outtet,fixiter):
    surfbase  = os.path.basename(surf)
    outdir    = os.path.dirname( outtet )
    surftemp_stl = os.path.join(outdir,surfbase+'.temp.stl')

    # massage surface mesh (rm handles, 60000 vertices, uniform)
    cmd='mris_convert '+surf+' '+surftemp_stl
    run_cmd(cmd,'mris_convert (to STLs) failed')
    # cmd='meshfix '+surftemp_stl+' -a 2.0 --remove-handles -q --stl -o '+surftemp_stl
    # run_cmd(cmd,'meshfix (remove-handles) failed, is it in your path?')
    cmd='meshfix '+surftemp_stl+' -a 2.0 -u 5 --vertices 60000 -q --stl -o '+surftemp_stl
    run_cmd(cmd,'meshfix (downsample) failed?')
    for num in range(0,fixiter):
        cmd='meshfix '+surftemp_stl+' -a 2.0 -u 1 -q --stl -o '+surftemp_stl
        run_cmd(cmd,'meshfix failed ('+str(num)+'a)?')
        cmd='meshfix '+surftemp_stl+' -a 2.0 -q --stl -o '+surftemp_stl
        run_cmd(cmd,'meshfix failed ('+str(num)+'b)?')

    # replacing meshfix never worked:
    # sdnahome = os.getenv('SHAPEDNA_HOME')
    # triaio = os.path.join(sdnahome,"triaIO")
    # cmd=triaio+' --infile '+surf+' --outfile '+surftemp_stl' --contractedges --remeshbk 1'
    # run_cmd(cmd,'triaIO remeshing failed?')

    # write gmsh geofile
    geofile  = os.path.join(outdir,'gmsh.'+str(uuid.uuid4())+'.geo')
    g = open(geofile, 'w')
    g.write("Mesh.Algorithm3D=4;\n")
    g.write("Mesh.Optimize=1;\n")
    g.write("Mesh.OptimizeNetgen=1;\n")
    g.write("Merge \"" + surfbase+'.temp.stl' + "\";\n")
    g.write("Surface Loop(1) = {1};\n")
    g.write("Volume(1) = {1};\n")
    g.write("Physical Volume(1) = {1};\n")
    g.close()

    # use gmsh to create tet mesh
    cmd = 'gmsh -3 -o '+outtet+' '+geofile
    run_cmd(cmd,'gmsh failed, is it in your path?')

    # cleanup
    cmd ='rm '+geofile
    run_cmd(cmd,'rm temp geofile failed?')
    cmd='rm '+surftemp_stl
    run_cmd(cmd,'rm temp stl surface failed?')

    # return tetmesh filename
    return outtet

# ------------------------------------------------------------------------------
# shapeDNA functions

# run shapeDNA-tetra
def run_shapeDNAtetra(tetmesh,outev,options):

    if not options.python:    
        # run shapeDNA-tretra binary
        sdnahome = os.getenv('SHAPEDNA_HOME')
        sdna = os.path.join(sdnahome,"shapeDNA-tetra")
        # mesh refine degree num bcond ouput ev
        num = 50
        if options.num is not None:
            num = options.num
        degree = 1
        if options.degree is not None:
            degree = options.degree
        dirichlet = ""
        if options.bcond == 0:
            dirichlet = " --dirichlet"
        cmd =sdna+' --mesh '+tetmesh+' --num '+str(options.num)+' --outfile '+outev+' --degree '+str(options.degree)+dirichlet
        if options.evec:
            cmd = cmd+' --evec'
        run_cmd(cmd,'shapeDNA-tetra failed?')
    else:
        # run shapeDNA-tretra python
        from importVTKtetra import importVTKtetra
        from exportVTKtetra import exportVTKtetra
        from exportEV import exportEV
        # note that gettetmesh must have been run prior to calling this command
        # TODO: mesh is originally in msh format, needs conversion
        my_print('Tet option is currently not supported for python script')
        sys.exit(1)
        #
        v, t = importVTKtetra(tetmesh)
        ev, evec = laplaceTetra(v,t,k=options.num)
        d=dict()
        d['Refine']=0
        d['Degree']=1
        d['Dimension']=3
        d['Elements']=len(t)
        d['DoF']=len(v)
        d['NumEW']=options.num
        d['Eigenvalues']=ev
        d['Eigenvectors']=evec
        exportEV(d,outev)
        exportVTKtetra(v,t,outsurf)


# run shapeDNA-tria
def run_shapeDNAtria(surf,outev,outsurf,options):
    if not options.python:
        # options : num, degree, evec, ignorelq, refmin, tsmooth, gsmooth, param2d
        sdnahome = os.getenv('SHAPEDNA_HOME')
        sdna = os.path.join(sdnahome,"shapeDNA-tria")
        num = 50
        if options.num is not None:
            num = options.num
        degree = 1
        if options.degree is not None:
            degree = options.degree
        dirichlet = ""
        if options.bcond == 0:
            dirichlet = " --dirichlet"
        cmd =sdna+' --mesh '+surf+' --num '+str(options.num)+' --outfile '+outev+' --degree '+str(options.degree)+dirichlet
        if options.evec:
            cmd = cmd+' --evec'
        if options.ignorelq:
            cmd = cmd+' --ignorelq'
        if options.refmin > 0:
            cmd = cmd+' --refmin '+str(options.refmin)
        if options.tsmooth > 0:
            cmd = cmd+' --tsmooth '+str(options.tsmooth)
        if options.gsmooth > 0:
            cmd = cmd+' --gsmooth '+str(options.gsmooth)
        if options.param2d is not None:
            cmd = cmd+' '+options.param2d
        if not outsurf == "":
            cmd = cmd+' --outmesh '+outsurf
        run_cmd(cmd,'shapeDNA-tria failed?')
    else:
        # imports
        from importVTK import importVTK
        from exportVTK import exportVTK
        from exportEV import exportEV
        #run shapedna triapython
        v, t = importVTK(surf)
        ev, evec = laplaceTria(v,t,k=options.num)
        d=dict()
        d['Refine']=0
        d['Degree']=1
        d['Dimension']=2
        d['Elements']=len(t)
        d['DoF']=len(v)
        d['NumEW']=options.num
        d['Eigenvalues']=ev
        d['Eigenvectors']=evec
        exportEV(d,outev)
        exportVTK(v,t,outsurf)
# ------------------------------------------------------------------------------
# shapeDNA functions (python)

# shapeDNA python: laplaceTria
def laplaceTria(v, t, k=10, lump=False):
    """
    Compute linear finite-element method Laplace-Beltrami spectrum
    """

    from scipy.sparse.linalg import LinearOperator, eigsh, splu
    useCholmod = True
    try:
        from sksparse.cholmod import cholesky
    except ImportError:
        useCholmod = False
    if useCholmod:
        print("Solver: cholesky decomp - performance optimal ...")
    else:
        print("Package scikit-sparse not found (Cholesky decomp)")
        print("Solver: spsolve (LU decomp) - performance not optimal ...")

    A, M = computeABtria(v,t,lump=lump)
    
    # turns out it is much faster to use cholesky and pass operator
    sigma=-0.01
    if useCholmod:
        chol = cholesky(A-sigma*M)
        OPinv = LinearOperator(matvec=chol,shape=A.shape, dtype=A.dtype)
    else:
        lu = splu(A-sigma*M)
        OPinv = LinearOperator(matvec=lu.solve,shape=A.shape, dtype=A.dtype)

    eigenvalues, eigenvectors = eigsh(A, k, M, sigma=sigma,OPinv=OPinv)

    return eigenvalues, eigenvectors

# shapeDNA python: laplaceTetra
def laplaceTetra(v, t, k=10, lump=False):
    """
    Compute linear finite-element method Laplace-Beltrami spectrum
    """

    from scipy.sparse.linalg import LinearOperator, eigsh, splu
    useCholmod = True
    try:
        from sksparse.cholmod import cholesky
    except ImportError:
        useCholmod = False
    if useCholmod:
        print("Solver: cholesky decomp - performance optimal ...")
    else:
        print("Package scikit-sparse not found (Cholesky decomp)")
        print("Solver: spsolve (LU decomp) - performance not optimal ...")

    A, M = computeABtetra(v,t,lump=lump)
    
    # turns out it is much faster to use cholesky and pass operator
    sigma=-0.01
    if useCholmod:
        chol = cholesky(A-sigma*M)
        OPinv = LinearOperator(matvec=chol,shape=A.shape, dtype=A.dtype)
    else:
        lu = splu(A-sigma*M)
        OPinv = LinearOperator(matvec=lu.solve,shape=A.shape, dtype=A.dtype)

    eigenvalues, eigenvectors = eigsh(A, k, M, sigma=sigma,OPinv=OPinv)
   
    return eigenvalues, eigenvectors

# shapeDNA python: computeABtria
def computeABtria(v, t, lump = False):
    """
    computeABtria(v,t) computes the two sparse symmetric matrices representing
           the Laplace Beltrami Operator for a given triangle mesh using
           the linear finite element method (assuming a closed mesh or 
           the Neumann boundary condition).

    Inputs:   v - vertices : list of lists of 3 floats
              t - triangles: list of lists of 3 int of indices (>=0) into v array

    Outputs:  A - sparse sym. (n x n) positive semi definite numpy matrix 
              B - sparse sym. (n x n) positive definite numpy matrix (inner product)

    Can be used to solve sparse generalized Eigenvalue problem: A x = lambda B x
    or to solve Poisson equation: A x = B f (where f is function on mesh vertices)
    or to solve Laplace equation: A x = 0
    or to model the operator's action on a vector x:   y = B\(Ax) 
    """

    import sys
    import numpy as np
    from scipy import sparse
  
    v = np.array(v)
    t = np.array(t)

    # Compute vertex coordinates and a difference vector for each triangle:
    t1 = t[:, 0]
    t2 = t[:, 1]
    t3 = t[:, 2]
    v1 = v[t1, :]
    v2 = v[t2, :]
    v3 = v[t3, :]
    v2mv1 = v2 - v1
    v3mv2 = v3 - v2
    v1mv3 = v1 - v3

    # Compute cross product and 4*vol for each triangle:
    cr  = np.cross(v3mv2,v1mv3)
    vol = 2 * np.sqrt(np.sum(cr*cr, axis=1))
    # zero vol will cause division by zero below, so set to small value:
    vol_mean = 0.0001*np.mean(vol)
    vol[vol<sys.float_info.epsilon] = vol_mean 

    # compute cotangents for A
    # using that v2mv1 = - (v3mv2 + v1mv3) this can also be seen by 
    # summing the local matrix entries in the old algorithm
    A12 = np.sum(v3mv2*v1mv3,axis=1)/vol
    A23 = np.sum(v1mv3*v2mv1,axis=1)/vol
    A31 = np.sum(v2mv1*v3mv2,axis=1)/vol
    # compute diagonals (from row sum = 0)
    A11 = -A12-A31
    A22 = -A12-A23
    A33 = -A31-A23
    # stack columns to assemble data
    localA = np.column_stack((A12, A12, A23, A23, A31, A31, A11, A22, A33))
    I = np.column_stack((t1, t2, t2, t3, t3, t1, t1, t2, t3))
    J = np.column_stack((t2, t1, t3, t2, t1, t3, t1, t2, t3))
    # Flatten arrays:
    I = I.flatten()
    J = J.flatten()
    localA = localA.flatten()
    # Construct sparse matrix:
    A = sparse.csc_matrix((localA, (I, J)))

    if not lump:
        # create b matrix data (account for that vol is 4 times area)
        Bii = vol / 24
        Bij = vol / 48
        localB = np.column_stack((Bij, Bij, Bij, Bij, Bij, Bij, Bii, Bii, Bii))
        localB = localB.flatten()
        B = sparse.csc_matrix((localB, (I, J)))
    else:
        # when lumping put all onto diagonal  (area/3 for each vertex)
        Bii = vol / 12
        localB = np.column_stack((Bii, Bii, Bii))
        I = np.column_stack((t1, t2, t3))
        I = I.flatten()
        localB = localB.flatten()
        B = sparse.csc_matrix((localB, (I, I)))

    return A, B

# shapeDNA python: computeABtetra
def computeABtetra(v, t, lump = False):
    """
    computeABtetra(v,t) computes the two sparse symmetric matrices representing
           the Laplace Beltrami Operator for a given tetrahedral mesh using
           the linear finite element method (Neumann boundary condition).

    Inputs:   v - vertices : list of lists of 3 floats
              t - tetras   : list of lists of 4 int of indices (>=0) into v array
                             Ordering is important: first three vertices for
                             triangle counter-clockwise when looking at it from 
                             the inside of the tetrahedron 

    Outputs:  A - sparse sym. (n x n) positive semi definite numpy matrix 
              B - sparse sym. (n x n) positive definite numpy matrix (inner product)

    Can be used to solve sparse generalized Eigenvalue problem: A x = lambda B x
    or to solve Poisson equation: A x = B f (where f is function on mesh vertices)
    or to solve Laplace equation: A x = 0
    or to model the operator's action on a vector x:   y = B\(Ax) 
    """

    import numpy as np
    from scipy import sparse

    v = np.array(v)
    t = np.array(t)

    # Compute vertex coordinates and a difference vector for each triangle:
    t1 = t[:, 0]
    t2 = t[:, 1]
    t3 = t[:, 2]
    t4 = t[:, 3]
    v1 = v[t1, :]
    v2 = v[t2, :]
    v3 = v[t3, :]
    v4 = v[t4, :]
    e1 = v2 - v1
    e2 = v3 - v2
    e3 = v1 - v3
    e4 = v4 - v1
    e5 = v4 - v2
    e6 = v4 - v3

    # Compute cross product and 6 * vol for each triangle:
    cr  = np.cross(e1,e3)
    vol = np.abs(np.sum(e4*cr, axis=1))
    # zero vol will cause division by zero below, so set to small value:
    vol_mean = 0.0001*np.mean(vol)
    vol[vol==0] = vol_mean 

    # compute dot products of edge vectors
    e11 = np.sum(e1*e1,axis=1)
    e22 = np.sum(e2*e2,axis=1)
    e33 = np.sum(e3*e3,axis=1)
    e44 = np.sum(e4*e4,axis=1)
    e55 = np.sum(e5*e5,axis=1)
    e66 = np.sum(e6*e6,axis=1)
    e12 = np.sum(e1*e2,axis=1)
    e13 = np.sum(e1*e3,axis=1)
    e14 = np.sum(e1*e4,axis=1)
    e15 = np.sum(e1*e5,axis=1)
    e23 = np.sum(e2*e3,axis=1)
    e25 = np.sum(e2*e5,axis=1)
    e26 = np.sum(e2*e6,axis=1)
    e34 = np.sum(e3*e4,axis=1)
    e36 = np.sum(e3*e6,axis=1)

    # compute entries for A (negations occur when one edge direction is flipped)
    # these can be computed multiple ways
    # basically for ij, take opposing edge (call it Ek) and two edges from the starting
    # point of Ek to point i (=El) and to point j (=Em), then these are of the 
    # scheme:   (El * Ek)  (Em * Ek) - (El * Em) (Ek * Ek)  
    # where * is vector dot product
    A12 = (- e36 * e26 + e23 * e66)/vol
    A13 = (- e15 * e25 + e12 * e55)/vol
    A14 = (e23 * e26 - e36 * e22)/vol
    A23 = (- e14 * e34 + e13 * e44)/vol
    A24 = (e13 * e34 - e14 * e33)/vol
    A34 = (- e14 * e13 + e11 * e34)/vol
    
    # compute diagonals (from row sum = 0)
    A11 = -A12-A13-A14
    A22 = -A12-A23-A24
    A33 = -A13-A23-A34
    A44 = -A14-A24-A34

    # stack columns to assemble data
    localA = np.column_stack((A12, A12, A23, A23, A13, A13, A14, A14, A24, A24, A34, A34, A11, A22, A33, A44))
    I = np.column_stack((t1, t2, t2, t3, t3, t1, t1, t4, t2, t4, t3, t4, t1, t2, t3, t4))
    J = np.column_stack((t2, t1, t3, t2, t1, t3, t4, t1, t4, t2, t4, t3, t1, t2, t3, t4))
    # Flatten arrays:
    I = I.flatten()
    J = J.flatten()
    localA = localA.flatten()/6.0
    # Construct sparse matrix:
    A = sparse.csc_matrix((localA, (I, J)))

    if not lump:
        # create b matrix data (account for that vol is 6 times tet volume)
        Bii = vol / 60.0
        Bij = vol / 120.0
        localB = np.column_stack((Bij, Bij, Bij, Bij, Bij, Bij, Bij, Bij, Bij, Bij, Bij, Bij, Bii, Bii, Bii, Bii))
        localB = localB.flatten()
        B = sparse.csc_matrix((localB, (I, J)))
    else:
        # when lumping put all onto diagonal (volume/4 for each vertex)
        Bii = vol / 24.0
        localB = np.column_stack((Bii, Bii, Bii, Bii))
        I = np.column_stack((t1, t2, t3, t4))
        I = I.flatten()
        localB = localB.flatten()
        B = sparse.csc_matrix((localB, (I, I)))

    return A, B

# ------------------------------------------------------------------------------
# main function

# main function
if __name__=="__main__":

    # Command Line options and error checking done here
    options = options_parse()

    if options.asegid is not None:
        surf = get_aseg_surf(options.sdir,options.sid,options.asegid,options.outsurf)
        outsurf = surf
    elif options.hsfid is not None:
        surf = get_hsf_surf(options.sdir,options.sid,options.hsfid,options.outsurf)
        outsurf = surf
    elif options.label is not None:
        surf = get_label_surf(options.sdir,options.sid,options.label,options.surf,options.source,options.outsurf)
        outsurf = surf
    elif options.aparcid is not None:
        surf = get_aparc_surf(options.sdir,options.sid,options.surf,options.aparcid,options.outsurf)
        outsurf = surf
    elif options.surf is not None:
        surf = get_surf_surf(options.sdir,options.sid,options.surf)
        outsurf = options.outsurf

    if surf is None:
        my_print('ERROR: no surface was created/selected?')
        sys.exit(1)

    if options.dotet:
        # convert to tetmesh
        get_tetmesh(surf,options.outtet,options.fixiter)
        # run shapedna tetra
        run_shapeDNAtetra(options.outtet,options.outev,options)
    else:
        # run shapedna tria
        run_shapeDNAtria(surf,options.outev,outsurf,options)

    # always exit with 0 exit code
    sys.exit(0)
