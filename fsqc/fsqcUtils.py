"""
This module provides various import/export functions as well as the
'levelsetsTria' function

"""

# ------------------------------------------------------------------------------


def importMGH(filename):
    """
    A function to read Freesurfer MGH files.

    Required arguments:
        - filename

    Returns:
        - vol

    Requires valid mgh file. If not found, NaNs will be returned.

    """

    import logging
    import os
    import struct
    import warnings

    import numpy

    logging.captureWarnings(True)

    if not os.path.exists(filename):
        warnings.warn("WARNING: could not find " + filename + ", returning NaNs")
        return numpy.nan

    fp = open(filename, "rb")
    intsize = struct.calcsize(">i")
    shortsize = struct.calcsize(">h")
    floatsize = struct.calcsize(">f")
    charsize = struct.calcsize(">b")

    v = struct.unpack(">i", fp.read(intsize))[0]
    ndim1 = struct.unpack(">i", fp.read(intsize))[0]
    ndim2 = struct.unpack(">i", fp.read(intsize))[0]
    ndim3 = struct.unpack(">i", fp.read(intsize))[0]
    nframes = struct.unpack(">i", fp.read(intsize))[0]
    vtype = struct.unpack(">i", fp.read(intsize))[0]
    dof = struct.unpack(">i", fp.read(intsize))[0]

    UNUSED_SPACE_SIZE = 256
    USED_SPACE_SIZE = (3 * 4) + (4 * 3 * 4)  # space for ras transform
    unused_space_size = UNUSED_SPACE_SIZE - 2

    ras_good_flag = struct.unpack(">h", fp.read(shortsize))[0]
    if ras_good_flag:
        # We read these in but don't process them
        # as we just want to move to the volume data
        delta = struct.unpack(">fff", fp.read(floatsize * 3))
        Mdc = struct.unpack(">fffffffff", fp.read(floatsize * 9))
        Pxyz_c = struct.unpack(">fff", fp.read(floatsize * 3))

    unused_space_size = unused_space_size - USED_SPACE_SIZE

    for i in range(unused_space_size):
        struct.unpack(">b", fp.read(charsize))[0]

    nv = ndim1 * ndim2 * ndim3 * nframes
    vol = numpy.frombuffer(fp.read(floatsize * nv), dtype=numpy.float32).byteswap()

    nvert = max([ndim1, ndim2, ndim3])
    vol = numpy.reshape(vol, (ndim1, ndim2, ndim3, nframes), order="F")
    vol = numpy.squeeze(vol)
    fp.close()

    return vol


# ------------------------------------------------------------------------------


def binarizeImage(img_file, out_file, match=None):
    import nibabel as nb
    import numpy as np

    # get image
    img = nb.load(img_file)
    img_data = img.get_fdata()

    # binarize
    if match is None:
        img_data_bin = img_data != 0.0
    else:
        img_data_bin = np.isin(img_data, match)

    # write output
    img_bin = nb.nifti1.Nifti1Image(img_data_bin.astype(int), img.affine, dtype="uint8")
    nb.save(img_bin, out_file)


# ------------------------------------------------------------------------------


def applyTransform(img_file, out_file, mat_file, interp):
    import os

    import nibabel as nb
    import numpy as np
    from scipy import ndimage

    # get image
    img = nb.load(img_file)
    img_data = img.get_fdata()

    #
    _, mat_file_ext = os.path.splitext(mat_file)

    # get matrix
    if mat_file_ext == ".xfm":
        raise Exception("ERROR: xfm matrices not (yet) supported. Please convert to lta format")
    elif mat_file_ext == ".lta":
        # get lta matrix
        lta = readLTA(mat_file)
        # get vox2vox transform
        if lta["type"] == 1:
            # compute vox2vox from ras2ras as vox2ras2ras2vox transform:
            # vox2ras from input image (source)
            # ras2ras from make_upright.lta
            # ras2vox from upright image (target)
            # m = np.matmul(np.linalg.inv(upr.affine), np.matmul(lta['lta'], img.affine))
            raise Exception("ERROR: lta type 1 (ras2ras) not supported yet")
        elif lta["type"] == 0:
            # vox2vox transform
            m = lta["lta"]
    else:
        raise Exception("ERROR: matrices must be either xfm or lta format")

    # apply transform
    if interp == "nearest":
        img_data_interp = ndimage.affine_transform(img_data, np.linalg.inv(m), order=0)
    elif interp == "cubic":
        img_data_interp = ndimage.affine_transform(img_data, np.linalg.inv(m), order=3)
    else:
        raise Exception("ERROR: interpolation must be either nearest or cubic")

    # write image
    img_interp = nb.nifti1.Nifti1Image(img_data_interp, img.affine)
    nb.save(img_interp, out_file)


# ------------------------------------------------------------------------------


def readLTA(file):
    import re

    import numpy as np

    with open(file, "r") as f:
        lta = f.readlines()
    d = dict()
    i = 0
    while i < len(lta):
        if re.match("type", lta[i]) is not None:
            d["type"] = int(re.sub("=", "", re.sub("[a-z]+", "", re.sub("#.*", "", lta[i]))).strip())
            i += 1
        elif re.match("nxforms", lta[i]) is not None:
            d["nxforms"] = int(re.sub("=", "", re.sub("[a-z]+", "", re.sub("#.*", "", lta[i]))).strip())
            i += 1
        elif re.match("mean", lta[i]) is not None:
            d["mean"] = [
                float(x)
                for x in re.split(" +", re.sub("=", "", re.sub("[a-z]+", "", re.sub("#.*", "", lta[i]))).strip())
            ]
            i += 1
        elif re.match("sigma", lta[i]) is not None:
            d["sigma"] = float(re.sub("=", "", re.sub("[a-z]+", "", re.sub("#.*", "", lta[i]))).strip())
            i += 1
        elif re.match("-*[0-9]\.\S+\W+-*[0-9]\.\S+\W+-*[0-9]\.\S+\W+-*[0-9]\.\S+\W+", lta[i]) is not None:
            d["lta"] = np.array(
                [
                    [
                        float(x)
                        for x in re.split(
                            " +",
                            re.match(
                                "-*[0-9]\.\S+\W+-*[0-9]\.\S+\W+-*[0-9]\.\S+\W+-*[0-9]\.\S+\W+", lta[i]
                            ).string.strip(),
                        )
                    ],
                    [
                        float(x)
                        for x in re.split(
                            " +",
                            re.match(
                                "-*[0-9]\.\S+\W+-*[0-9]\.\S+\W+-*[0-9]\.\S+\W+-*[0-9]\.\S+\W+", lta[i + 1]
                            ).string.strip(),
                        )
                    ],
                    [
                        float(x)
                        for x in re.split(
                            " +",
                            re.match(
                                "-*[0-9]\.\S+\W+-*[0-9]\.\S+\W+-*[0-9]\.\S+\W+-*[0-9]\.\S+\W+", lta[i + 2]
                            ).string.strip(),
                        )
                    ],
                    [
                        float(x)
                        for x in re.split(
                            " +",
                            re.match(
                                "-*[0-9]\.\S+\W+-*[0-9]\.\S+\W+-*[0-9]\.\S+\W+-*[0-9]\.\S+\W+", lta[i + 3]
                            ).string.strip(),
                        )
                    ],
                ]
            )
            i += 4
        elif re.match("src volume info", lta[i]) is not None:
            while i < len(lta) and re.match("dst volume info", lta[i]) is None:
                if re.match("valid", lta[i]) is not None:
                    d["src_valid"] = int(re.sub(".*=", "", re.sub("#.*", "", lta[i])).strip())
                elif re.match("filename", lta[i]) is not None:
                    d["src_filename"] = re.split(" +", re.sub(".*=", "", re.sub("#.*", "", lta[i])).strip())
                elif re.match("volume", lta[i]) is not None:
                    d["src_volume"] = [
                        int(x) for x in re.split(" +", re.sub(".*=", "", re.sub("#.*", "", lta[i])).strip())
                    ]
                elif re.match("voxelsize", lta[i]) is not None:
                    d["src_voxelsize"] = [
                        float(x) for x in re.split(" +", re.sub(".*=", "", re.sub("#.*", "", lta[i])).strip())
                    ]
                elif re.match("xras", lta[i]) is not None:
                    d["src_xras"] = [
                        float(x) for x in re.split(" +", re.sub(".*=", "", re.sub("#.*", "", lta[i])).strip())
                    ]
                elif re.match("yras", lta[i]) is not None:
                    d["src_yras"] = [
                        float(x) for x in re.split(" +", re.sub(".*=", "", re.sub("#.*", "", lta[i])).strip())
                    ]
                elif re.match("zras", lta[i]) is not None:
                    d["src_zras"] = [
                        float(x) for x in re.split(" +", re.sub(".*=", "", re.sub("#.*", "", lta[i])).strip())
                    ]
                elif re.match("cras", lta[i]) is not None:
                    d["src_cras"] = [
                        float(x) for x in re.split(" +", re.sub(".*=", "", re.sub("#.*", "", lta[i])).strip())
                    ]
                i += 1
        elif re.match("dst volume info", lta[i]) is not None:
            while i < len(lta) and re.match("src volume info", lta[i]) is None:
                if re.match("valid", lta[i]) is not None:
                    d["dst_valid"] = int(re.sub(".*=", "", re.sub("#.*", "", lta[i])).strip())
                elif re.match("filename", lta[i]) is not None:
                    d["dst_filename"] = re.split(" +", re.sub(".*=", "", re.sub("#.*", "", lta[i])).strip())
                elif re.match("volume", lta[i]) is not None:
                    d["dst_volume"] = [
                        int(x) for x in re.split(" +", re.sub(".*=", "", re.sub("#.*", "", lta[i])).strip())
                    ]
                elif re.match("voxelsize", lta[i]) is not None:
                    d["dst_voxelsize"] = [
                        float(x) for x in re.split(" +", re.sub(".*=", "", re.sub("#.*", "", lta[i])).strip())
                    ]
                elif re.match("xras", lta[i]) is not None:
                    d["dst_xras"] = [
                        float(x) for x in re.split(" +", re.sub(".*=", "", re.sub("#.*", "", lta[i])).strip())
                    ]
                elif re.match("yras", lta[i]) is not None:
                    d["dst_yras"] = [
                        float(x) for x in re.split(" +", re.sub(".*=", "", re.sub("#.*", "", lta[i])).strip())
                    ]
                elif re.match("zras", lta[i]) is not None:
                    d["dst_zras"] = [
                        float(x) for x in re.split(" +", re.sub(".*=", "", re.sub("#.*", "", lta[i])).strip())
                    ]
                elif re.match("cras", lta[i]) is not None:
                    d["dst_cras"] = [
                        float(x) for x in re.split(" +", re.sub(".*=", "", re.sub("#.*", "", lta[i])).strip())
                    ]
                i += 1
        else:
            i += 1
    # create full transformation matrices
    d["src"] = np.concatenate(
        (
            np.concatenate(
                (np.c_[d["src_xras"]], np.c_[d["src_yras"]], np.c_[d["src_zras"]], np.c_[d["src_cras"]]), axis=1
            ),
            np.array([0.0, 0.0, 0.0, 1.0], ndmin=2),
        ),
        axis=0,
    )
    d["dst"] = np.concatenate(
        (
            np.concatenate(
                (np.c_[d["dst_xras"]], np.c_[d["dst_yras"]], np.c_[d["dst_zras"]], np.c_[d["dst_cras"]]), axis=1
            ),
            np.array([0.0, 0.0, 0.0, 1.0], ndmin=2),
        ),
        axis=0,
    )
    # return
    return d


# ------------------------------------------------------------------------------


def levelsetsTria(v, t, p, levelsets):
    """
    This is the levelsetsTria function

    """

    import numpy as np
    from scipy.sparse import lil_matrix

    vLVL = list()
    lLVL = list()
    iLVL = list()

    levelsets = np.array(levelsets, ndmin=2)

    for lidx in range(len(levelsets)):
        A = lil_matrix((np.shape(v)[0], np.shape(v)[0]))

        lvl = levelsets[lidx]

        nlvl = p[t] > lvl

        n = np.where(np.logical_or(np.sum(nlvl, axis=1) == 1, np.sum(nlvl, axis=1) == 2))[0]

        # interpolate points

        ti = list()
        vi = list()

        for i in range(len(n)):
            # which are the outlying points in the current tria?
            oi = np.where(nlvl[n[i], :])[0]

            #  convert 2 --> 1
            if len(oi) == 2:
                oi = np.setdiff1d((0, 1, 2), oi)

            # find the two non - outyling points
            oix = np.setdiff1d((0, 1, 2), oi)

            # check if we have interpolated for one or both of these points before
            if np.count_nonzero(A[t[n[i], oi.item()], t[n[i], oix[0]]]) == 0:
                # compute difference vectors between outlying point and other points

                d10 = v[t[n[i], oix[0]], :] - v[t[n[i], oi], :]

                # compute differences of all points to lvl to get interpolation factors

                s10 = (lvl - p[t[n[i], oi]]) / (p[t[n[i], oix[0]]] - p[t[n[i], oi]])

                # compute new points

                v10 = s10 * d10 + v[t[n[i], oi], :]

                # update vi and index(order matters)

                vi.append(v10.tolist()[0])

                ti10 = len(vi)

                # store between which two points we are interpolating (to avoid having duplicate points)

                A[t[n[i], oi.item()], t[n[i], oix[0]]] = ti10
                A[t[n[i], oix[0]], t[n[i], oi.item()]] = ti10

            else:
                ti10 = int(A[t[n[i], oi.item()], t[n[i], oix[0]]])

            # essentially the same as above, just for oix[1]

            if np.count_nonzero(A[t[n[i], oi.item()], t[n[i], oix[1]]]) == 0:
                d20 = v[t[n[i], oix[1]], :] - v[t[n[i], oi], :]

                s20 = (lvl - p[t[n[i], oi]]) / (p[t[n[i], oix[1]]] - p[t[n[i], oi]])

                v20 = s20 * d20 + v[t[n[i], oi], :]

                # update vi and index(order matters)

                vi.append(v20.tolist()[0])

                ti20 = len(vi)

                A[t[n[i], oi.item()], t[n[i], oix[1]]] = ti20
                A[t[n[i], oix[1]], t[n[i], oi.item()]] = ti20

            else:
                ti20 = int(A[t[n[i], oi.item()], t[n[i], oix[1]]])

            # store new indices

            ti.append((ti10, ti20))

            # clean up

            # clear oi oix d10 d20 s10 s20 v10 v20 t10 t20

        # store

        vLVL.append(vi)
        lLVL.append(ti)
        iLVL.append(n)

    return vLVL, lLVL, iLVL

# ------------------------------------------------------------------------------

def returnFreeSurferColorLUT():
    """
    Provides FreeSurfer color look-up table
    """

    import numpy as np

    return np.array((
        [0,"Unknown",0,0,0,0],
        [1,"Left-Cerebral-Exterior",70,130,180,0],
        [2,"Left-Cerebral-White-Matter",245,245,245,0],
        [3,"Left-Cerebral-Cortex",205,62,78,0],
        [4,"Left-Lateral-Ventricle",120,18,134,0],
        [5,"Left-Inf-Lat-Vent",196,58,250,0],
        [6,"Left-Cerebellum-Exterior",0,148,0,0],
        [7,"Left-Cerebellum-White-Matter",220,248,164,0],
        [8,"Left-Cerebellum-Cortex",230,148,34,0],
        [9,"Left-Thalamus-unused",0,118,14,0],
        [10,"Left-Thalamus",0,118,14,0],
        [11,"Left-Caudate",122,186,220,0],
        [12,"Left-Putamen",236,13,176,0],
        [13,"Left-Pallidum",12,48,255,0],
        [14,"3rd-Ventricle",204,182,142,0],
        [15,"4th-Ventricle",42,204,164,0],
        [16,"Brain-Stem",119,159,176,0],
        [17,"Left-Hippocampus",220,216,20,0],
        [18,"Left-Amygdala",103,255,255,0],
        [19,"Left-Insula",80,196,98,0],
        [20,"Left-Operculum",60,58,210,0],
        [21,"Line-1",60,58,210,0],
        [22,"Line-2",60,58,210,0],
        [23,"Line-3",60,58,210,0],
        [24,"CSF",60,60,60,0],
        [25,"Left-Lesion",255,165,0,0],
        [26,"Left-Accumbens-area",255,165,0,0],
        [27,"Left-Substancia-Nigra",0,255,127,0],
        [28,"Left-VentralDC",165,42,42,0],
        [29,"Left-undetermined",135,206,235,0],
        [30,"Left-vessel",160,32,240,0],
        [31,"Left-choroid-plexus",0,200,200,0],
        [32,"Left-F3orb",100,50,100,0],
        [33,"Left-lOg",135,50,74,0],
        [34,"Left-aOg",122,135,50,0],
        [35,"Left-mOg",51,50,135,0],
        [36,"Left-pOg",74,155,60,0],
        [37,"Left-Stellate",120,62,43,0],
        [38,"Left-Porg",74,155,60,0],
        [39,"Left-Aorg",122,135,50,0],
        [40,"Right-Cerebral-Exterior",70,130,180,0],
        [41,"Right-Cerebral-White-Matter",245,245,245,0],
        [42,"Right-Cerebral-Cortex",205,62,78,0],
        [43,"Right-Lateral-Ventricle",120,18,134,0],
        [44,"Right-Inf-Lat-Vent",196,58,250,0],
        [45,"Right-Cerebellum-Exterior",0,148,0,0],
        [46,"Right-Cerebellum-White-Matter",220,248,164,0],
        [47,"Right-Cerebellum-Cortex",230,148,34,0],
        [48,"Right-Thalamus-unused",0,118,14,0],
        [49,"Right-Thalamus",0,118,14,0],
        [50,"Right-Caudate",122,186,220,0],
        [51,"Right-Putamen",236,13,176,0],
        [52,"Right-Pallidum",13,48,255,0],
        [53,"Right-Hippocampus",220,216,20,0],
        [54,"Right-Amygdala",103,255,255,0],
        [55,"Right-Insula",80,196,98,0],
        [56,"Right-Operculum",60,58,210,0],
        [57,"Right-Lesion",255,165,0,0],
        [58,"Right-Accumbens-area",255,165,0,0],
        [59,"Right-Substancia-Nigra",0,255,127,0],
        [60,"Right-VentralDC",165,42,42,0],
        [61,"Right-undetermined",135,206,235,0],
        [62,"Right-vessel",160,32,240,0],
        [63,"Right-choroid-plexus",0,200,221,0],
        [64,"Right-F3orb",100,50,100,0],
        [65,"Right-lOg",135,50,74,0],
        [66,"Right-aOg",122,135,50,0],
        [67,"Right-mOg",51,50,135,0],
        [68,"Right-pOg",74,155,60,0],
        [69,"Right-Stellate",120,62,43,0],
        [70,"Right-Porg",74,155,60,0],
        [71,"Right-Aorg",122,135,50,0],
        [72,"5th-Ventricle",120,190,150,0],
        [73,"Left-Interior",122,135,50,0],
        [74,"Right-Interior",122,135,50,0],
        [77,"WM-hypointensities",200,70,255,0],
        [78,"Left-WM-hypointensities",255,148,10,0],
        [79,"Right-WM-hypointensities",255,148,10,0],
        [80,"non-WM-hypointensities",164,108,226,0],
        [81,"Left-non-WM-hypointensities",164,108,226,0],
        [82,"Right-non-WM-hypointensities",164,108,226,0],
        [83,"Left-F1",255,218,185,0],
        [84,"Right-F1",255,218,185,0],
        [85,"Optic-Chiasm",234,169,30,0],
        [192,"Corpus_Callosum",250,255,50,0],
        [86,"Left_future_WMSA",200,120,255,0],
        [87,"Right_future_WMSA",200,121,255,0],
        [88,"future_WMSA",200,122,255,0],
        [96,"Left-Amygdala-Anterior",205,10,125,0],
        [97,"Right-Amygdala-Anterior",205,10,125,0],
        [98,"Dura",160,32,240,0],
        [99,"Lesion",255,165,0,0],
        [100,"Left-wm-intensity-abnormality",124,140,178,0],
        [101,"Left-caudate-intensity-abnormality",125,140,178,0],
        [102,"Left-putamen-intensity-abnormality",126,140,178,0],
        [103,"Left-accumbens-intensity-abnormality",127,140,178,0],
        [104,"Left-pallidum-intensity-abnormality",124,141,178,0],
        [105,"Left-amygdala-intensity-abnormality",124,142,178,0],
        [106,"Left-hippocampus-intensity-abnormality",124,143,178,0],
        [107,"Left-thalamus-intensity-abnormality",124,144,178,0],
        [108,"Left-VDC-intensity-abnormality",124,140,179,0],
        [109,"Right-wm-intensity-abnormality",124,140,178,0],
        [110,"Right-caudate-intensity-abnormality",125,140,178,0],
        [111,"Right-putamen-intensity-abnormality",126,140,178,0],
        [112,"Right-accumbens-intensity-abnormality",127,140,178,0],
        [113,"Right-pallidum-intensity-abnormality",124,141,178,0],
        [114,"Right-amygdala-intensity-abnormality",124,142,178,0],
        [115,"Right-hippocampus-intensity-abnormality",124,143,178,0],
        [116,"Right-thalamus-intensity-abnormality",124,144,178,0],
        [117,"Right-VDC-intensity-abnormality",124,140,179,0],
        [118,"Epidermis",255,20,147,0],
        [119,"Conn-Tissue",205,179,139,0],
        [120,"SC-Fat-Muscle",238,238,209,0],
        [121,"Cranium",200,200,200,0],
        [122,"CSF-SA",74,255,74,0],
        [123,"Muscle",238,0,0,0],
        [124,"Ear",0,0,139,0],
        [125,"Adipose",173,255,47,0],
        [126,"Spinal-Cord",133,203,229,0],
        [127,"Soft-Tissue",26,237,57,0],
        [128,"Nerve",34,139,34,0],
        [129,"Bone",30,144,255,0],
        [130,"AirCavity",196,160,128,0],
        [131,"Orbital-Fat",238,59,59,0],
        [132,"Tongue",221,39,200,0],
        [133,"Nasal-Structures",238,174,238,0],
        [134,"Globe",255,0,0,0],
        [135,"Teeth",72,61,139,0],
        [136,"Left-Caudate-Putamen",21,39,132,0],
        [137,"Right-Caudate-Putamen",21,39,132,0],
        [138,"Left-Claustrum",65,135,20,0],
        [139,"Right-Claustrum",65,135,20,0],
        [140,"Cornea",134,4,160,0],
        [142,"Diploe",221,226,68,0],
        [143,"Vitreous-Humor",255,255,254,0],
        [144,"Lens",52,209,226,0],
        [145,"Aqueous-Humor",239,160,223,0],
        [146,"Outer-Table",70,130,180,0],
        [147,"Inner-Table",70,130,181,0],
        [148,"Periosteum",139,121,94,0],
        [149,"Endosteum",224,224,224,0],
        [150,"R-C-S",255,0,0,0],
        [151,"Iris",205,205,0,0],
        [152,"SC-Adipose-Muscle",238,238,209,0],
        [153,"SC-Tissue",139,121,94,0],
        [154,"Orbital-Adipose",238,59,59,0],
        [155,"Left-IntCapsule-Ant",238,59,59,0],
        [156,"Right-IntCapsule-Ant",238,59,59,0],
        [157,"Left-IntCapsule-Pos",62,10,205,0],
        [158,"Right-IntCapsule-Pos",62,10,205,0],
        [159,"Left-Cerebral-WM-unmyelinated",0,118,14,0],
        [160,"Right-Cerebral-WM-unmyelinated",0,118,14,0],
        [161,"Left-Cerebral-WM-myelinated",220,216,21,0],
        [162,"Right-Cerebral-WM-myelinated",220,216,21,0],
        [163,"Left-Subcortical-Gray-Matter",122,186,220,0],
        [164,"Right-Subcortical-Gray-Matter",122,186,220,0],
        [165,"Skull",120,120,120,0],
        [166,"Posterior-fossa",14,48,255,0],
        [167,"Scalp",166,42,42,0],
        [168,"Hematoma",121,18,134,0],
        [169,"Left-Basal-Ganglia",236,13,127,0],
        [176,"Right-Basal-Ganglia",236,13,126,0],
        [170,"brainstem",119,159,176,0],
        [171,"DCG",119,0,176,0],
        [172,"Vermis",119,100,176,0],
        [173,"Midbrain",242,104,76,0],
        [174,"Pons",206,195,58,0],
        [175,"Medulla",119,159,176,0],
        [177,"Vermis-White-Matter",119,50,176,0],
        [178,"SCP",142,182,0,0],
        [179,"Floculus",19,100,176,0],
        [180,"Left-Cortical-Dysplasia",73,61,139,0],
        [181,"Right-Cortical-Dysplasia",73,62,139,0],
        [182,"CblumNodulus",10,100,176,0],
        [193,"Left-hippocampal_fissure",0,196,255,0],
        [194,"Left-CADG-head",255,164,164,0],
        [195,"Left-subiculum",196,196,0,0],
        [196,"Left-fimbria",0,100,255,0],
        [197,"Right-hippocampal_fissure",128,196,164,0],
        [198,"Right-CADG-head",0,126,75,0],
        [199,"Right-subiculum",128,96,64,0],
        [200,"Right-fimbria",0,50,128,0],
        [201,"alveus",255,204,153,0],
        [202,"perforant_pathway",255,128,128,0],
        [203,"parasubiculum",175,175,75,0],
        [204,"presubiculum",64,0,64,0],
        [205,"subiculum",0,0,255,0],
        [206,"CA1",255,0,0,0],
        [207,"CA2",128,128,255,0],
        [208,"CA3",0,128,0,0],
        [209,"CA4",196,160,128,0],
        [210,"GC-DG",32,200,255,0],
        [211,"HATA",128,255,128,0],
        [212,"fimbria",204,153,204,0],
        [213,"lateral_ventricle",121,17,136,0],
        [214,"molecular_layer_HP",128,0,0,0],
        [215,"hippocampal_fissure",128,32,255,0],
        [216,"entorhinal_cortex",255,204,102,0],
        [217,"molecular_layer_subiculum",128,128,128,0],
        [218,"Amygdala",104,255,255,0],
        [219,"Cerebral_White_Matter",0,226,0,0],
        [220,"Cerebral_Cortex",205,63,78,0],
        [221,"Inf_Lat_Vent",197,58,250,0],
        [222,"Perirhinal",33,150,250,0],
        [223,"Cerebral_White_Matter_Edge",226,0,0,0],
        [224,"Background",100,100,100,0],
        [225,"Ectorhinal",197,150,250,0],
        [226,"HP_tail",170,170,255,0],
        [227,"Polymorphic-Layer",128,255,128,0],
        [228,"Intracellular-Space",204,153,204,0],
        [229,"molecular_layer_DG",168,0,0,0],
        [231,"HP_body",0,255,0,0],
        [232,"HP_head",255,0,0,0],
        [233,"presubiculum-head",32,0,32,0],
        [234,"presubiculum-body",64,0,64,0],
        [235,"subiculum-head",0,0,175,0],
        [236,"subiculum-body",0,0,255,0],
        [237,"CA1-head",175,75,75,0],
        [238,"CA1-body",255,0,0,0],
        [239,"CA3-head",0,80,0,0],
        [240,"CA3-body",0,128,0,0],
        [241,"CA4-head",120,90,50,0],
        [242,"CA4-body",196,160,128,0],
        [243,"GC-ML-DG-head",75,125,175,0],
        [244,"GC-ML-DG-body",32,200,255,0],
        [245,"molecular_layer_HP-head",100,25,25,0],
        [246,"molecular_layer_HP-body",128,0,0,0],
        [247,"FreezeSurface",10,100,100,0],
        [250,"Fornix",255,0,0,0],
        [251,"CC_Posterior",0,0,64,0],
        [252,"CC_Mid_Posterior",0,0,112,0],
        [253,"CC_Central",0,0,160,0],
        [254,"CC_Mid_Anterior",0,0,208,0],
        [255,"CC_Anterior",0,0,255,0],
        [256,"Voxel-Unchanged",0,0,0,0],
        [257,"CSF-ExtraCerebral",60,60,60,0],
        [258,"Head-ExtraCerebral",150,150,200,0],
        [259,"Eye-Fluid",60,60,60,0],
        [260,"BoneOrAir",119,159,176,0],
        [261,"PossibleFluid",120,18,134,0],
        [262,"Sinus",196,160,128,0],
        [263,"Left-Eustachian",119,159,176,0],
        [264,"Right-Eustachian",119,159,176,0],
        [265,"Left-Eyeball",60,60,60,0],
        [266,"Right-Eyeball",60,60,60,0],
        [331,"Aorta",255,0,0,0],
        [332,"Left-Common-IliacA",255,80,0,0],
        [333,"Right-Common-IliacA",255,160,0,0],
        [334,"Left-External-IliacA",255,255,0,0],
        [335,"Right-External-IliacA",0,255,0,0],
        [336,"Left-Internal-IliacA",255,0,160,0],
        [337,"Right-Internal-IliacA",255,0,255,0],
        [338,"Left-Lateral-SacralA",255,50,80,0],
        [339,"Right-Lateral-SacralA",80,255,50,0],
        [340,"Left-ObturatorA",160,255,50,0],
        [341,"Right-ObturatorA",160,200,255,0],
        [342,"Left-Internal-PudendalA",0,255,160,0],
        [343,"Right-Internal-PudendalA",0,0,255,0],
        [344,"Left-UmbilicalA",80,50,255,0],
        [345,"Right-UmbilicalA",160,0,255,0],
        [346,"Left-Inf-RectalA",255,210,0,0],
        [347,"Right-Inf-RectalA",0,160,255,0],
        [348,"Left-Common-IliacV",255,200,80,0],
        [349,"Right-Common-IliacV",255,200,160,0],
        [350,"Left-External-IliacV",255,80,200,0],
        [351,"Right-External-IliacV",255,160,200,0],
        [352,"Left-Internal-IliacV",30,255,80,0],
        [353,"Right-Internal-IliacV",80,200,255,0],
        [354,"Left-ObturatorV",80,255,200,0],
        [355,"Right-ObturatorV",195,255,200,0],
        [356,"Left-Internal-PudendalV",120,200,20,0],
        [357,"Right-Internal-PudendalV",170,10,200,0],
        [358,"Pos-Lymph",20,130,180,0],
        [359,"Neg-Lymph",20,180,130,0],
        [400,"V1",206,62,78,0],
        [401,"V2",121,18,134,0],
        [402,"BA44",199,58,250,0],
        [403,"BA45",1,148,0,0],
        [404,"BA4a",221,248,164,0],
        [405,"BA4p",231,148,34,0],
        [406,"BA6",1,118,14,0],
        [407,"BA2",120,118,14,0],
        [408,"BA1_old",123,186,221,0],
        [409,"BAun2",238,13,177,0],
        [410,"BA1",123,186,220,0],
        [411,"BA2b",138,13,206,0],
        [412,"BA3a",238,130,176,0],
        [413,"BA3b",218,230,76,0],
        [414,"MT",38,213,176,0],
        [415,"AIPS_AIP_l",1,225,176,0],
        [416,"AIPS_AIP_r",1,225,176,0],
        [417,"AIPS_VIP_l",200,2,100,0],
        [418,"AIPS_VIP_r",200,2,100,0],
        [419,"IPL_PFcm_l",5,200,90,0],
        [420,"IPL_PFcm_r",5,200,90,0],
        [421,"IPL_PF_l",100,5,200,0],
        [422,"IPL_PFm_l",25,255,100,0],
        [423,"IPL_PFm_r",25,255,100,0],
        [424,"IPL_PFop_l",230,7,100,0],
        [425,"IPL_PFop_r",230,7,100,0],
        [426,"IPL_PF_r",100,5,200,0],
        [427,"IPL_PFt_l",150,10,200,0],
        [428,"IPL_PFt_r",150,10,200,0],
        [429,"IPL_PGa_l",175,10,176,0],
        [430,"IPL_PGa_r",175,10,176,0],
        [431,"IPL_PGp_l",10,100,255,0],
        [432,"IPL_PGp_r",10,100,255,0],
        [433,"Visual_V3d_l",150,45,70,0],
        [434,"Visual_V3d_r",150,45,70,0],
        [435,"Visual_V4_l",45,200,15,0],
        [436,"Visual_V4_r",45,200,15,0],
        [437,"Visual_V5_b",227,45,100,0],
        [438,"Visual_VP_l",227,45,100,0],
        [439,"Visual_VP_r",227,45,100,0],
        [498,"wmsa",143,188,143,0],
        [499,"other_wmsa",255,248,220,0],
        [500,"right_CA2_3",17,85,136,0],
        [501,"right_alveus",119,187,102,0],
        [502,"right_CA1",204,68,34,0],
        [503,"right_fimbria",204,0,255,0],
        [504,"right_presubiculum",221,187,17,0],
        [505,"right_hippocampal_fissure",153,221,238,0],
        [506,"right_CA4_DG",51,17,17,0],
        [507,"right_subiculum",0,119,85,0],
        [508,"right_fornix",20,100,200,0],
        [550,"left_CA2_3",17,85,137,0],
        [551,"left_alveus",119,187,103,0],
        [552,"left_CA1",204,68,35,0],
        [553,"left_fimbria",204,0,254,0],
        [554,"left_presubiculum",221,187,16,0],
        [555,"left_hippocampal_fissure",153,221,239,0],
        [556,"left_CA4_DG",51,17,18,0],
        [557,"left_subiculum",0,119,86,0],
        [558,"left_fornix",20,100,201,0],
        [600,"Tumor",254,254,254,0],
        [601,"Cbm_Left_I_IV",70,130,180,0],
        [602,"Cbm_Right_I_IV",245,245,245,0],
        [603,"Cbm_Left_V",205,62,78,0],
        [604,"Cbm_Right_V",120,18,134,0],
        [605,"Cbm_Left_VI",196,58,250,0],
        [606,"Cbm_Vermis_VI",0,148,0,0],
        [607,"Cbm_Right_VI",220,248,164,0],
        [608,"Cbm_Left_CrusI",230,148,34,0],
        [609,"Cbm_Vermis_CrusI",0,118,14,0],
        [610,"Cbm_Right_CrusI",0,118,14,0],
        [611,"Cbm_Left_CrusII",122,186,220,0],
        [612,"Cbm_Vermis_CrusII",236,13,176,0],
        [613,"Cbm_Right_CrusII",12,48,255,0],
        [614,"Cbm_Left_VIIb",204,182,142,0],
        [615,"Cbm_Vermis_VIIb",42,204,164,0],
        [616,"Cbm_Right_VIIb",119,159,176,0],
        [617,"Cbm_Left_VIIIa",220,216,20,0],
        [618,"Cbm_Vermis_VIIIa",103,255,255,0],
        [619,"Cbm_Right_VIIIa",80,196,98,0],
        [620,"Cbm_Left_VIIIb",60,58,210,0],
        [621,"Cbm_Vermis_VIIIb",60,58,210,0],
        [622,"Cbm_Right_VIIIb",60,58,210,0],
        [623,"Cbm_Left_IX",60,58,210,0],
        [624,"Cbm_Vermis_IX",60,60,60,0],
        [625,"Cbm_Right_IX",255,165,0,0],
        [626,"Cbm_Left_X",255,165,0,0],
        [627,"Cbm_Vermis_X",0,255,127,0],
        [628,"Cbm_Right_X",165,42,42,0],
        [640,"Cbm_Right_I_V_med",204,0,0,0],
        [641,"Cbm_Right_I_V_mid",255,0,0,0],
        [642,"Cbm_Right_VI_med",0,0,255,0],
        [643,"Cbm_Right_VI_mid",30,144,255,0],
        [644,"Cbm_Right_VI_lat",100,212,237,0],
        [645,"Cbm_Right_CrusI_med",218,165,32,0],
        [646,"Cbm_Right_CrusI_mid",255,215,0,0],
        [647,"Cbm_Right_CrusI_lat",255,255,166,0],
        [648,"Cbm_Right_CrusII_med",153,0,204,0],
        [649,"Cbm_Right_CrusII_mid",153,141,209,0],
        [650,"Cbm_Right_CrusII_lat",204,204,255,0],
        [651,"Cbm_Right_7med",31,212,194,0],
        [652,"Cbm_Right_7mid",3,255,237,0],
        [653,"Cbm_Right_7lat",204,255,255,0],
        [654,"Cbm_Right_8med",86,74,147,0],
        [655,"Cbm_Right_8mid",114,114,190,0],
        [656,"Cbm_Right_8lat",184,178,255,0],
        [657,"Cbm_Right_PUNs",126,138,37,0],
        [658,"Cbm_Right_TONs",189,197,117,0],
        [659,"Cbm_Right_FLOs",240,230,140,0],
        [660,"Cbm_Left_I_V_med",204,0,0,0],
        [661,"Cbm_Left_I_V_mid",255,0,0,0],
        [662,"Cbm_Left_VI_med",0,0,255,0],
        [663,"Cbm_Left_VI_mid",30,144,255,0],
        [664,"Cbm_Left_VI_lat",100,212,237,0],
        [665,"Cbm_Left_CrusI_med",218,165,32,0],
        [666,"Cbm_Left_CrusI_mid",255,215,0,0],
        [667,"Cbm_Left_CrusI_lat",255,255,166,0],
        [668,"Cbm_Left_CrusII_med",153,0,204,0],
        [669,"Cbm_Left_CrusII_mid",153,141,209,0],
        [670,"Cbm_Left_CrusII_lat",204,204,255,0],
        [671,"Cbm_Left_7med",31,212,194,0],
        [672,"Cbm_Left_7mid",3,255,237,0],
        [673,"Cbm_Left_7lat",204,255,255,0],
        [674,"Cbm_Left_8med",86,74,147,0],
        [675,"Cbm_Left_8mid",114,114,190,0],
        [676,"Cbm_Left_8lat",184,178,255,0],
        [677,"Cbm_Left_PUNs",126,138,37,0],
        [678,"Cbm_Left_TONs",189,197,117,0],
        [679,"Cbm_Left_FLOs",240,230,140,0],
        [690,"CbmWM_Gyri_Left",122,135,50,0],
        [691,"CbmWM_Gyri_Right",122,135,50,0],
        [701,"CSF-FSL-FAST",120,18,134,0],
        [702,"GrayMatter-FSL-FAST",205,62,78,0],
        [703,"WhiteMatter-FSL-FAST",0,225,0,0],
        [801,"L_hypothalamus_anterior_inferior",250,255,50,0],
        [802,"L_hypothalamus_anterior_superior",80,200,255,0],
        [803,"L_hypothalamus_posterior",255,160,0,0],
        [804,"L_hypothalamus_tubular_inferior",255,160,200,0],
        [805,"L_hypothalamus_tubular_superior",20,180,130,0],
        [806,"R_hypothalamus_anterior_inferior",250,255,50,0],
        [807,"R_hypothalamus_anterior_superior",80,200,255,0],
        [808,"R_hypothalamus_posterior",255,160,0,0],
        [809,"R_hypothalamus_tubular_inferior",255,160,200,0],
        [810,"R_hypothalamus_tubular_superior",20,180,130,0],
        [999,"SUSPICIOUS",255,100,100,0],
        [1000,"ctx-lh-unknown",25,5,25,0],
        [1001,"ctx-lh-bankssts",25,100,40,0],
        [1002,"ctx-lh-caudalanteriorcingulate",125,100,160,0],
        [1003,"ctx-lh-caudalmiddlefrontal",100,25,0,0],
        [1004,"ctx-lh-corpuscallosum",120,70,50,0],
        [1005,"ctx-lh-cuneus",220,20,100,0],
        [1006,"ctx-lh-entorhinal",220,20,10,0],
        [1007,"ctx-lh-fusiform",180,220,140,0],
        [1008,"ctx-lh-inferiorparietal",220,60,220,0],
        [1009,"ctx-lh-inferiortemporal",180,40,120,0],
        [1010,"ctx-lh-isthmuscingulate",140,20,140,0],
        [1011,"ctx-lh-lateraloccipital",20,30,140,0],
        [1012,"ctx-lh-lateralorbitofrontal",35,75,50,0],
        [1013,"ctx-lh-lingual",225,140,140,0],
        [1014,"ctx-lh-medialorbitofrontal",200,35,75,0],
        [1015,"ctx-lh-middletemporal",160,100,50,0],
        [1016,"ctx-lh-parahippocampal",20,220,60,0],
        [1017,"ctx-lh-paracentral",60,220,60,0],
        [1018,"ctx-lh-parsopercularis",220,180,140,0],
        [1019,"ctx-lh-parsorbitalis",20,100,50,0],
        [1020,"ctx-lh-parstriangularis",220,60,20,0],
        [1021,"ctx-lh-pericalcarine",120,100,60,0],
        [1022,"ctx-lh-postcentral",220,20,20,0],
        [1023,"ctx-lh-posteriorcingulate",220,180,220,0],
        [1024,"ctx-lh-precentral",60,20,220,0],
        [1025,"ctx-lh-precuneus",160,140,180,0],
        [1026,"ctx-lh-rostralanteriorcingulate",80,20,140,0],
        [1027,"ctx-lh-rostralmiddlefrontal",75,50,125,0],
        [1028,"ctx-lh-superiorfrontal",20,220,160,0],
        [1029,"ctx-lh-superiorparietal",20,180,140,0],
        [1030,"ctx-lh-superiortemporal",140,220,220,0],
        [1031,"ctx-lh-supramarginal",80,160,20,0],
        [1032,"ctx-lh-frontalpole",100,0,100,0],
        [1033,"ctx-lh-temporalpole",70,70,70,0],
        [1034,"ctx-lh-transversetemporal",150,150,200,0],
        [1035,"ctx-lh-insula",255,192,32,0],
        [2000,"ctx-rh-unknown",25,5,25,0],
        [2001,"ctx-rh-bankssts",25,100,40,0],
        [2002,"ctx-rh-caudalanteriorcingulate",125,100,160,0],
        [2003,"ctx-rh-caudalmiddlefrontal",100,25,0,0],
        [2004,"ctx-rh-corpuscallosum",120,70,50,0],
        [2005,"ctx-rh-cuneus",220,20,100,0],
        [2006,"ctx-rh-entorhinal",220,20,10,0],
        [2007,"ctx-rh-fusiform",180,220,140,0],
        [2008,"ctx-rh-inferiorparietal",220,60,220,0],
        [2009,"ctx-rh-inferiortemporal",180,40,120,0],
        [2010,"ctx-rh-isthmuscingulate",140,20,140,0],
        [2011,"ctx-rh-lateraloccipital",20,30,140,0],
        [2012,"ctx-rh-lateralorbitofrontal",35,75,50,0],
        [2013,"ctx-rh-lingual",225,140,140,0],
        [2014,"ctx-rh-medialorbitofrontal",200,35,75,0],
        [2015,"ctx-rh-middletemporal",160,100,50,0],
        [2016,"ctx-rh-parahippocampal",20,220,60,0],
        [2017,"ctx-rh-paracentral",60,220,60,0],
        [2018,"ctx-rh-parsopercularis",220,180,140,0],
        [2019,"ctx-rh-parsorbitalis",20,100,50,0],
        [2020,"ctx-rh-parstriangularis",220,60,20,0],
        [2021,"ctx-rh-pericalcarine",120,100,60,0],
        [2022,"ctx-rh-postcentral",220,20,20,0],
        [2023,"ctx-rh-posteriorcingulate",220,180,220,0],
        [2024,"ctx-rh-precentral",60,20,220,0],
        [2025,"ctx-rh-precuneus",160,140,180,0],
        [2026,"ctx-rh-rostralanteriorcingulate",80,20,140,0],
        [2027,"ctx-rh-rostralmiddlefrontal",75,50,125,0],
        [2028,"ctx-rh-superiorfrontal",20,220,160,0],
        [2029,"ctx-rh-superiorparietal",20,180,140,0],
        [2030,"ctx-rh-superiortemporal",140,220,220,0],
        [2031,"ctx-rh-supramarginal",80,160,20,0],
        [2032,"ctx-rh-frontalpole",100,0,100,0],
        [2033,"ctx-rh-temporalpole",70,70,70,0],
        [2034,"ctx-rh-transversetemporal",150,150,200,0],
        [2035,"ctx-rh-insula",255,192,32,0],
        [3000,"wm-lh-unknown",230,250,230,0],
        [3001,"wm-lh-bankssts",230,155,215,0],
        [3002,"wm-lh-caudalanteriorcingulate",130,155,95,0],
        [3003,"wm-lh-caudalmiddlefrontal",155,230,255,0],
        [3004,"wm-lh-corpuscallosum",135,185,205,0],
        [3005,"wm-lh-cuneus",35,235,155,0],
        [3006,"wm-lh-entorhinal",35,235,245,0],
        [3007,"wm-lh-fusiform",75,35,115,0],
        [3008,"wm-lh-inferiorparietal",35,195,35,0],
        [3009,"wm-lh-inferiortemporal",75,215,135,0],
        [3010,"wm-lh-isthmuscingulate",115,235,115,0],
        [3011,"wm-lh-lateraloccipital",235,225,115,0],
        [3012,"wm-lh-lateralorbitofrontal",220,180,205,0],
        [3013,"wm-lh-lingual",30,115,115,0],
        [3014,"wm-lh-medialorbitofrontal",55,220,180,0],
        [3015,"wm-lh-middletemporal",95,155,205,0],
        [3016,"wm-lh-parahippocampal",235,35,195,0],
        [3017,"wm-lh-paracentral",195,35,195,0],
        [3018,"wm-lh-parsopercularis",35,75,115,0],
        [3019,"wm-lh-parsorbitalis",235,155,205,0],
        [3020,"wm-lh-parstriangularis",35,195,235,0],
        [3021,"wm-lh-pericalcarine",135,155,195,0],
        [3022,"wm-lh-postcentral",35,235,235,0],
        [3023,"wm-lh-posteriorcingulate",35,75,35,0],
        [3024,"wm-lh-precentral",195,235,35,0],
        [3025,"wm-lh-precuneus",95,115,75,0],
        [3026,"wm-lh-rostralanteriorcingulate",175,235,115,0],
        [3027,"wm-lh-rostralmiddlefrontal",180,205,130,0],
        [3028,"wm-lh-superiorfrontal",235,35,95,0],
        [3029,"wm-lh-superiorparietal",235,75,115,0],
        [3030,"wm-lh-superiortemporal",115,35,35,0],
        [3031,"wm-lh-supramarginal",175,95,235,0],
        [3032,"wm-lh-frontalpole",155,255,155,0],
        [3033,"wm-lh-temporalpole",185,185,185,0],
        [3034,"wm-lh-transversetemporal",105,105,55,0],
        [3035,"wm-lh-insula",20,220,160,0],
        [4000,"wm-rh-unknown",230,250,230,0],
        [4001,"wm-rh-bankssts",230,155,215,0],
        [4002,"wm-rh-caudalanteriorcingulate",130,155,95,0],
        [4003,"wm-rh-caudalmiddlefrontal",155,230,255,0],
        [4004,"wm-rh-corpuscallosum",135,185,205,0],
        [4005,"wm-rh-cuneus",35,235,155,0],
        [4006,"wm-rh-entorhinal",35,235,245,0],
        [4007,"wm-rh-fusiform",75,35,115,0],
        [4008,"wm-rh-inferiorparietal",35,195,35,0],
        [4009,"wm-rh-inferiortemporal",75,215,135,0],
        [4010,"wm-rh-isthmuscingulate",115,235,115,0],
        [4011,"wm-rh-lateraloccipital",235,225,115,0],
        [4012,"wm-rh-lateralorbitofrontal",220,180,205,0],
        [4013,"wm-rh-lingual",30,115,115,0],
        [4014,"wm-rh-medialorbitofrontal",55,220,180,0],
        [4015,"wm-rh-middletemporal",95,155,205,0],
        [4016,"wm-rh-parahippocampal",235,35,195,0],
        [4017,"wm-rh-paracentral",195,35,195,0],
        [4018,"wm-rh-parsopercularis",35,75,115,0],
        [4019,"wm-rh-parsorbitalis",235,155,205,0],
        [4020,"wm-rh-parstriangularis",35,195,235,0],
        [4021,"wm-rh-pericalcarine",135,155,195,0],
        [4022,"wm-rh-postcentral",35,235,235,0],
        [4023,"wm-rh-posteriorcingulate",35,75,35,0],
        [4024,"wm-rh-precentral",195,235,35,0],
        [4025,"wm-rh-precuneus",95,115,75,0],
        [4026,"wm-rh-rostralanteriorcingulate",175,235,115,0],
        [4027,"wm-rh-rostralmiddlefrontal",180,205,130,0],
        [4028,"wm-rh-superiorfrontal",235,35,95,0],
        [4029,"wm-rh-superiorparietal",235,75,115,0],
        [4030,"wm-rh-superiortemporal",115,35,35,0],
        [4031,"wm-rh-supramarginal",175,95,235,0],
        [4032,"wm-rh-frontalpole",155,255,155,0],
        [4033,"wm-rh-temporalpole",185,185,185,0],
        [4034,"wm-rh-transversetemporal",105,105,55,0],
        [4035,"wm-rh-insula",20,220,160,0],
        [1301,"ctx-lh-frontal-lobe",25,100,40,0],
        [1303,"ctx-lh-cingulate-lobe",100,25,0,0],
        [1304,"ctx-lh-occipital-lobe",120,70,50,0],
        [1305,"ctx-lh-temporal-lobe",220,20,100,0],
        [1306,"ctx-lh-parietal-lobe",220,20,10,0],
        [1307,"ctx-lh-insula-lobe",255,192,32,0],
        [2301,"ctx-rh-frontal-lobe",25,100,40,0],
        [2303,"ctx-rh-cingulate-lobe",100,25,0,0],
        [2304,"ctx-rh-occipital-lobe",120,70,50,0],
        [2305,"ctx-rh-temporal-lobe",220,20,100,0],
        [2306,"ctx-rh-parietal-lobe",220,20,10,0],
        [2307,"ctx-rh-insula-lobe",255,192,32,0],
        [3201,"wm-lh-frontal-lobe",235,35,95,0],
        [3203,"wm-lh-cingulate-lobe",35,75,35,0],
        [3204,"wm-lh-occipital-lobe",135,155,195,0],
        [3205,"wm-lh-temporal-lobe",115,35,35,0],
        [3206,"wm-lh-parietal-lobe",35,195,35,0],
        [3207,"wm-lh-insula-lobe",20,220,160,0],
        [4201,"wm-rh-frontal-lobe",235,35,95,0],
        [4203,"wm-rh-cingulate-lobe",35,75,35,0],
        [4204,"wm-rh-occipital-lobe",135,155,195,0],
        [4205,"wm-rh-temporal-lobe",115,35,35,0],
        [4206,"wm-rh-parietal-lobe",35,195,35,0],
        [4207,"wm-rh-insula-lobe",20,220,160,0],
        [1100,"ctx-lh-Unknown",0,0,0,0],
        [1101,"ctx-lh-Corpus_callosum",50,50,50,0],
        [1102,"ctx-lh-G_and_S_Insula_ONLY_AVERAGE",180,20,30,0],
        [1103,"ctx-lh-G_cingulate-Isthmus",60,25,25,0],
        [1104,"ctx-lh-G_cingulate-Main_part",25,60,60,0],
        [1200,"ctx-lh-G_cingulate-caudal_ACC",25,60,61,0],
        [1201,"ctx-lh-G_cingulate-rostral_ACC",25,90,60,0],
        [1202,"ctx-lh-G_cingulate-posterior",25,120,60,0],
        [1205,"ctx-lh-S_cingulate-caudal_ACC",25,150,60,0],
        [1206,"ctx-lh-S_cingulate-rostral_ACC",25,180,60,0],
        [1207,"ctx-lh-S_cingulate-posterior",25,210,60,0],
        [1210,"ctx-lh-S_pericallosal-caudal",25,150,90,0],
        [1211,"ctx-lh-S_pericallosal-rostral",25,180,90,0],
        [1212,"ctx-lh-S_pericallosal-posterior",25,210,90,0],
        [1105,"ctx-lh-G_cuneus",180,20,20,0],
        [1106,"ctx-lh-G_frontal_inf-Opercular_part",220,20,100,0],
        [1107,"ctx-lh-G_frontal_inf-Orbital_part",140,60,60,0],
        [1108,"ctx-lh-G_frontal_inf-Triangular_part",180,220,140,0],
        [1109,"ctx-lh-G_frontal_middle",140,100,180,0],
        [1110,"ctx-lh-G_frontal_superior",180,20,140,0],
        [1111,"ctx-lh-G_frontomarginal",140,20,140,0],
        [1112,"ctx-lh-G_insular_long",21,10,10,0],
        [1113,"ctx-lh-G_insular_short",225,140,140,0],
        [1114,"ctx-lh-G_and_S_occipital_inferior",23,60,180,0],
        [1115,"ctx-lh-G_occipital_middle",180,60,180,0],
        [1116,"ctx-lh-G_occipital_superior",20,220,60,0],
        [1117,"ctx-lh-G_occipit-temp_lat-Or_fusiform",60,20,140,0],
        [1118,"ctx-lh-G_occipit-temp_med-Lingual_part",220,180,140,0],
        [1119,"ctx-lh-G_occipit-temp_med-Parahippocampal_part",65,100,20,0],
        [1120,"ctx-lh-G_orbital",220,60,20,0],
        [1121,"ctx-lh-G_paracentral",60,100,60,0],
        [1122,"ctx-lh-G_parietal_inferior-Angular_part",20,60,220,0],
        [1123,"ctx-lh-G_parietal_inferior-Supramarginal_part",100,100,60,0],
        [1124,"ctx-lh-G_parietal_superior",220,180,220,0],
        [1125,"ctx-lh-G_postcentral",20,180,140,0],
        [1126,"ctx-lh-G_precentral",60,140,180,0],
        [1127,"ctx-lh-G_precuneus",25,20,140,0],
        [1128,"ctx-lh-G_rectus",20,60,100,0],
        [1129,"ctx-lh-G_subcallosal",60,220,20,0],
        [1130,"ctx-lh-G_subcentral",60,20,220,0],
        [1131,"ctx-lh-G_temporal_inferior",220,220,100,0],
        [1132,"ctx-lh-G_temporal_middle",180,60,60,0],
        [1133,"ctx-lh-G_temp_sup-G_temp_transv_and_interm_S",60,60,220,0],
        [1134,"ctx-lh-G_temp_sup-Lateral_aspect",220,60,220,0],
        [1135,"ctx-lh-G_temp_sup-Planum_polare",65,220,60,0],
        [1136,"ctx-lh-G_temp_sup-Planum_tempolare",25,140,20,0],
        [1137,"ctx-lh-G_and_S_transverse_frontopolar",13,0,250,0],
        [1138,"ctx-lh-Lat_Fissure-ant_sgt-ramus_horizontal",61,20,220,0],
        [1139,"ctx-lh-Lat_Fissure-ant_sgt-ramus_vertical",61,20,60,0],
        [1140,"ctx-lh-Lat_Fissure-post_sgt",61,60,100,0],
        [1141,"ctx-lh-Medial_wall",25,25,25,0],
        [1142,"ctx-lh-Pole_occipital",140,20,60,0],
        [1143,"ctx-lh-Pole_temporal",220,180,20,0],
        [1144,"ctx-lh-S_calcarine",63,180,180,0],
        [1145,"ctx-lh-S_central",221,20,10,0],
        [1146,"ctx-lh-S_central_insula",21,220,20,0],
        [1147,"ctx-lh-S_cingulate-Main_part_and_Intracingulate",183,100,20,0],
        [1148,"ctx-lh-S_cingulate-Marginalis_part",221,20,100,0],
        [1149,"ctx-lh-S_circular_insula_anterior",221,60,140,0],
        [1150,"ctx-lh-S_circular_insula_inferior",221,20,220,0],
        [1151,"ctx-lh-S_circular_insula_superior",61,220,220,0],
        [1152,"ctx-lh-S_collateral_transverse_ant",100,200,200,0],
        [1153,"ctx-lh-S_collateral_transverse_post",10,200,200,0],
        [1154,"ctx-lh-S_frontal_inferior",221,220,20,0],
        [1155,"ctx-lh-S_frontal_middle",141,20,100,0],
        [1156,"ctx-lh-S_frontal_superior",61,220,100,0],
        [1157,"ctx-lh-S_frontomarginal",21,220,60,0],
        [1158,"ctx-lh-S_intermedius_primus-Jensen",141,60,20,0],
        [1159,"ctx-lh-S_intraparietal-and_Parietal_transverse",143,20,220,0],
        [1160,"ctx-lh-S_occipital_anterior",61,20,180,0],
        [1161,"ctx-lh-S_occipital_middle_and_Lunatus",101,60,220,0],
        [1162,"ctx-lh-S_occipital_superior_and_transversalis",21,20,140,0],
        [1163,"ctx-lh-S_occipito-temporal_lateral",221,140,20,0],
        [1164,"ctx-lh-S_occipito-temporal_medial_and_S_Lingual",141,100,220,0],
        [1165,"ctx-lh-S_orbital-H_shapped",101,20,20,0],
        [1166,"ctx-lh-S_orbital_lateral",221,100,20,0],
        [1167,"ctx-lh-S_orbital_medial-Or_olfactory",181,200,20,0],
        [1168,"ctx-lh-S_paracentral",21,180,140,0],
        [1169,"ctx-lh-S_parieto_occipital",101,100,180,0],
        [1170,"ctx-lh-S_pericallosal",181,220,20,0],
        [1171,"ctx-lh-S_postcentral",21,140,200,0],
        [1172,"ctx-lh-S_precentral-Inferior-part",21,20,240,0],
        [1173,"ctx-lh-S_precentral-Superior-part",21,20,200,0],
        [1174,"ctx-lh-S_subcentral_ant",61,180,60,0],
        [1175,"ctx-lh-S_subcentral_post",61,180,250,0],
        [1176,"ctx-lh-S_suborbital",21,20,60,0],
        [1177,"ctx-lh-S_subparietal",101,60,60,0],
        [1178,"ctx-lh-S_supracingulate",21,220,220,0],
        [1179,"ctx-lh-S_temporal_inferior",21,180,180,0],
        [1180,"ctx-lh-S_temporal_superior",223,220,60,0],
        [1181,"ctx-lh-S_temporal_transverse",221,60,60,0],
        [2100,"ctx-rh-Unknown",0,0,0,0],
        [2101,"ctx-rh-Corpus_callosum",50,50,50,0],
        [2102,"ctx-rh-G_and_S_Insula_ONLY_AVERAGE",180,20,30,0],
        [2103,"ctx-rh-G_cingulate-Isthmus",60,25,25,0],
        [2104,"ctx-rh-G_cingulate-Main_part",25,60,60,0],
        [2105,"ctx-rh-G_cuneus",180,20,20,0],
        [2106,"ctx-rh-G_frontal_inf-Opercular_part",220,20,100,0],
        [2107,"ctx-rh-G_frontal_inf-Orbital_part",140,60,60,0],
        [2108,"ctx-rh-G_frontal_inf-Triangular_part",180,220,140,0],
        [2109,"ctx-rh-G_frontal_middle",140,100,180,0],
        [2110,"ctx-rh-G_frontal_superior",180,20,140,0],
        [2111,"ctx-rh-G_frontomarginal",140,20,140,0],
        [2112,"ctx-rh-G_insular_long",21,10,10,0],
        [2113,"ctx-rh-G_insular_short",225,140,140,0],
        [2114,"ctx-rh-G_and_S_occipital_inferior",23,60,180,0],
        [2115,"ctx-rh-G_occipital_middle",180,60,180,0],
        [2116,"ctx-rh-G_occipital_superior",20,220,60,0],
        [2117,"ctx-rh-G_occipit-temp_lat-Or_fusiform",60,20,140,0],
        [2118,"ctx-rh-G_occipit-temp_med-Lingual_part",220,180,140,0],
        [2119,"ctx-rh-G_occipit-temp_med-Parahippocampal_part",65,100,20,0],
        [2120,"ctx-rh-G_orbital",220,60,20,0],
        [2121,"ctx-rh-G_paracentral",60,100,60,0],
        [2122,"ctx-rh-G_parietal_inferior-Angular_part",20,60,220,0],
        [2123,"ctx-rh-G_parietal_inferior-Supramarginal_part",100,100,60,0],
        [2124,"ctx-rh-G_parietal_superior",220,180,220,0],
        [2125,"ctx-rh-G_postcentral",20,180,140,0],
        [2126,"ctx-rh-G_precentral",60,140,180,0],
        [2127,"ctx-rh-G_precuneus",25,20,140,0],
        [2128,"ctx-rh-G_rectus",20,60,100,0],
        [2129,"ctx-rh-G_subcallosal",60,220,20,0],
        [2130,"ctx-rh-G_subcentral",60,20,220,0],
        [2131,"ctx-rh-G_temporal_inferior",220,220,100,0],
        [2132,"ctx-rh-G_temporal_middle",180,60,60,0],
        [2133,"ctx-rh-G_temp_sup-G_temp_transv_and_interm_S",60,60,220,0],
        [2134,"ctx-rh-G_temp_sup-Lateral_aspect",220,60,220,0],
        [2135,"ctx-rh-G_temp_sup-Planum_polare",65,220,60,0],
        [2136,"ctx-rh-G_temp_sup-Planum_tempolare",25,140,20,0],
        [2137,"ctx-rh-G_and_S_transverse_frontopolar",13,0,250,0],
        [2138,"ctx-rh-Lat_Fissure-ant_sgt-ramus_horizontal",61,20,220,0],
        [2139,"ctx-rh-Lat_Fissure-ant_sgt-ramus_vertical",61,20,60,0],
        [2140,"ctx-rh-Lat_Fissure-post_sgt",61,60,100,0],
        [2141,"ctx-rh-Medial_wall",25,25,25,0],
        [2142,"ctx-rh-Pole_occipital",140,20,60,0],
        [2143,"ctx-rh-Pole_temporal",220,180,20,0],
        [2144,"ctx-rh-S_calcarine",63,180,180,0],
        [2145,"ctx-rh-S_central",221,20,10,0],
        [2146,"ctx-rh-S_central_insula",21,220,20,0],
        [2147,"ctx-rh-S_cingulate-Main_part_and_Intracingulate",183,100,20,0],
        [2148,"ctx-rh-S_cingulate-Marginalis_part",221,20,100,0],
        [2149,"ctx-rh-S_circular_insula_anterior",221,60,140,0],
        [2150,"ctx-rh-S_circular_insula_inferior",221,20,220,0],
        [2151,"ctx-rh-S_circular_insula_superior",61,220,220,0],
        [2152,"ctx-rh-S_collateral_transverse_ant",100,200,200,0],
        [2153,"ctx-rh-S_collateral_transverse_post",10,200,200,0],
        [2154,"ctx-rh-S_frontal_inferior",221,220,20,0],
        [2155,"ctx-rh-S_frontal_middle",141,20,100,0],
        [2156,"ctx-rh-S_frontal_superior",61,220,100,0],
        [2157,"ctx-rh-S_frontomarginal",21,220,60,0],
        [2158,"ctx-rh-S_intermedius_primus-Jensen",141,60,20,0],
        [2159,"ctx-rh-S_intraparietal-and_Parietal_transverse",143,20,220,0],
        [2160,"ctx-rh-S_occipital_anterior",61,20,180,0],
        [2161,"ctx-rh-S_occipital_middle_and_Lunatus",101,60,220,0],
        [2162,"ctx-rh-S_occipital_superior_and_transversalis",21,20,140,0],
        [2163,"ctx-rh-S_occipito-temporal_lateral",221,140,20,0],
        [2164,"ctx-rh-S_occipito-temporal_medial_and_S_Lingual",141,100,220,0],
        [2165,"ctx-rh-S_orbital-H_shapped",101,20,20,0],
        [2166,"ctx-rh-S_orbital_lateral",221,100,20,0],
        [2167,"ctx-rh-S_orbital_medial-Or_olfactory",181,200,20,0],
        [2168,"ctx-rh-S_paracentral",21,180,140,0],
        [2169,"ctx-rh-S_parieto_occipital",101,100,180,0],
        [2170,"ctx-rh-S_pericallosal",181,220,20,0],
        [2171,"ctx-rh-S_postcentral",21,140,200,0],
        [2172,"ctx-rh-S_precentral-Inferior-part",21,20,240,0],
        [2173,"ctx-rh-S_precentral-Superior-part",21,20,200,0],
        [2174,"ctx-rh-S_subcentral_ant",61,180,60,0],
        [2175,"ctx-rh-S_subcentral_post",61,180,250,0],
        [2176,"ctx-rh-S_suborbital",21,20,60,0],
        [2177,"ctx-rh-S_subparietal",101,60,60,0],
        [2178,"ctx-rh-S_supracingulate",21,220,220,0],
        [2179,"ctx-rh-S_temporal_inferior",21,180,180,0],
        [2180,"ctx-rh-S_temporal_superior",223,220,60,0],
        [2181,"ctx-rh-S_temporal_transverse",221,60,60,0],
        [2200,"ctx-rh-G_cingulate-caudal_ACC",25,60,61,0],
        [2201,"ctx-rh-G_cingulate-rostral_ACC",25,90,60,0],
        [2202,"ctx-rh-G_cingulate-posterior",25,120,60,0],
        [2205,"ctx-rh-S_cingulate-caudal_ACC",25,150,60,0],
        [2206,"ctx-rh-S_cingulate-rostral_ACC",25,180,60,0],
        [2207,"ctx-rh-S_cingulate-posterior",25,210,60,0],
        [2210,"ctx-rh-S_pericallosal-caudal",25,150,90,0],
        [2211,"ctx-rh-S_pericallosal-rostral",25,180,90,0],
        [2212,"ctx-rh-S_pericallosal-posterior",25,210,90,0],
        [3100,"wm-lh-Unknown",0,0,0,0],
        [3101,"wm-lh-Corpus_callosum",50,50,50,0],
        [3102,"wm-lh-G_and_S_Insula_ONLY_AVERAGE",180,20,30,0],
        [3103,"wm-lh-G_cingulate-Isthmus",60,25,25,0],
        [3104,"wm-lh-G_cingulate-Main_part",25,60,60,0],
        [3105,"wm-lh-G_cuneus",180,20,20,0],
        [3106,"wm-lh-G_frontal_inf-Opercular_part",220,20,100,0],
        [3107,"wm-lh-G_frontal_inf-Orbital_part",140,60,60,0],
        [3108,"wm-lh-G_frontal_inf-Triangular_part",180,220,140,0],
        [3109,"wm-lh-G_frontal_middle",140,100,180,0],
        [3110,"wm-lh-G_frontal_superior",180,20,140,0],
        [3111,"wm-lh-G_frontomarginal",140,20,140,0],
        [3112,"wm-lh-G_insular_long",21,10,10,0],
        [3113,"wm-lh-G_insular_short",225,140,140,0],
        [3114,"wm-lh-G_and_S_occipital_inferior",23,60,180,0],
        [3115,"wm-lh-G_occipital_middle",180,60,180,0],
        [3116,"wm-lh-G_occipital_superior",20,220,60,0],
        [3117,"wm-lh-G_occipit-temp_lat-Or_fusiform",60,20,140,0],
        [3118,"wm-lh-G_occipit-temp_med-Lingual_part",220,180,140,0],
        [3119,"wm-lh-G_occipit-temp_med-Parahippocampal_part",65,100,20,0],
        [3120,"wm-lh-G_orbital",220,60,20,0],
        [3121,"wm-lh-G_paracentral",60,100,60,0],
        [3122,"wm-lh-G_parietal_inferior-Angular_part",20,60,220,0],
        [3123,"wm-lh-G_parietal_inferior-Supramarginal_part",100,100,60,0],
        [3124,"wm-lh-G_parietal_superior",220,180,220,0],
        [3125,"wm-lh-G_postcentral",20,180,140,0],
        [3126,"wm-lh-G_precentral",60,140,180,0],
        [3127,"wm-lh-G_precuneus",25,20,140,0],
        [3128,"wm-lh-G_rectus",20,60,100,0],
        [3129,"wm-lh-G_subcallosal",60,220,20,0],
        [3130,"wm-lh-G_subcentral",60,20,220,0],
        [3131,"wm-lh-G_temporal_inferior",220,220,100,0],
        [3132,"wm-lh-G_temporal_middle",180,60,60,0],
        [3133,"wm-lh-G_temp_sup-G_temp_transv_and_interm_S",60,60,220,0],
        [3134,"wm-lh-G_temp_sup-Lateral_aspect",220,60,220,0],
        [3135,"wm-lh-G_temp_sup-Planum_polare",65,220,60,0],
        [3136,"wm-lh-G_temp_sup-Planum_tempolare",25,140,20,0],
        [3137,"wm-lh-G_and_S_transverse_frontopolar",13,0,250,0],
        [3138,"wm-lh-Lat_Fissure-ant_sgt-ramus_horizontal",61,20,220,0],
        [3139,"wm-lh-Lat_Fissure-ant_sgt-ramus_vertical",61,20,60,0],
        [3140,"wm-lh-Lat_Fissure-post_sgt",61,60,100,0],
        [3141,"wm-lh-Medial_wall",25,25,25,0],
        [3142,"wm-lh-Pole_occipital",140,20,60,0],
        [3143,"wm-lh-Pole_temporal",220,180,20,0],
        [3144,"wm-lh-S_calcarine",63,180,180,0],
        [3145,"wm-lh-S_central",221,20,10,0],
        [3146,"wm-lh-S_central_insula",21,220,20,0],
        [3147,"wm-lh-S_cingulate-Main_part_and_Intracingulate",183,100,20,0],
        [3148,"wm-lh-S_cingulate-Marginalis_part",221,20,100,0],
        [3149,"wm-lh-S_circular_insula_anterior",221,60,140,0],
        [3150,"wm-lh-S_circular_insula_inferior",221,20,220,0],
        [3151,"wm-lh-S_circular_insula_superior",61,220,220,0],
        [3152,"wm-lh-S_collateral_transverse_ant",100,200,200,0],
        [3153,"wm-lh-S_collateral_transverse_post",10,200,200,0],
        [3154,"wm-lh-S_frontal_inferior",221,220,20,0],
        [3155,"wm-lh-S_frontal_middle",141,20,100,0],
        [3156,"wm-lh-S_frontal_superior",61,220,100,0],
        [3157,"wm-lh-S_frontomarginal",21,220,60,0],
        [3158,"wm-lh-S_intermedius_primus-Jensen",141,60,20,0],
        [3159,"wm-lh-S_intraparietal-and_Parietal_transverse",143,20,220,0],
        [3160,"wm-lh-S_occipital_anterior",61,20,180,0],
        [3161,"wm-lh-S_occipital_middle_and_Lunatus",101,60,220,0],
        [3162,"wm-lh-S_occipital_superior_and_transversalis",21,20,140,0],
        [3163,"wm-lh-S_occipito-temporal_lateral",221,140,20,0],
        [3164,"wm-lh-S_occipito-temporal_medial_and_S_Lingual",141,100,220,0],
        [3165,"wm-lh-S_orbital-H_shapped",101,20,20,0],
        [3166,"wm-lh-S_orbital_lateral",221,100,20,0],
        [3167,"wm-lh-S_orbital_medial-Or_olfactory",181,200,20,0],
        [3168,"wm-lh-S_paracentral",21,180,140,0],
        [3169,"wm-lh-S_parieto_occipital",101,100,180,0],
        [3170,"wm-lh-S_pericallosal",181,220,20,0],
        [3171,"wm-lh-S_postcentral",21,140,200,0],
        [3172,"wm-lh-S_precentral-Inferior-part",21,20,240,0],
        [3173,"wm-lh-S_precentral-Superior-part",21,20,200,0],
        [3174,"wm-lh-S_subcentral_ant",61,180,60,0],
        [3175,"wm-lh-S_subcentral_post",61,180,250,0],
        [3176,"wm-lh-S_suborbital",21,20,60,0],
        [3177,"wm-lh-S_subparietal",101,60,60,0],
        [3178,"wm-lh-S_supracingulate",21,220,220,0],
        [3179,"wm-lh-S_temporal_inferior",21,180,180,0],
        [3180,"wm-lh-S_temporal_superior",223,220,60,0],
        [3181,"wm-lh-S_temporal_transverse",221,60,60,0],
        [4100,"wm-rh-Unknown",0,0,0,0],
        [4101,"wm-rh-Corpus_callosum",50,50,50,0],
        [4102,"wm-rh-G_and_S_Insula_ONLY_AVERAGE",180,20,30,0],
        [4103,"wm-rh-G_cingulate-Isthmus",60,25,25,0],
        [4104,"wm-rh-G_cingulate-Main_part",25,60,60,0],
        [4105,"wm-rh-G_cuneus",180,20,20,0],
        [4106,"wm-rh-G_frontal_inf-Opercular_part",220,20,100,0],
        [4107,"wm-rh-G_frontal_inf-Orbital_part",140,60,60,0],
        [4108,"wm-rh-G_frontal_inf-Triangular_part",180,220,140,0],
        [4109,"wm-rh-G_frontal_middle",140,100,180,0],
        [4110,"wm-rh-G_frontal_superior",180,20,140,0],
        [4111,"wm-rh-G_frontomarginal",140,20,140,0],
        [4112,"wm-rh-G_insular_long",21,10,10,0],
        [4113,"wm-rh-G_insular_short",225,140,140,0],
        [4114,"wm-rh-G_and_S_occipital_inferior",23,60,180,0],
        [4115,"wm-rh-G_occipital_middle",180,60,180,0],
        [4116,"wm-rh-G_occipital_superior",20,220,60,0],
        [4117,"wm-rh-G_occipit-temp_lat-Or_fusiform",60,20,140,0],
        [4118,"wm-rh-G_occipit-temp_med-Lingual_part",220,180,140,0],
        [4119,"wm-rh-G_occipit-temp_med-Parahippocampal_part",65,100,20,0],
        [4120,"wm-rh-G_orbital",220,60,20,0],
        [4121,"wm-rh-G_paracentral",60,100,60,0],
        [4122,"wm-rh-G_parietal_inferior-Angular_part",20,60,220,0],
        [4123,"wm-rh-G_parietal_inferior-Supramarginal_part",100,100,60,0],
        [4124,"wm-rh-G_parietal_superior",220,180,220,0],
        [4125,"wm-rh-G_postcentral",20,180,140,0],
        [4126,"wm-rh-G_precentral",60,140,180,0],
        [4127,"wm-rh-G_precuneus",25,20,140,0],
        [4128,"wm-rh-G_rectus",20,60,100,0],
        [4129,"wm-rh-G_subcallosal",60,220,20,0],
        [4130,"wm-rh-G_subcentral",60,20,220,0],
        [4131,"wm-rh-G_temporal_inferior",220,220,100,0],
        [4132,"wm-rh-G_temporal_middle",180,60,60,0],
        [4133,"wm-rh-G_temp_sup-G_temp_transv_and_interm_S",60,60,220,0],
        [4134,"wm-rh-G_temp_sup-Lateral_aspect",220,60,220,0],
        [4135,"wm-rh-G_temp_sup-Planum_polare",65,220,60,0],
        [4136,"wm-rh-G_temp_sup-Planum_tempolare",25,140,20,0],
        [4137,"wm-rh-G_and_S_transverse_frontopolar",13,0,250,0],
        [4138,"wm-rh-Lat_Fissure-ant_sgt-ramus_horizontal",61,20,220,0],
        [4139,"wm-rh-Lat_Fissure-ant_sgt-ramus_vertical",61,20,60,0],
        [4140,"wm-rh-Lat_Fissure-post_sgt",61,60,100,0],
        [4141,"wm-rh-Medial_wall",25,25,25,0],
        [4142,"wm-rh-Pole_occipital",140,20,60,0],
        [4143,"wm-rh-Pole_temporal",220,180,20,0],
        [4144,"wm-rh-S_calcarine",63,180,180,0],
        [4145,"wm-rh-S_central",221,20,10,0],
        [4146,"wm-rh-S_central_insula",21,220,20,0],
        [4147,"wm-rh-S_cingulate-Main_part_and_Intracingulate",183,100,20,0],
        [4148,"wm-rh-S_cingulate-Marginalis_part",221,20,100,0],
        [4149,"wm-rh-S_circular_insula_anterior",221,60,140,0],
        [4150,"wm-rh-S_circular_insula_inferior",221,20,220,0],
        [4151,"wm-rh-S_circular_insula_superior",61,220,220,0],
        [4152,"wm-rh-S_collateral_transverse_ant",100,200,200,0],
        [4153,"wm-rh-S_collateral_transverse_post",10,200,200,0],
        [4154,"wm-rh-S_frontal_inferior",221,220,20,0],
        [4155,"wm-rh-S_frontal_middle",141,20,100,0],
        [4156,"wm-rh-S_frontal_superior",61,220,100,0],
        [4157,"wm-rh-S_frontomarginal",21,220,60,0],
        [4158,"wm-rh-S_intermedius_primus-Jensen",141,60,20,0],
        [4159,"wm-rh-S_intraparietal-and_Parietal_transverse",143,20,220,0],
        [4160,"wm-rh-S_occipital_anterior",61,20,180,0],
        [4161,"wm-rh-S_occipital_middle_and_Lunatus",101,60,220,0],
        [4162,"wm-rh-S_occipital_superior_and_transversalis",21,20,140,0],
        [4163,"wm-rh-S_occipito-temporal_lateral",221,140,20,0],
        [4164,"wm-rh-S_occipito-temporal_medial_and_S_Lingual",141,100,220,0],
        [4165,"wm-rh-S_orbital-H_shapped",101,20,20,0],
        [4166,"wm-rh-S_orbital_lateral",221,100,20,0],
        [4167,"wm-rh-S_orbital_medial-Or_olfactory",181,200,20,0],
        [4168,"wm-rh-S_paracentral",21,180,140,0],
        [4169,"wm-rh-S_parieto_occipital",101,100,180,0],
        [4170,"wm-rh-S_pericallosal",181,220,20,0],
        [4171,"wm-rh-S_postcentral",21,140,200,0],
        [4172,"wm-rh-S_precentral-Inferior-part",21,20,240,0],
        [4173,"wm-rh-S_precentral-Superior-part",21,20,200,0],
        [4174,"wm-rh-S_subcentral_ant",61,180,60,0],
        [4175,"wm-rh-S_subcentral_post",61,180,250,0],
        [4176,"wm-rh-S_suborbital",21,20,60,0],
        [4177,"wm-rh-S_subparietal",101,60,60,0],
        [4178,"wm-rh-S_supracingulate",21,220,220,0],
        [4179,"wm-rh-S_temporal_inferior",21,180,180,0],
        [4180,"wm-rh-S_temporal_superior",223,220,60,0],
        [4181,"wm-rh-S_temporal_transverse",221,60,60,0],
        [5001,"Left-UnsegmentedWhiteMatter",20,30,40,0],
        [5002,"Right-UnsegmentedWhiteMatter",20,30,40,0],
        [5100,"fmajor",204,102,102,0],
        [5101,"fminor",204,102,102,0],
        [5102,"cc.body",204,102,102,0],
        [5103,"cc.bodyc",255,153,153,0],
        [5104,"cc.bodypf",255,153,153,0],
        [5105,"cc.bodypm",255,204,204,0],
        [5106,"cc.bodyp",255,102,102,0],
        [5107,"cc.bodyt",255,204,204,0],
        [5108,"cc.genu",255,102,102,0],
        [5109,"cc.rostrum",204,51,51,0],
        [5110,"cc.splenium",204,51,51,0],
        [5111,"acomm",204,102,102,0],
        [5112,"mcp",102,51,153,0],
        [5200,"lh.atr",255,255,102,0],
        [5201,"lh.cab",153,204,0,0],
        [5202,"lh.ccg",0,153,153,0],
        [5203,"lh.cst",204,153,255,0],
        [5204,"lh.ilf",255,153,51,0],
        [5205,"lh.slfp",204,204,204,0],
        [5206,"lh.slft",153,255,255,0],
        [5207,"lh.unc",102,153,255,0],
        [5208,"lh.cb",0,153,153,0],
        [5209,"lh.slf",204,204,204,0],
        [5210,"lh.af",153,255,255,0],
        [5211,"lh.ifof",51,153,51,0],
        [5212,"lh.fx",255,153,204,0],
        [5213,"lh.fat",204,51,102,0],
        [5214,"lh.or",153,102,255,0],
        [5215,"lh.mlf",255,255,204,0],
        [5216,"lh.slf1",51,204,255,0],
        [5217,"lh.slf2",51,255,204,0],
        [5218,"lh.slf3",204,204,204,0],
        [5219,"lh.afd",153,255,255,0],
        [5220,"lh.afv",153,255,255,0],
        [5221,"lh.ar",153,0,204,0],
        [5222,"lh.cbd",0,153,153,0],
        [5223,"lh.cbv",153,204,0,0],
        [5224,"lh.emc",51,153,51,0],
        [5225,"lh.uf",102,153,255,0],
        [5300,"rh.atr",255,255,102,0],
        [5301,"rh.cab",153,204,0,0],
        [5302,"rh.ccg",0,153,153,0],
        [5303,"rh.cst",204,153,255,0],
        [5304,"rh.ilf",255,153,51,0],
        [5305,"rh.slfp",204,204,204,0],
        [5306,"rh.slft",153,255,255,0],
        [5307,"rh.unc",102,153,255,0],
        [5308,"rh.cb",0,153,153,0],
        [5309,"rh.slf",204,204,204,0],
        [5310,"rh.af",153,255,255,0],
        [5311,"rh.ifof",51,153,51,0],
        [5312,"rh.fx",255,153,204,0],
        [5313,"rh.fat",204,51,102,0],
        [5314,"rh.or",153,102,255,0],
        [5315,"rh.mlf",255,255,204,0],
        [5316,"rh.slf1",51,204,255,0],
        [5317,"rh.slf2",51,255,204,0],
        [5318,"rh.slf3",204,204,204,0],
        [5319,"rh.afd",153,255,255,0],
        [5320,"rh.afv",153,255,255,0],
        [5321,"rh.ar",153,0,204,0],
        [5322,"rh.cbd",0,153,153,0],
        [5323,"rh.cbv",153,204,0,0],
        [5324,"rh.emc",51,153,51,0],
        [5325,"rh.uf",102,153,255,0],
        [6000,"CST-orig",0,255,0,0],
        [6001,"CST-hammer",255,255,0,0],
        [6002,"CST-CVS",0,255,255,0],
        [6003,"CST-flirt",0,0,255,0],
        [6010,"Left-SLF1",236,16,231,0],
        [6020,"Right-SLF1",237,18,232,0],
        [6030,"Left-SLF3",236,13,227,0],
        [6040,"Right-SLF3",236,17,228,0],
        [6050,"Left-CST",1,255,1,0],
        [6060,"Right-CST",2,255,1,0],
        [6070,"Left-SLF2",236,14,230,0],
        [6080,"Right-SLF2",237,14,230,0],
        [7001,"Lateral-nucleus",72,132,181,0],
        [7002,"Basolateral-nucleus",243,243,243,0],
        [7003,"Basal-nucleus",207,63,79,0],
        [7004,"Centromedial-nucleus",121,20,135,0],
        [7005,"Central-nucleus",197,60,248,0],
        [7006,"Medial-nucleus",2,149,2,0],
        [7007,"Cortical-nucleus",221,249,166,0],
        [7008,"Accessory-Basal-nucleus",232,146,35,0],
        [7009,"Corticoamygdaloid-transitio",20,60,120,0],
        [7010,"Anterior-amygdaloid-area-AAA",250,250,0,0],
        [7011,"Fusion-amygdala-HP-FAH",122,187,222,0],
        [7012,"Hippocampal-amygdala-transition-HATA",237,12,177,0],
        [7013,"Endopiriform-nucleus",10,49,255,0],
        [7014,"Lateral-nucleus-olfactory-tract",205,184,144,0],
        [7015,"Paralaminar-nucleus",45,205,165,0],
        [7016,"Intercalated-nucleus",117,160,175,0],
        [7017,"Prepiriform-cortex",221,217,21,0],
        [7018,"Periamygdaloid-cortex",20,60,120,0],
        [7019,"Envelope-Amygdala",141,21,100,0],
        [7020,"Extranuclear-Amydala",225,140,141,0],
        [7100,"Brainstem-inferior-colliculus",42,201,168,0],
        [7101,"Brainstem-cochlear-nucleus",168,104,162,0],
        [7201,"DR",121,255,250,0],
        [7202,"MnR",0,255,0,0],
        [7203,"PAG",153,153,255,0],
        [7204,"VTA",255,0,255,0],
        [7301,"Left-LC",0,0,255,0],
        [7302,"Left-LDTg",255,127,0,0],
        [7303,"Left-mRt",255,0,0,0],
        [7304,"Left-PBC",255,255,0,0],
        [7305,"Left-PnO",0,127,255,0],
        [7306,"Left-PTg",127,0,255,0],
        [7401,"Right-LC",0,0,255,0],
        [7402,"Right-LDTg",255,127,0,0],
        [7403,"Right-mRt",255,0,0,0],
        [7404,"Right-PBC",255,255,0,0],
        [7405,"Right-PnO",0,127,255,0],
        [7406,"Right-PTg",127,0,255,0],
        [8001,"Thalamus-Anterior",74,130,181,0],
        [8002,"Thalamus-Ventral-anterior",242,241,240,0],
        [8003,"Thalamus-Lateral-dorsal",206,65,78,0],
        [8004,"Thalamus-Lateral-posterior",120,21,133,0],
        [8005,"Thalamus-Ventral-lateral",195,61,246,0],
        [8006,"Thalamus-Ventral-posterior-medial",3,147,6,0],
        [8007,"Thalamus-Ventral-posterior-lateral",220,251,163,0],
        [8008,"Thalamus-intralaminar",232,146,33,0],
        [8009,"Thalamus-centromedian",4,114,14,0],
        [8010,"Thalamus-mediodorsal",121,184,220,0],
        [8011,"Thalamus-medial",235,11,175,0],
        [8012,"Thalamus-pulvinar",12,46,250,0],
        [8013,"Thalamus-lateral-geniculate",203,182,143,0],
        [8014,"Thalamus-medial-geniculate",42,204,167,0],
        [8103,"Left-AV",0,85,0,0],
        [8104,"Left-CeM",170,85,0,0],
        [8105,"Left-CL",0,170,0,0],
        [8106,"Left-CM",170,170,0,0],
        [8108,"Left-LD",170,255,0,0],
        [8109,"Left-LGN",0,0,127,0],
        [8110,"Left-LP",0,85,127,0],
        [8111,"Left-L-Sg",170,85,127,0],
        [8112,"Left-MDl",0,170,127,0],
        [8113,"Left-MDm",170,170,127,0],
        [8115,"Left-MGN",170,255,127,0],
        [8116,"Left-MV(Re)",0,0,255,0],
        [8117,"Left-Pc",170,0,255,0],
        [8118,"Left-Pf",0,85,255,0],
        [8119,"Left-Pt",170,85,255,0],
        [8120,"Left-PuA",0,170,255,0],
        [8121,"Left-PuI",170,170,255,0],
        [8122,"Left-PuL",0,255,255,0],
        [8123,"Left-PuM",170,255,255,0],
        [8125,"Left-R",255,0,0,0],
        [8126,"Left-VA",85,85,0,0],
        [8127,"Left-VAmc",255,85,0,0],
        [8128,"Left-VLa",85,170,0,0],
        [8129,"Left-VLp",255,170,0,0],
        [8130,"Left-VM",85,255,0,0],
        [8133,"Left-VPL",255,0,255,0],
        [8134,"Left-PaV",120,18,134,0],
        [8203,"Right-AV",0,85,0,0],
        [8204,"Right-CeM",170,85,0,0],
        [8205,"Right-CL",0,170,0,0],
        [8206,"Right-CM",170,170,0,0],
        [8208,"Right-LD",170,255,0,0],
        [8209,"Right-LGN",0,0,127,0],
        [8210,"Right-LP",0,85,127,0],
        [8211,"Right-L-Sg",170,85,127,0],
        [8212,"Right-MDl",0,170,127,0],
        [8213,"Right-MDm",170,170,127,0],
        [8215,"Right-MGN",170,255,127,0],
        [8216,"Right-MV(Re)",0,0,255,0],
        [8217,"Right-Pc",170,0,255,0],
        [8218,"Right-Pf",0,85,255,0],
        [8219,"Right-Pt",170,85,255,0],
        [8220,"Right-PuA",0,170,255,0],
        [8221,"Right-PuI",170,170,255,0],
        [8222,"Right-PuL",0,255,255,0],
        [8223,"Right-PuM",170,255,255,0],
        [8225,"Right-R",255,0,0,0],
        [8226,"Right-VA",85,85,0,0],
        [8227,"Right-VAmc",255,85,0,0],
        [8228,"Right-VLa",85,170,0,0],
        [8229,"Right-VLp",255,170,0,0],
        [8230,"Right-VM",85,255,0,0],
        [8233,"Right-VPL",255,0,255,0],
        [8234,"Right-PaV",120,18,134,0],
        [9000,"ctx-lh-prefrontal",50,100,30,0],
        [9001,"ctx-lh-primary-motor",30,100,45,0],
        [9002,"ctx-lh-premotor",130,100,165,0],
        [9003,"ctx-lh-temporal",105,25,5,0],
        [9004,"ctx-lh-posterior-parietal",125,70,55,0],
        [9005,"ctx-lh-prim-sec-somatosensory",225,20,105,0],
        [9006,"ctx-lh-occipital",225,20,15,0],
        [9500,"ctx-rh-prefrontal",50,200,30,0],
        [9501,"ctx-rh-primary-motor",30,150,45,0],
        [9502,"ctx-rh-premotor",130,150,165,0],
        [9503,"ctx-rh-temporal",105,75,5,0],
        [9504,"ctx-rh-posterior-parietal",125,120,55,0],
        [9505,"ctx-rh-prim-sec-somatosensory",225,70,105,0],
        [9506,"ctx-rh-occipital",225,70,15,0],
        [11100,"ctx_lh_Unknown",0,0,0,0],
        [11101,"ctx_lh_G_and_S_frontomargin",23,220,60,0],
        [11102,"ctx_lh_G_and_S_occipital_inf",23,60,180,0],
        [11103,"ctx_lh_G_and_S_paracentral",63,100,60,0],
        [11104,"ctx_lh_G_and_S_subcentral",63,20,220,0],
        [11105,"ctx_lh_G_and_S_transv_frontopol",13,0,250,0],
        [11106,"ctx_lh_G_and_S_cingul-Ant",26,60,0,0],
        [11107,"ctx_lh_G_and_S_cingul-Mid-Ant",26,60,75,0],
        [11108,"ctx_lh_G_and_S_cingul-Mid-Post",26,60,150,0],
        [11109,"ctx_lh_G_cingul-Post-dorsal",25,60,250,0],
        [11110,"ctx_lh_G_cingul-Post-ventral",60,25,25,0],
        [11111,"ctx_lh_G_cuneus",180,20,20,0],
        [11112,"ctx_lh_G_front_inf-Opercular",220,20,100,0],
        [11113,"ctx_lh_G_front_inf-Orbital",140,60,60,0],
        [11114,"ctx_lh_G_front_inf-Triangul",180,220,140,0],
        [11115,"ctx_lh_G_front_middle",140,100,180,0],
        [11116,"ctx_lh_G_front_sup",180,20,140,0],
        [11117,"ctx_lh_G_Ins_lg_and_S_cent_ins",23,10,10,0],
        [11118,"ctx_lh_G_insular_short",225,140,140,0],
        [11119,"ctx_lh_G_occipital_middle",180,60,180,0],
        [11120,"ctx_lh_G_occipital_sup",20,220,60,0],
        [11121,"ctx_lh_G_oc-temp_lat-fusifor",60,20,140,0],
        [11122,"ctx_lh_G_oc-temp_med-Lingual",220,180,140,0],
        [11123,"ctx_lh_G_oc-temp_med-Parahip",65,100,20,0],
        [11124,"ctx_lh_G_orbital",220,60,20,0],
        [11125,"ctx_lh_G_pariet_inf-Angular",20,60,220,0],
        [11126,"ctx_lh_G_pariet_inf-Supramar",100,100,60,0],
        [11127,"ctx_lh_G_parietal_sup",220,180,220,0],
        [11128,"ctx_lh_G_postcentral",20,180,140,0],
        [11129,"ctx_lh_G_precentral",60,140,180,0],
        [11130,"ctx_lh_G_precuneus",25,20,140,0],
        [11131,"ctx_lh_G_rectus",20,60,100,0],
        [11132,"ctx_lh_G_subcallosal",60,220,20,0],
        [11133,"ctx_lh_G_temp_sup-G_T_transv",60,60,220,0],
        [11134,"ctx_lh_G_temp_sup-Lateral",220,60,220,0],
        [11135,"ctx_lh_G_temp_sup-Plan_polar",65,220,60,0],
        [11136,"ctx_lh_G_temp_sup-Plan_tempo",25,140,20,0],
        [11137,"ctx_lh_G_temporal_inf",220,220,100,0],
        [11138,"ctx_lh_G_temporal_middle",180,60,60,0],
        [11139,"ctx_lh_Lat_Fis-ant-Horizont",61,20,220,0],
        [11140,"ctx_lh_Lat_Fis-ant-Vertical",61,20,60,0],
        [11141,"ctx_lh_Lat_Fis-post",61,60,100,0],
        [11142,"ctx_lh_Medial_wall",25,25,25,0],
        [11143,"ctx_lh_Pole_occipital",140,20,60,0],
        [11144,"ctx_lh_Pole_temporal",220,180,20,0],
        [11145,"ctx_lh_S_calcarine",63,180,180,0],
        [11146,"ctx_lh_S_central",221,20,10,0],
        [11147,"ctx_lh_S_cingul-Marginalis",221,20,100,0],
        [11148,"ctx_lh_S_circular_insula_ant",221,60,140,0],
        [11149,"ctx_lh_S_circular_insula_inf",221,20,220,0],
        [11150,"ctx_lh_S_circular_insula_sup",61,220,220,0],
        [11151,"ctx_lh_S_collat_transv_ant",100,200,200,0],
        [11152,"ctx_lh_S_collat_transv_post",10,200,200,0],
        [11153,"ctx_lh_S_front_inf",221,220,20,0],
        [11154,"ctx_lh_S_front_middle",141,20,100,0],
        [11155,"ctx_lh_S_front_sup",61,220,100,0],
        [11156,"ctx_lh_S_interm_prim-Jensen",141,60,20,0],
        [11157,"ctx_lh_S_intrapariet_and_P_trans",143,20,220,0],
        [11158,"ctx_lh_S_oc_middle_and_Lunatus",101,60,220,0],
        [11159,"ctx_lh_S_oc_sup_and_transversal",21,20,140,0],
        [11160,"ctx_lh_S_occipital_ant",61,20,180,0],
        [11161,"ctx_lh_S_oc-temp_lat",221,140,20,0],
        [11162,"ctx_lh_S_oc-temp_med_and_Lingual",141,100,220,0],
        [11163,"ctx_lh_S_orbital_lateral",221,100,20,0],
        [11164,"ctx_lh_S_orbital_med-olfact",181,200,20,0],
        [11165,"ctx_lh_S_orbital-H_Shaped",101,20,20,0],
        [11166,"ctx_lh_S_parieto_occipital",101,100,180,0],
        [11167,"ctx_lh_S_pericallosal",181,220,20,0],
        [11168,"ctx_lh_S_postcentral",21,140,200,0],
        [11169,"ctx_lh_S_precentral-inf-part",21,20,240,0],
        [11170,"ctx_lh_S_precentral-sup-part",21,20,200,0],
        [11171,"ctx_lh_S_suborbital",21,20,60,0],
        [11172,"ctx_lh_S_subparietal",101,60,60,0],
        [11173,"ctx_lh_S_temporal_inf",21,180,180,0],
        [11174,"ctx_lh_S_temporal_sup",223,220,60,0],
        [11175,"ctx_lh_S_temporal_transverse",221,60,60,0],
        [12100,"ctx_rh_Unknown",0,0,0,0],
        [12101,"ctx_rh_G_and_S_frontomargin",23,220,60,0],
        [12102,"ctx_rh_G_and_S_occipital_inf",23,60,180,0],
        [12103,"ctx_rh_G_and_S_paracentral",63,100,60,0],
        [12104,"ctx_rh_G_and_S_subcentral",63,20,220,0],
        [12105,"ctx_rh_G_and_S_transv_frontopol",13,0,250,0],
        [12106,"ctx_rh_G_and_S_cingul-Ant",26,60,0,0],
        [12107,"ctx_rh_G_and_S_cingul-Mid-Ant",26,60,75,0],
        [12108,"ctx_rh_G_and_S_cingul-Mid-Post",26,60,150,0],
        [12109,"ctx_rh_G_cingul-Post-dorsal",25,60,250,0],
        [12110,"ctx_rh_G_cingul-Post-ventral",60,25,25,0],
        [12111,"ctx_rh_G_cuneus",180,20,20,0],
        [12112,"ctx_rh_G_front_inf-Opercular",220,20,100,0],
        [12113,"ctx_rh_G_front_inf-Orbital",140,60,60,0],
        [12114,"ctx_rh_G_front_inf-Triangul",180,220,140,0],
        [12115,"ctx_rh_G_front_middle",140,100,180,0],
        [12116,"ctx_rh_G_front_sup",180,20,140,0],
        [12117,"ctx_rh_G_Ins_lg_and_S_cent_ins",23,10,10,0],
        [12118,"ctx_rh_G_insular_short",225,140,140,0],
        [12119,"ctx_rh_G_occipital_middle",180,60,180,0],
        [12120,"ctx_rh_G_occipital_sup",20,220,60,0],
        [12121,"ctx_rh_G_oc-temp_lat-fusifor",60,20,140,0],
        [12122,"ctx_rh_G_oc-temp_med-Lingual",220,180,140,0],
        [12123,"ctx_rh_G_oc-temp_med-Parahip",65,100,20,0],
        [12124,"ctx_rh_G_orbital",220,60,20,0],
        [12125,"ctx_rh_G_pariet_inf-Angular",20,60,220,0],
        [12126,"ctx_rh_G_pariet_inf-Supramar",100,100,60,0],
        [12127,"ctx_rh_G_parietal_sup",220,180,220,0],
        [12128,"ctx_rh_G_postcentral",20,180,140,0],
        [12129,"ctx_rh_G_precentral",60,140,180,0],
        [12130,"ctx_rh_G_precuneus",25,20,140,0],
        [12131,"ctx_rh_G_rectus",20,60,100,0],
        [12132,"ctx_rh_G_subcallosal",60,220,20,0],
        [12133,"ctx_rh_G_temp_sup-G_T_transv",60,60,220,0],
        [12134,"ctx_rh_G_temp_sup-Lateral",220,60,220,0],
        [12135,"ctx_rh_G_temp_sup-Plan_polar",65,220,60,0],
        [12136,"ctx_rh_G_temp_sup-Plan_tempo",25,140,20,0],
        [12137,"ctx_rh_G_temporal_inf",220,220,100,0],
        [12138,"ctx_rh_G_temporal_middle",180,60,60,0],
        [12139,"ctx_rh_Lat_Fis-ant-Horizont",61,20,220,0],
        [12140,"ctx_rh_Lat_Fis-ant-Vertical",61,20,60,0],
        [12141,"ctx_rh_Lat_Fis-post",61,60,100,0],
        [12142,"ctx_rh_Medial_wall",25,25,25,0],
        [12143,"ctx_rh_Pole_occipital",140,20,60,0],
        [12144,"ctx_rh_Pole_temporal",220,180,20,0],
        [12145,"ctx_rh_S_calcarine",63,180,180,0],
        [12146,"ctx_rh_S_central",221,20,10,0],
        [12147,"ctx_rh_S_cingul-Marginalis",221,20,100,0],
        [12148,"ctx_rh_S_circular_insula_ant",221,60,140,0],
        [12149,"ctx_rh_S_circular_insula_inf",221,20,220,0],
        [12150,"ctx_rh_S_circular_insula_sup",61,220,220,0],
        [12151,"ctx_rh_S_collat_transv_ant",100,200,200,0],
        [12152,"ctx_rh_S_collat_transv_post",10,200,200,0],
        [12153,"ctx_rh_S_front_inf",221,220,20,0],
        [12154,"ctx_rh_S_front_middle",141,20,100,0],
        [12155,"ctx_rh_S_front_sup",61,220,100,0],
        [12156,"ctx_rh_S_interm_prim-Jensen",141,60,20,0],
        [12157,"ctx_rh_S_intrapariet_and_P_trans",143,20,220,0],
        [12158,"ctx_rh_S_oc_middle_and_Lunatus",101,60,220,0],
        [12159,"ctx_rh_S_oc_sup_and_transversal",21,20,140,0],
        [12160,"ctx_rh_S_occipital_ant",61,20,180,0],
        [12161,"ctx_rh_S_oc-temp_lat",221,140,20,0],
        [12162,"ctx_rh_S_oc-temp_med_and_Lingual",141,100,220,0],
        [12163,"ctx_rh_S_orbital_lateral",221,100,20,0],
        [12164,"ctx_rh_S_orbital_med-olfact",181,200,20,0],
        [12165,"ctx_rh_S_orbital-H_Shaped",101,20,20,0],
        [12166,"ctx_rh_S_parieto_occipital",101,100,180,0],
        [12167,"ctx_rh_S_pericallosal",181,220,20,0],
        [12168,"ctx_rh_S_postcentral",21,140,200,0],
        [12169,"ctx_rh_S_precentral-inf-part",21,20,240,0],
        [12170,"ctx_rh_S_precentral-sup-part",21,20,200,0],
        [12171,"ctx_rh_S_suborbital",21,20,60,0],
        [12172,"ctx_rh_S_subparietal",101,60,60,0],
        [12173,"ctx_rh_S_temporal_inf",21,180,180,0],
        [12174,"ctx_rh_S_temporal_sup",223,220,60,0],
        [12175,"ctx_rh_S_temporal_transverse",221,60,60,0],
        [13100,"wm_lh_Unknown",0,0,0,0],
        [13101,"wm_lh_G_and_S_frontomargin",23,220,60,0],
        [13102,"wm_lh_G_and_S_occipital_inf",23,60,180,0],
        [13103,"wm_lh_G_and_S_paracentral",63,100,60,0],
        [13104,"wm_lh_G_and_S_subcentral",63,20,220,0],
        [13105,"wm_lh_G_and_S_transv_frontopol",13,0,250,0],
        [13106,"wm_lh_G_and_S_cingul-Ant",26,60,0,0],
        [13107,"wm_lh_G_and_S_cingul-Mid-Ant",26,60,75,0],
        [13108,"wm_lh_G_and_S_cingul-Mid-Post",26,60,150,0],
        [13109,"wm_lh_G_cingul-Post-dorsal",25,60,250,0],
        [13110,"wm_lh_G_cingul-Post-ventral",60,25,25,0],
        [13111,"wm_lh_G_cuneus",180,20,20,0],
        [13112,"wm_lh_G_front_inf-Opercular",220,20,100,0],
        [13113,"wm_lh_G_front_inf-Orbital",140,60,60,0],
        [13114,"wm_lh_G_front_inf-Triangul",180,220,140,0],
        [13115,"wm_lh_G_front_middle",140,100,180,0],
        [13116,"wm_lh_G_front_sup",180,20,140,0],
        [13117,"wm_lh_G_Ins_lg_and_S_cent_ins",23,10,10,0],
        [13118,"wm_lh_G_insular_short",225,140,140,0],
        [13119,"wm_lh_G_occipital_middle",180,60,180,0],
        [13120,"wm_lh_G_occipital_sup",20,220,60,0],
        [13121,"wm_lh_G_oc-temp_lat-fusifor",60,20,140,0],
        [13122,"wm_lh_G_oc-temp_med-Lingual",220,180,140,0],
        [13123,"wm_lh_G_oc-temp_med-Parahip",65,100,20,0],
        [13124,"wm_lh_G_orbital",220,60,20,0],
        [13125,"wm_lh_G_pariet_inf-Angular",20,60,220,0],
        [13126,"wm_lh_G_pariet_inf-Supramar",100,100,60,0],
        [13127,"wm_lh_G_parietal_sup",220,180,220,0],
        [13128,"wm_lh_G_postcentral",20,180,140,0],
        [13129,"wm_lh_G_precentral",60,140,180,0],
        [13130,"wm_lh_G_precuneus",25,20,140,0],
        [13131,"wm_lh_G_rectus",20,60,100,0],
        [13132,"wm_lh_G_subcallosal",60,220,20,0],
        [13133,"wm_lh_G_temp_sup-G_T_transv",60,60,220,0],
        [13134,"wm_lh_G_temp_sup-Lateral",220,60,220,0],
        [13135,"wm_lh_G_temp_sup-Plan_polar",65,220,60,0],
        [13136,"wm_lh_G_temp_sup-Plan_tempo",25,140,20,0],
        [13137,"wm_lh_G_temporal_inf",220,220,100,0],
        [13138,"wm_lh_G_temporal_middle",180,60,60,0],
        [13139,"wm_lh_Lat_Fis-ant-Horizont",61,20,220,0],
        [13140,"wm_lh_Lat_Fis-ant-Vertical",61,20,60,0],
        [13141,"wm_lh_Lat_Fis-post",61,60,100,0],
        [13142,"wm_lh_Medial_wall",25,25,25,0],
        [13143,"wm_lh_Pole_occipital",140,20,60,0],
        [13144,"wm_lh_Pole_temporal",220,180,20,0],
        [13145,"wm_lh_S_calcarine",63,180,180,0],
        [13146,"wm_lh_S_central",221,20,10,0],
        [13147,"wm_lh_S_cingul-Marginalis",221,20,100,0],
        [13148,"wm_lh_S_circular_insula_ant",221,60,140,0],
        [13149,"wm_lh_S_circular_insula_inf",221,20,220,0],
        [13150,"wm_lh_S_circular_insula_sup",61,220,220,0],
        [13151,"wm_lh_S_collat_transv_ant",100,200,200,0],
        [13152,"wm_lh_S_collat_transv_post",10,200,200,0],
        [13153,"wm_lh_S_front_inf",221,220,20,0],
        [13154,"wm_lh_S_front_middle",141,20,100,0],
        [13155,"wm_lh_S_front_sup",61,220,100,0],
        [13156,"wm_lh_S_interm_prim-Jensen",141,60,20,0],
        [13157,"wm_lh_S_intrapariet_and_P_trans",143,20,220,0],
        [13158,"wm_lh_S_oc_middle_and_Lunatus",101,60,220,0],
        [13159,"wm_lh_S_oc_sup_and_transversal",21,20,140,0],
        [13160,"wm_lh_S_occipital_ant",61,20,180,0],
        [13161,"wm_lh_S_oc-temp_lat",221,140,20,0],
        [13162,"wm_lh_S_oc-temp_med_and_Lingual",141,100,220,0],
        [13163,"wm_lh_S_orbital_lateral",221,100,20,0],
        [13164,"wm_lh_S_orbital_med-olfact",181,200,20,0],
        [13165,"wm_lh_S_orbital-H_Shaped",101,20,20,0],
        [13166,"wm_lh_S_parieto_occipital",101,100,180,0],
        [13167,"wm_lh_S_pericallosal",181,220,20,0],
        [13168,"wm_lh_S_postcentral",21,140,200,0],
        [13169,"wm_lh_S_precentral-inf-part",21,20,240,0],
        [13170,"wm_lh_S_precentral-sup-part",21,20,200,0],
        [13171,"wm_lh_S_suborbital",21,20,60,0],
        [13172,"wm_lh_S_subparietal",101,60,60,0],
        [13173,"wm_lh_S_temporal_inf",21,180,180,0],
        [13174,"wm_lh_S_temporal_sup",223,220,60,0],
        [13175,"wm_lh_S_temporal_transverse",221,60,60,0],
        [14100,"wm_rh_Unknown",0,0,0,0],
        [14101,"wm_rh_G_and_S_frontomargin",23,220,60,0],
        [14102,"wm_rh_G_and_S_occipital_inf",23,60,180,0],
        [14103,"wm_rh_G_and_S_paracentral",63,100,60,0],
        [14104,"wm_rh_G_and_S_subcentral",63,20,220,0],
        [14105,"wm_rh_G_and_S_transv_frontopol",13,0,250,0],
        [14106,"wm_rh_G_and_S_cingul-Ant",26,60,0,0],
        [14107,"wm_rh_G_and_S_cingul-Mid-Ant",26,60,75,0],
        [14108,"wm_rh_G_and_S_cingul-Mid-Post",26,60,150,0],
        [14109,"wm_rh_G_cingul-Post-dorsal",25,60,250,0],
        [14110,"wm_rh_G_cingul-Post-ventral",60,25,25,0],
        [14111,"wm_rh_G_cuneus",180,20,20,0],
        [14112,"wm_rh_G_front_inf-Opercular",220,20,100,0],
        [14113,"wm_rh_G_front_inf-Orbital",140,60,60,0],
        [14114,"wm_rh_G_front_inf-Triangul",180,220,140,0],
        [14115,"wm_rh_G_front_middle",140,100,180,0],
        [14116,"wm_rh_G_front_sup",180,20,140,0],
        [14117,"wm_rh_G_Ins_lg_and_S_cent_ins",23,10,10,0],
        [14118,"wm_rh_G_insular_short",225,140,140,0],
        [14119,"wm_rh_G_occipital_middle",180,60,180,0],
        [14120,"wm_rh_G_occipital_sup",20,220,60,0],
        [14121,"wm_rh_G_oc-temp_lat-fusifor",60,20,140,0],
        [14122,"wm_rh_G_oc-temp_med-Lingual",220,180,140,0],
        [14123,"wm_rh_G_oc-temp_med-Parahip",65,100,20,0],
        [14124,"wm_rh_G_orbital",220,60,20,0],
        [14125,"wm_rh_G_pariet_inf-Angular",20,60,220,0],
        [14126,"wm_rh_G_pariet_inf-Supramar",100,100,60,0],
        [14127,"wm_rh_G_parietal_sup",220,180,220,0],
        [14128,"wm_rh_G_postcentral",20,180,140,0],
        [14129,"wm_rh_G_precentral",60,140,180,0],
        [14130,"wm_rh_G_precuneus",25,20,140,0],
        [14131,"wm_rh_G_rectus",20,60,100,0],
        [14132,"wm_rh_G_subcallosal",60,220,20,0],
        [14133,"wm_rh_G_temp_sup-G_T_transv",60,60,220,0],
        [14134,"wm_rh_G_temp_sup-Lateral",220,60,220,0],
        [14135,"wm_rh_G_temp_sup-Plan_polar",65,220,60,0],
        [14136,"wm_rh_G_temp_sup-Plan_tempo",25,140,20,0],
        [14137,"wm_rh_G_temporal_inf",220,220,100,0],
        [14138,"wm_rh_G_temporal_middle",180,60,60,0],
        [14139,"wm_rh_Lat_Fis-ant-Horizont",61,20,220,0],
        [14140,"wm_rh_Lat_Fis-ant-Vertical",61,20,60,0],
        [14141,"wm_rh_Lat_Fis-post",61,60,100,0],
        [14142,"wm_rh_Medial_wall",25,25,25,0],
        [14143,"wm_rh_Pole_occipital",140,20,60,0],
        [14144,"wm_rh_Pole_temporal",220,180,20,0],
        [14145,"wm_rh_S_calcarine",63,180,180,0],
        [14146,"wm_rh_S_central",221,20,10,0],
        [14147,"wm_rh_S_cingul-Marginalis",221,20,100,0],
        [14148,"wm_rh_S_circular_insula_ant",221,60,140,0],
        [14149,"wm_rh_S_circular_insula_inf",221,20,220,0],
        [14150,"wm_rh_S_circular_insula_sup",61,220,220,0],
        [14151,"wm_rh_S_collat_transv_ant",100,200,200,0],
        [14152,"wm_rh_S_collat_transv_post",10,200,200,0],
        [14153,"wm_rh_S_front_inf",221,220,20,0],
        [14154,"wm_rh_S_front_middle",141,20,100,0],
        [14155,"wm_rh_S_front_sup",61,220,100,0],
        [14156,"wm_rh_S_interm_prim-Jensen",141,60,20,0],
        [14157,"wm_rh_S_intrapariet_and_P_trans",143,20,220,0],
        [14158,"wm_rh_S_oc_middle_and_Lunatus",101,60,220,0],
        [14159,"wm_rh_S_oc_sup_and_transversal",21,20,140,0],
        [14160,"wm_rh_S_occipital_ant",61,20,180,0],
        [14161,"wm_rh_S_oc-temp_lat",221,140,20,0],
        [14162,"wm_rh_S_oc-temp_med_and_Lingual",141,100,220,0],
        [14163,"wm_rh_S_orbital_lateral",221,100,20,0],
        [14164,"wm_rh_S_orbital_med-olfact",181,200,20,0],
        [14165,"wm_rh_S_orbital-H_Shaped",101,20,20,0],
        [14166,"wm_rh_S_parieto_occipital",101,100,180,0],
        [14167,"wm_rh_S_pericallosal",181,220,20,0],
        [14168,"wm_rh_S_postcentral",21,140,200,0],
        [14169,"wm_rh_S_precentral-inf-part",21,20,240,0],
        [14170,"wm_rh_S_precentral-sup-part",21,20,200,0],
        [14171,"wm_rh_S_suborbital",21,20,60,0],
        [14172,"wm_rh_S_subparietal",101,60,60,0],
        [14173,"wm_rh_S_temporal_inf",21,180,180,0],
        [14174,"wm_rh_S_temporal_sup",223,220,60,0],
        [14175,"wm_rh_S_temporal_transverse",221,60,60,0]),
        dtype="object")