# fsqc toolbox

## Description

This package provides quality assurance / quality control scripts for FastSurfer- or
FreeSurfer-processed structural MRI data.

It is a revision, extension, and translation to the Python language of the
[Freesurfer QA Tools](https://surfer.nmr.mgh.harvard.edu/fswiki/QATools). It has
been augmented by additional functions from the [MRIQC toolbox](https://github.com/poldracklab/mriqc),
and with code derived from the [LaPy](https://github.com/Deep-MI/lapy) and
[BrainPrint](https://github.com/Deep-MI/brainprint) toolboxes.
___

## Contents

- [Functionality](#functionality)
- [Development](#development)
  - [News](#news)
  - [Main and development branches](#main-and-development-branches)
  - [Roadmap](#roadmap)
- [Usage](#usage)
  - [As a command line tool](#as-a-command-line-tool)
  - [As a Python package](#as-a-python-package)
  - [As a Docker image](#as-a-docker-image)
- [Installation](#installation)
   - [Installation as a Python package](#installation-as-a-python-package)
   - [Installation from GitHub](#installation-from-github)
   - [Download from GitHub](#download-from-github)
- [Requirements](#requirements)
- [Known issues](#known-issues)
- [Authors](#authors)
- [Citations](#citations)
- [License](#license)

___

## Functionality

The core functionality of this toolbox is to compute the following features:

variable       |   description
---------------|----------------------------------------------------------------
subject        |   subject ID
wm_snr_orig    |   signal-to-noise ratio for white matter in orig.mgz
gm_snr_orig    |   signal-to-noise ratio for gray matter in orig.mgz
wm_snr_norm    |   signal-to-noise ratio for white matter in norm.mgz
gm_snr_norm    |   signal-to-noise ratio for gray matter in norm.mgz
cc_size        |   relative size of the corpus callosum
lh_holes       |   number of holes in the left hemisphere
rh_holes       |   number of holes in the right hemisphere
lh_defects     |   number of defects in the left hemisphere
rh_defects     |   number of defects in the right hemisphere
topo_lh        |   topological fixing time for the left hemisphere
topo_rh        |   topological fixing time for the right hemisphere
con_lh_snr     |   wm/gm contrast signal-to-noise ratio in the left hemisphere
con_rh_snr     |   wm/gm contrast signal-to-noise ratio in the right hemisphere
rot_tal_x      |   rotation component of the Talairach transform around the x axis
rot_tal_y      |   rotation component of the Talairach transform around the y axis
rot_tal_z      |   rotation component of the Talairach transform around the z axis

The program will use an existing output directory (or try to create it) and
write a csv table into that location. The csv table will contain the above
metrics plus a subject identifier.

The program can also be run on images that were processed with [FastSurfer](https://github.com/Deep-MI/FastSurfer)
(v1.1 or later) instead of FreeSurfer. In that case, simply add a `--fastsurfer`
switch to your shell command. Note that FastSurfer's full processing stream must
have been run, including surface reconstruction (i.e. brain segmentation alone
is not sufficient).

In addition to the core functionality of the toolbox there are several optional
modules that can be run according to need:

- screenshots module

This module allows for the automated generation of cross-sections of the brain
that are overlaid with the anatomical segmentations (asegs) and the white and
pial surfaces. These images will be saved to the 'screenshots' subdirectory
that will be created within the output directory. These images can be used for
quickly glimpsing through the processing results. Note that no display manager
is required for this module, i.e. it can be run on a remote server, for example.

- surfaces module

This module allows for the automated generation of surface renderings of the
left and right pial and inflated surfaces, overlaid with the aparc annotation.
These images will be saved to the 'surfaces' subdirectory that will be created
within the output directory. These images can be used for quickly glimpsing
through the processing results. Note that no display manager is required for
this module, i.e. it can be run on a remote server, for example.

- skullstrip module

This module allows for the automated generation cross-sections of the brain
that are overlaid with the colored and semi-transparent brainmask. This allows
to check the quality of the skullstripping in FreeSurfer. The resulting images
will be saved to the 'skullstrip' subdirectory that will be created within the
output directory.

- fornix module

This is a module to assess potential issues with the segmentation of the
corpus callosum, which may incorrectly include parts of the fornix. To assess
segmentation quality, a screenshot of the contours of the corpus callosum
segmentation overlaid on the norm.mgz will be saved as 'cc.png' for each
subject within the 'fornix' subdirectory of the output directory.

- modules for the amygdala, hippocampus, and hypothalamus

These modules evaluate potential missegmentations of the amygdala, hippocampus,
and hypothalamus. To assess segmentation quality, screenshots will be created
These modules require prior processing of the MR images with FreeSurfer's
dedicated toolboxes for the segmentation of the amygdala and hippocampus, and
the hypothalamus, respectively.

- shape module

The shape module will run a shapeDNA / brainprint analysis to compute distances
of shape descriptors between lateralized brain structures. This can be used
to identify discrepancies and irregularities between pairs of corresponding
structures. The results will be included in the main csv table, and the output
directory will also contain a 'brainprint' subdirectory.

- outlier module

This is a module to detect extreme values among the subcortical ('aseg')
segmentations as well as the cortical parcellations. If present, hypothalamic
and hippocampal subsegmentations will also be included.

The outlier detection is based on comparisons with the
distributions of the sample as well as normative values taken from the
literature (see References).

For comparisons with the sample distributions, extreme values are defined in
two ways: nonparametrically, i.e. values that are 1.5 times the interquartile
range below or above the 25th or 75th percentile of the sample, respectively,
and parametrically, i.e. values that are more than 2 standard deviations above
or below the sample mean. Note that a minimum of 10 supplied subjects is
required for running these analyses, otherwise `NaNs` will be returned.

For comparisons with the normative values, lower and upper bounds are computed
from the 95% prediction intervals of the regression models given in Potvin et
al., 1996, and values exceeding these bounds will be flagged. As an
alternative, users may specify their own normative values by using the
'--outlier-table' argument. This requires a custom csv table with headers
`label`, `upper`, and `lower`, where `label` indicates a column of anatomical
names. It can be a subset and the order is arbitrary, but naming must exactly
match the nomenclature of the 'aseg.stats' and/or '[lr]h.aparc.stats' file.
If cortical parcellations are included in the outlier table for a comparison
with aparc.stats values, the labels must have a 'lh.' or 'rh.' prefix. file.
`upper` and `lower` are user-specified upper and lower bounds.

The main csv table will be appended with the following summary variables, and
more detailed output about will be saved as csv tables in the 'outliers'
subdirectory of the main output directory.

variable                 |   description
-------------------------|---------------------------------------------------
n_outliers_sample_nonpar | number of structures that are 1.5 times the IQR above/below the 75th/25th percentile
n_outliers_sample_param  | number of structures that are 2 SD above/below the mean
n_outliers_norms         | number of structures exceeding the upper and lower bounds of the normative values

___


## Development

### Current status

We are happy to announce the release of version 2.0 of the fsqc toolbox. With
this release comes a change of the project name from `qatools` to `fsqc`, to
reflect increased independence from the original FreeSurfer QA tools, and
applicability to other neuroimaging analysis packages - such as [Fastsurfer](https://github.com/Deep-MI/FastSurfer).

Recent changes include the addition of the hippocampus and hypothalamus modules 
as well as the addition of surface and skullstrip visualization modules. 
Technical changes include how the package is installed, imported, and run, see 
[below](https://github.com/Deep-MI/fsqc#usage) for details.

A list of changes is available [here](CHANGES.md).

### Main and development branches

This repository contains multiple branches, reflecting the ongoing
development of the toolbox. The two primary branches are the main branch
(`stable`) and the development branch (`dev`). New features will first be added
to the development branch, and eventually be merged with the main branch. You
are currently on the main branch. To go to the development branch, select it
from the drop-down menu on the top left, or [click here](https://github.com/Deep-MI/fsqc/tree/dev).

### Roadmap

The goal of the `fsqc` project is to create a modular and extensible software
package that provides quantitative metrics and visual information for the
quality control of FreeSurfer- or Fastsurfer-processed MR images. The package
is currently under development, and new features are continuously added.

New features will initially be available in the [development branch](https://github.com/Deep-MI/fsqc/tree/dev)
of this toolbox and will be included in the [main branch](https://github.com/Deep-MI/fsqc/tree/stable)
after a period of testing and evaluation. Unless explicitly announced, all new
features will preserve compatibility with earlier versions.

Feedback, suggestions, and [contributions](CONTRIBUTINNG.md) are always welcome,
preferably via [issues](https://github.com/Deep-MI/fsqc/issues) and [pull requests](https://github.com/Deep-MI/fsqc/pulls).

___

## Usage

### As a command line tool

```
run_fsqc --subjects_dir <directory> --output_dir <directory>
    [--subjects SubjectID [SubjectID ...]]
    [--subjects-file <file>] [--screenshots]
    [--screenshots-html] [--surfaces] [--surfaces-html]
    [--skullstrip] [--skullstrip-html]
    [--fornix] [--fornix-html] [--hippocampus]
    [--hippocampus-html] [--hippocampus-label ... ]
    [--hypothalamus] [--hypothalamus-html] [--shape]
    [--outlier] [--fastsurfer] [-h] [--more-help]
    [...]


required arguments:
  --subjects_dir <directory>
                         subjects directory with a set of Freesurfer- or
                         Fastsurfer-processed individual datasets.
  --output_dir <directory>
                         output directory

optional arguments:
  --subjects SubjectID [SubjectID ...]
                         list of subject IDs
  --subjects-file <file> filename of a file with subject IDs (one per line)
  --screenshots          create screenshots of individual brains
  --screenshots-html     create screenshots of individual brains incl.
                         html summary page
  --surfaces             create screenshots of individual brain surfaces
  --surfaces-html        create screenshots of individual brain surfaces
                         and html summary page
  --skullstrip           create screenshots of individual brainmasks
  --skullstrip-html      create screenshots of individual brainmasks and
                         html summary page
  --fornix               check fornix segmentation
  --fornix-html          check fornix segmentation and create html summary
                         page of fornix evaluation
  --hypothalamus         check hypothalamic segmentation
  --hypothalamus-html    check hypothalamic segmentation and create html
                         summary page
  --hippocampus          check segmentation of hippocampus and amygdala
  --hippocampus-html     check segmentation of hippocampus and amygdala
                         and create html summary page
  --hippocampus-label    specify label for hippocampus segmentation files
                         (default: T1.v21). The full filename is then
                         [lr]h.hippoAmygLabels-<LABEL>.FSvoxelSpace.mgz
  --shape                run shape analysis
  --outlier              run outlier detection
  --outlier-table        specify normative values (only in conjunction with
                         --outlier)
  --fastsurfer           use FastSurfer instead of FreeSurfer output
  --exit-on-error        terminate the program when encountering an error;
                         otherwise, try to continue with the next module or
                         case

getting help:
  -h, --help            display this help message and exit
  --more-help           display extensive help message and exit

expert options:
  --screenshots_base <image>
                        filename of an image that should be used instead of
                        norm.mgz as the base image for the screenshots. Can be
                        an individual file (which would not be appropriate for
                        multi-subject analysis) or can be a file without
                        pathname and with the same filename across subjects
                        within the 'mri' subdirectory of an individual
                        FreeSurfer results directory (which would be appropriate
                        for multi-subject analysis).
  --screenshots_overlay <image>
                        path to an image that should be used instead of aseg.mgz
                        as the overlay image for the screenshots; can also be
                        none. Can be an individual file (which would not be
                        appropriate for multi-subject analysis) or can be a file
                        without pathname and with the same filename across
                        subjects within the 'mri' subdirectory of an individual
                        FreeSurfer results directory (which would be appropriate
                        for multi-subject analysis).
  --screenshots_surf <surf> [<surf> ...]
                        one or more surface files that should be used instead
                        of [lr]h.white and [lr]h.pial; can also be none. Can be
                        one or more individual file(s) (which would not be
                        appropriate for multi-subject analysis) or can be a
                        (list of) file(s) without pathname and with the same
                        filename across subjects within the 'surf' subdirectory
                        of an individual FreeSurfer results directory (which
                        would be appropriate for multi-subject analysis).
  --screenshots_views <view> [<view> ...]
                        one or more views to use for the screenshots in the form
                        of x=<numeric> y=<numeric> and/or z=<numeric>. Order
                        does not matter. Default views are x=-10 x=10 y=0 z=0.
  --screenshots_layout <rows> <columns>
                        layout matrix for screenshot images.

```

*Examples:*

- Run the QC pipeline for all subjects found in `/my/subjects/directory`:

```bash
run_fsqc --subjects_dir /my/subjects/directory --output_dir /my/output/directory
```

- Run the QC pipeline for two specific subjects that need to be present in `/my/subjects/directory`:

```bash
run_fsqc --subjects_dir /my/subjects/directory --output_dir /my/output/directory --subjects mySubjectID1 mySubjectID2
```

- Run the QC pipeline for all subjects found in `/my/subjects/directory` after full FastSurfer processing:

```bash
run_fsqc --subjects_dir /my/subjects/directory --output_dir /my/output/directory --fastsurfer
```

- Run the QC pipeline plus the screenshots module for all subjects found in `/my/subjects/directory`:

```bash
run_fsqc --subjects_dir /my/subjects/directory --output_dir /my/output/directory --screenshots
```

- Run the QC pipeline plus the fornix pipeline for all subjects found in `/my/subjects/directory`:

```bash
run_fsqc --subjects_dir /my/subjects/directory --output_dir /my/output/directory --fornix
```

- Run the QC pipeline plus the shape analysis pipeline for all subjects found in `/my/subjects/directory`:

```bash
run_fsqc --subjects_dir /my/subjects/directory --output_dir /my/output/directory --shape
```

- Run the QC pipeline plus the outlier detection module for all subjects found in `/my/subjects/directory`:

```bash
run_fsqc --subjects_dir /my/subjects/directory --output_dir /my/output/directory --outlier
```

- Run the QC pipeline plus the outlier detection module with a user-specific table of normative values for all subjects found in `/my/subjects/directory`:

```bash
run_fsqc --subjects_dir /my/subjects/directory --output_dir /my/output/directory --outlier --outlier-table /my/table/with/normative/values.csv
```

- Note that the `--screenshots`, `--fornix`, `--shape`, and `--outlier` (and other) arguments can also be used in conjunction.

### As a Python package

As an alternative to their command-line usage, the fsqc scripts can also be run
within a pure Python environment, i.e. installed and imported as a Python package.

Use `import fsqc` (or sth. equivalent) to import the package within a
Python environment, and use the `run_fsqc` function from the `fsqc` module to
run an analysis.

In its most basic form:

```python
import fsqc
fsqc.run_fsqc(subjects_dir='/my/subjects/dir', output_dir='/my/output/dir')
```

Specify subjects as a list:

```python
import fsqc
fsqc.run_fsqc(subjects_dir='/my/subjects/dir', output_dir='/my/output/dir', subjects=['subject1', 'subject2', 'subject3'])
```

And as a more elaborate example:

```python
import fsqc
fsqc.run_fsqc(subjects_dir='/my/subjects/dir', output_dir='/my/output/dir', subject_file='/my/subjects/file.txt', screenshots_html=True, surfaces_html=True, skullstrip_html=True, fornix_html=True, hypothalamus_html=True, hippocampus_html=True, hippocampus_label="T1.v21", shape=True, outlier=True)
```


Call `help(fsqc.run_fsqc)` for further usage info and additional options.

### As a Docker image

We provide a configuration files that can be used to create a Docker or
Singularity image for the fsqc scripts. Documentation can be found on the
[Docker](docker/Docker.md) and [Singularity](singularity/Singularity.md) pages.

___

## Installation

### Installation as a Python package

Use:

```bash
pip install fsqc
```

to install the fsqc package and all of its dependencies. This is the recommended
way of installing the package, and allows for both command-line execution and
execution as a Python function. We also recommend to do this installation within
a Python virtual environment, which can be created and activated as follows:

```bash
virtualenv /path/to/my/virtual/environment
source /path/to/my/virtual/environment/bin/activate
```

### Installation from GitHub

Use the following code to download, build and install the fsqc package from its
GitHub repository into your local Python package directory:

```bash
pip install git+https://github.com/deep-mi/fsqc.git
```

This can be useful if you want to install a particular branch - such as the `dev`
branch in the following example:

```bash
pip install git+https://github.com/deep-mi/fsqc.git@dev
```

### Download from GitHub

This software can also be downloaded from its GitHub repository at `https://github.com/Deep-MI/fsqc`,
or cloned directly via `git clone https://github.com/Deep-MI/fsqc`.

The `run_fsqc` script will then be executable from the command line, as
detailed above. Note, however, that the required dependencies will have to be
installed manually. See the [requirements](#requirements) section for
instructions.


___

## Requirements

- At least one structural MR image that was processed with Freesurfer 6.0, 7.x,
  or FastSurfer 1.1 or later (including the surface pipeline).

- A Python version >= 3.8 is required to run this script.

- Required packages include (among others) the nibabel and skimage package for
  the core functionality, plus the matplotlib, pandas, and transform3d
  packages for some optional functions and modules. See the `requirements.txt`
  file for a complete list. Use `pip install -r requirements.txt` to install
  these packages.

- If installing the toolbox as a Python package or if using the Docker image,
  all required packages will be installed automatically and manual installation
  as detailed above will not be necessary.

- This software has been tested on Ubuntu 20.04.

- A working [FreeSurfer](https://freesurfer.net) installation (version 6 or
  newer) is required for running the 'shape' module of this toolbox. Also make
  sure that FreeSurfer is sourced (i.e., `FREESURFER_HOME` is set as an
  environment variable) before running an analysis.

___

## Known issues

- Aborted / restarted recon-all runs: the program will analyze recon-all
  logfiles, and may fail or return erroneous results if the logfile is
  appended by multiple restarts of recon-all runs. Ideally, the logfile should
  therefore consist of just a single, successful recon-all run.

___

## Authors

- fsqc toolbox: Kersten Diers, Tobias Wolff, and Martin Reuter.
- Freesurfer QA Tools: David Koh, Stephanie Lee, Jenni Pacheco, Vasanth Pappu,
  and Louis Vinke.
- lapy and brainprint toolboxes: Martin Reuter.

___

## Citations

- Esteban O, Birman D, Schaer M, Koyejo OO, Poldrack RA, Gorgolewski KJ; 2017;
  MRIQC: Advancing the Automatic Prediction of Image Quality in MRI from Unseen
  Sites; PLOS ONE 12(9):e0184661; doi:10.1371/journal.pone.0184661.

- Wachinger C, Golland P, Kremen W, Fischl B, Reuter M; 2015; BrainPrint: a
  Discriminative Characterization of Brain Morphology; Neuroimage: 109, 232-248;
  doi:10.1016/j.neuroimage.2015.01.032.

- Reuter M, Wolter FE, Shenton M, Niethammer M; 2009; Laplace-Beltrami
  Eigenvalues and Topological Features of Eigenfunctions for Statistical Shape
  Analysis; Computer-Aided Design: 41, 739-755; doi:10.1016/j.cad.2009.02.007.

- Potvin O, Mouiha A, Dieumegarde L, Duchesne S, & Alzheimer's Disease
  Neuroimaging Initiative; 2016; Normative data for subcortical regional volumes
  over the lifetime of the adult human brain; Neuroimage: 137, 9-20; doi.org/10.1016/j.neuroimage.2016.05.016

___

## License

This software is licensed under the MIT License, see associated LICENSE file
for details.

Copyright (c) 2019 Image Analysis Group, DZNE e.V.
