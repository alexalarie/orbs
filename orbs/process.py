#!/usr/bin/python
# *-* coding: utf-8 *-*
# Author: Thomas Martin <thomas.martin.1@ulaval.ca>
# File: process.py

## Copyright (c) 2010-2014 Thomas Martin <thomas.martin.1@ulaval.ca>
## 
## This file is part of ORBS
##
## ORBS is free software: you can redistribute it and/or modify it
## under the terms of the GNU General Public License as published by
## the Free Software Foundation, either version 3 of the License, or
## (at your option) any later version.
##
## ORBS is distributed in the hope that it will be useful, but WITHOUT
## ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
## or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public
## License for more details.
##
## You should have received a copy of the GNU General Public License
## along with ORBS.  If not, see <http://www.gnu.org/licenses/>.

"""
Process module contains all the processing classes of ORBS.
"""

__author__ = "Thomas Martin"
__licence__ = "Thomas Martin (thomas.martin.1@ulaval.ca)"                      
__docformat__ = 'reStructuredText'
import version
__version__ = version.__version__

from orb.core import Tools, Cube, ProgressBar, TextColor
import orb.utils
import orb.astrometry
import orb.constants
from orb.astrometry import Astrometry, Gaussian, Aligner

import os
import numpy as np
import math
from scipy import optimize, interpolate

import astropy.io.fits as pyfits
import astropy.wcs as pywcs


##################################################
#### CLASS RawData ###############################
##################################################

class RawData(Cube):
    """ORBS raw data processing class.

    .. note:: Raw data is the output data of SpIOMM/SITELLE without
      any kind of processing.
    """

    cr_map = None
    alignment_vector = None

    def _get_alignment_vector_path(self, err=False):
        """Return the default path to the alignment vector.

        :param err: (Optional) If True, the error vector path is
          returned (default False).
        """
        if not err:
            return self._data_path_hdr + "alignment_vector.fits"
        else:
            return self._data_path_hdr + "alignment_vector_err.fits"

    def _get_alignment_vector_header(self, err=False):
        """Return the header of the alignment vector.

        :param err: (Optional) If True, the error vector header is
          returned (default False).
        """
        if not err:
            return (self._get_basic_header('Alignment vector')
                    + self._project_header)
        else:
            return (self._get_basic_header('Alignment vector error')
                    + self._project_header) 
    
    def _get_cr_map_frame_path(self, index):
        """Return the default path to a frame of the cosmic ray map.

        :param index: Index of the frame"""
        formatted_index = "%(#)04d" %{"#":index}
        crmap_dirname = os.path.dirname(self._data_path_hdr)
        crmap_basename = os.path.basename(self._data_path_hdr)
        return (crmap_dirname + os.sep + "CRMAP" + os.sep
                + crmap_basename + "cr_map" 
                + str(formatted_index) + ".fits")

    def _get_cr_map_frame_header(self):
        """Return the header of the cosmic ray map."""
        return (self._get_basic_header('Cosmic ray map')
                + self._project_header)

    def _get_cr_map_list_path(self):
        """Return  the default path to the cosmic ray map list"""
        return self._data_path_hdr + "cr_map.list"
    
    def _get_hp_map_path(self):
        """Return the default path to the hot pixels map."""
        return self._data_path_hdr + "hp_map.fits"

    def _get_deep_frame_path(self):
        """Return the default path to the deep frame."""
        return self._data_path_hdr + "deep_frame.fits"

    def _get_deep_frame_header(self):
        """Return the header of the deep frame."""
        return (self._get_basic_header('Deep frame')
                + self._project_header
                + self._get_basic_frame_header(self.dimx, self.dimy))

    def _get_energy_map_path(self):
        """Return the default path to the energy map."""
        return self._data_path_hdr + "energy_map.fits"

    def _get_energy_map_header(self):
        """Return the header of the energy map."""
        return (self._get_basic_header('Energy Map')
                + self._project_header
                + self._get_basic_frame_header(self.dimx, self.dimy))

    def _get_interfero_frame_path(self, index):
        """Return the default path to the interferogram frames.

        :param index: The index of the interferogram frame.
        """
        formatted_index = "%(#)04d" %{"#":index}
        interfero_dirname = os.path.dirname(self._data_path_hdr)
        interfero_basename = os.path.basename(self._data_path_hdr)
        return (interfero_dirname + "/INTERFEROGRAM/" 
                + interfero_basename + "interferogram" 
                + str(formatted_index) + ".fits")

    def _get_interfero_frame_header(self):
        """Return the header of an interferogram frame"""
        return (self._get_basic_header('Interferogram frame')
                + self._project_header
                + self._get_basic_frame_header(self.dimx, self.dimy))

    def _get_interfero_list_path(self):
        """Return the default path to the list of the interferogram
        cube"""
        return self._data_path_hdr + "interf.list"

    def _get_master_path(self, kind):
        """Return the default path to a master frame.

        :param kind: Kind of master frame (e.g. : 'bias', 'dark',
          'flat')
        """
        return self._data_path_hdr + "master_%s.fits"%kind

    def _get_master_header(self, kind):
        """Return the header of a master frame.
        
        :param kind: Kind of master frame (e.g. : 'bias', 'dark',
          'flat')
        """
        return (self._get_basic_header('Master %s'%kind)
                + self._project_header
                + self._get_basic_frame_header(self.dimx, self.dimy))

    def _load_bias(self, bias_list_path, return_temperature=False,
                   combine='average', reject='avsigclip'):
        """Return a master bias.

        :param bias_list_path: Path to the list of bias frames

        :param return_temperature: If True return also the mean
          temperature of the bias frames. Note that the header of the
          files must have the keyword 'CCD_TEMP'. Return None if the
          temperatures could not be read.

        :param reject: (Optional) Rejection operation. Can be
          'sigclip', 'minmax', 'avsigclip' or None (default
          'avsigclip'). See
          :py:meth:`orb.utils.create_master_frame`.
        
        :param combine: (Optional) Combining operation. Can be
          'average' or 'median' (default 'average'). See
          :py:meth:`orb.utils.create_master_frame`.

        .. note:: Bias images are resized if x and y dimensions of the
            flat images are not equal to the cube dimensions.

        .. seealso:: :py:meth:`orb.utils.create_master_frame`
        """
        bias_cube = Cube(bias_list_path,
                         config_file_name=self.config_file_name)
        self._print_msg('Creating Master Bias')
        # try to read temperatures in the header of each bias and
        # return the mean
        if return_temperature:
            temp_list = list()
            error = False
            for ibias in range(bias_cube.dimz):
                try:
                    temp_list.append(
                        bias_cube.get_frame_header(ibias)['CCD-TEMP'])
                except:
                    error = True
                
            if len(temp_list) == 0:
                self._print_warning("Bias temperatures could not be read. Check presence of the keyword 'CCD-TEMP'")
                bias_temp = None
            else:
                bias_temp = np.mean(temp_list)
                self._print_msg(
                    "Master bias mean temperature : %f C"%bias_temp)
                if error:
                    self._print_warning("Some of the bias temperatures could not be read. Check presence of the keyword 'CCD-TEMP'")

        # Create master bias
        # Resizing if nescessary (Warning this must be avoided)
        if self.is_same_2D_size(bias_cube):
            bias_frames = bias_cube.get_all_data()   
        else:
            self._print_warning("Bad bias cube dimensions : resizing data")
            bias_frames = bias_cube.get_resized_data(self.dimx, self.dimy)

        if not self.BIG_DATA:
            master_bias = orb.utils.create_master_frame(bias_frames,
                                                        combine=combine,
                                                        reject=reject)
        else:
            master_bias = orb.utils.pp_create_master_frame(bias_frames,
                                                           combine=combine,
                                                           reject=reject)
        
            
        self.write_fits(self._get_master_path('bias'),
                        master_bias, overwrite=True,
                        fits_header=self._get_master_header('Bias'))
        
        if return_temperature:
            return master_bias, bias_temp
        else:
            return master_bias

    def _load_dark(self, dark_list_path, return_temperature=False,
                   combine='average', reject='avsigclip'):
        """Return a master dark.
            
        :param dark_list_path: Path to the list of dark frames

        :param return_temperature: If True return also the mean
          temperature of the dark frames. Note that the header of the
          files must have the keyword 'CCD_TEMP'. Return None if the
          temperatures could not be read.

        :param reject: (Optional) Rejection operation. Can be
          'sigclip', 'minmax', 'avsigclip' or None (default
          'avsigclip'). See
          :py:meth:`orb.utils.create_master_frame`.
        
        :param combine: (Optional) Combining operation. Can be
          'average' or 'median' (default 'average'). See
          :py:meth:`orb.utils.create_master_frame`.

        .. note:: Dark images are resized if x and y dimensions of the
            flat images are not equal to the cube dimensions.

        .. seealso:: :py:meth:`orb.utils.create_master_frame`
        """
        dark_cube = Cube(dark_list_path,
                         config_file_name=self.config_file_name)
        self._print_msg('Creating Master Dark')

        # try to read temperatures in the header of each dark and
        # return the mean
        if return_temperature:
            temp_list = list()
            error = False
            for idark in range(dark_cube.dimz):
                try:
                    temp_list.append(
                        dark_cube.get_frame_header(idark)['CCD-TEMP'])
                except:
                    error = True
                
            if len(temp_list) == 0:
                self._print_warning("Dark temperatures could not be read. Check presence of the keyword 'CCD-TEMP'")
                dark_temp = None
            else:
                dark_temp = np.mean(temp_list)
                self._print_msg(
                    "Master dark mean temperature : %f C"%dark_temp)
                if error:
                    self._print_warning("Some of the dark temperatures could not be read. Check presence of the keyword 'CCD-TEMP'")

        # Resizing operation if nescessary (this must be avoided)
        if self.is_same_2D_size(dark_cube):
            dark_frames = dark_cube.get_all_data().astype(float)
            
        else:
            self._print_warning("Bad dark cube dimensions : resizing data")
            dark_frames = dark_cube.get_resized_data(self.dimx, self.dimy)

        # Create master dark
        if not self.BIG_DATA:
            master_dark = orb.utils.create_master_frame(dark_frames,
                                                        combine=combine,
                                                        reject=reject)
        else:
            master_dark = orb.utils.pp_create_master_frame(dark_frames,
                                                           combine=combine,
                                                           reject=reject)

        # Write master dark
        self.write_fits(self._get_master_path('dark'),
                        master_dark, overwrite=True,
                        fits_header=self._get_master_header('Dark'))
            
        if return_temperature:
            return master_dark, dark_temp
        else:
            return master_dark

    def _load_flat(self, flat_list_path, combine='average', reject='avsigclip',
                   smooth_deg=0):
        """Return a master flat.

        :param flat_list_path: Path to the list of flat frames
        
        :param reject: (Optional) Rejection operation. Can be
          'sigclip', 'minmax', 'avsigclip' or None (default
          'avsigclip'). See
          :py:meth:`orb.utils.create_master_frame`.
        
        :param combine: (Optional) Combining operation. Can be
          'average' or 'median' (default 'average'). See
          :py:meth:`orb.utils.create_master_frame`.

        :param smooth_deg: (Optional) If > 0 smooth the master flat (help
          removing possible fringe pattern) (default 0).

        .. note:: Flat images are resized if the x and y dimensions of
            the flat images are not equal to the cube dimensions.

        .. seealso:: :py:meth:`orb.utils.create_master_frame`
        """
        flat_cube = Cube(flat_list_path,
                         config_file_name=self.config_file_name)
        self._print_msg('Creating Master Flat')
        
        # resizing if nescessary
        if self.is_same_2D_size(flat_cube):   
            flat_frames = flat_cube.get_all_data().astype(float)
            
        else:
            self._print_warning("Bad flat cube dimensions : resizing data")
            flat_frames = flat_cube.get_resized_data(self.dimx, self.dimy)

        # create master flat
        if not self.BIG_DATA:
            master_flat = orb.utils.create_master_frame(flat_frames,
                                                        combine=combine,
                                                        reject=reject)
        else:
            master_flat = orb.utils.pp_create_master_frame(flat_frames,
                                                           combine=combine,
                                                           reject=reject)

        if smooth_deg > 0:
            master_flat = orb.utils.low_pass_image_filter(master_flat,
                                                          smooth_deg)
            self._print_warning('Master flat smoothed (Degree: %d)'%smooth_deg)


        # write master flat
        self.write_fits(self._get_master_path('flat'),
                        master_flat, overwrite=True,
                        fits_header=self._get_master_header('Flat'))

        return master_flat
            
    def _load_alignment_vector(self, alignment_vector_path):
        """Load the alignment vector.
          
        :param alignment_vector_path: Path to the alignment vector file.
        """
        self._print_msg("Loading alignment vector")
        alignment_vector = self.read_fits(alignment_vector_path, no_error=True)
        if (alignment_vector is not None):
            if (alignment_vector.shape[0] == self.dimz):
                self._print_msg("Alignment vector loaded")
                return alignment_vector
            else:
                self._print_error("Alignment vector dimensions are not compatible")
                return None
        else:
            self._print_warning("Alignment vector not loaded")
            return None

    def add_missing_frames(self, step_number):
        """Add non taken frames at the end of a cube in order to
        complete it and have a centered ZDP. Useful when a cube could
        not be completed during the night.

        :param step_number: Number of steps for a full cube.
        """
        if step_number > self.dimz:
            zeros_frame = np.zeros((self.dimx, self.dimy), dtype=float)
            image_list_text = ""
            for iframe in range(step_number):
                image_list_text += self._get_interfero_frame_path(iframe) + "\n"
                if iframe >= self.dimz:
                    self.write_fits(
                        self._get_interfero_frame_path(iframe), 
                        zeros_frame,
                        fits_header=self._get_interfero_frame_header(),
                        overwrite=self.overwrite,
                        mask=zeros_frame)
            f = open(self._get_interfero_list_path(), "w")
            f.write(image_list_text)
            f.close

    def create_alignment_vector(self, star_list_path, init_fwhm_arc,
                                fov, profile_name='gaussian',
                                moffat_beta=3.5, min_coeff=0.3,
                                readout_noise=10., dark_current_level=0.):
        """Create the alignment vector used to compute the
          interferogram from the raw images.

        :param star_list_path: Path to a list of star coordinates that
          will be used to calculates the displacement vector. Please
          refer to :meth:`orb.astrometry.load_star_list` for more
          information about a list of stars.

        :param init_fwhm_arc: Initial guess for the FWHM in arcsec

        :param fov: Field of View along x axis in arcmin

        :param profile_name: (Optional) PSF profile for star
          fitting. Can be 'moffat' or 'gaussian'. See:
          :py:class:`orb.astrometry.Astrometry` (default 'gaussian').

        :param moffat_beta: (Optional) Beta parameter to use for
          moffat PSF (default 3.5).

        :param min_coeff: (Optional) The minimum proportion of stars
            correctly fitted to assume a good enough calculated
            disalignment (default 0.3).
            
        :param readout_noise: (Optional) Readout noise in ADU/pixel
          (can be computed from bias frames: std(master_bias_frame))
          (default 10.)
    
        :param dark_current_level: (Optional) Dark current level in
          ADU/pixel (can be computed from dark frames:
          median(master_dark_frame)) (default 0.)

        .. note:: The alignement vector contains the calculated
           disalignment for each image along x and y axes to the first
           image.
        """
        self._print_msg("Creating alignment vector", color=True)
        # init Astrometry class
        astrom = Astrometry(self, init_fwhm_arc,
                            fov, profile_name=profile_name,
                            moffat_beta=moffat_beta,
                            data_prefix=self._data_prefix,
                            readout_noise=readout_noise,
                            dark_current_level=dark_current_level,
                            logfile_name=self._logfile_name,
                            tuning_parameters=self._tuning_parameters,
                            config_file_name=self.config_file_name)
        astrom.load_star_list(star_list_path)

        # get alignment vectors
        (alignment_vector_x,
         alignment_vector_y,
         alignment_error) = astrom.get_alignment_vectors(fit_cube=True)

        self.alignment_vector = np.array([alignment_vector_x,
                                     alignment_vector_y]).T
        
        alignment_vector_path = self._get_alignment_vector_path()
        alignment_err_vector_path = self._get_alignment_vector_path(err=True)
        self.write_fits(alignment_vector_path, self.alignment_vector, 
                        fits_header=
                        self._get_alignment_vector_header(),
                        overwrite=self.overwrite)
        if self.indexer is not None:
            self.indexer['alignment_vector'] = alignment_vector_path
        self.write_fits(alignment_err_vector_path, np.array(alignment_error), 
                        fits_header=
                        self._get_alignment_vector_header(err=True),
                        overwrite=self.overwrite)
        if self.indexer is not None:
            self.indexer['alignment_err_vector'] = alignment_err_vector_path
    

    def create_cosmic_ray_map(self, z_coeff=3., step_number=None,
                              bad_frames_vector=[], star_list_path=None,
                              stars_fwhm_pix=2.):
        """Find the cosmic rays in the raw images and creates 
        the cosmic ray map used to compute the interferogram.

        :param z_coeff: (Optional) Threshold coefficient for cosmic ray
          detection, lower it to detect more cosmic rays (default : 3.).

        :param step_number: (Optional) 'Full' number of steps if the
          cube was complete. Might be different from the 'real' number
          of steps obtained. Helps in finding ZPD (default None).

        :param bad_frames_vector: (Optional) Contains the index of the
          frames considered as bad(default []).

        :param star_list_path: (Optional) Path to a list of stars that
          must be protected from over detection. All cosmic rays
          detected in those stars will be removed.

        :param stars_fwhm_pix: (Optional) mean FWHM of the stars in
          pixels.

        .. note:: A cosmic ray map is a 'mask like' cube filled with
           zeros and containing a one for each pixel identified as a
           cosmic ray. This cube is stored as a virtual
           **frame-divided** cube
        """


        def predetect_crs_in_column(fdata, z_coeff):
            """predetect CR in a column of filtered data"""

            MAX_VALUES_NB = 2 # Number of max values removed before
                              # computing median and std of the
                              # interferogram. Must be > 0
                              
            MAX_CR = 5 # Maximum pre-detected number of cosmic rays
            
            FFT_CUT = 0.1 # Ratio giving the position of the cut for
                           # FFT filtering
                           
            result = np.zeros_like(fdata, dtype=bool)
            
            for ij in range(fdata.shape[0]):
                test_vector = np.copy(fdata[ij,:])
                    
                # FFT filtering: remove low frequency modes due to
                # misalignment of the frames
                test_vector = orb.utils.fft_filter(test_vector, FFT_CUT,
                                                   width_coeff=0.1)
       
                # median and std computed over the vector without
                # its too deviant values
                max_threshold = np.sort(
                    np.abs(test_vector))[-MAX_VALUES_NB]
                filter_test_vector = test_vector[
                    np.nonzero(np.abs(test_vector) < max_threshold)]
                z_median = orb.utils.robust_median(filter_test_vector, warn=False)
                z_std = orb.utils.robust_std(filter_test_vector, warn=False)
                       
                # CR detection: If too much CRs are pre detected the
                # level of detection is raised
                too_much_cr = True
                while too_much_cr:
                    cr_vector = np.nonzero(test_vector > z_median + 
                                           (z_std * z_coeff))
                    if len(cr_vector[0]) <= MAX_CR:
                        too_much_cr = False
                    else:
                        z_coeff += 0.5
                        
                result[ij,:][cr_vector] = 1
            return result
            

        def check_predected_crs_in_frame(frames, pre_cr_map, ik):
            """Check pre-detected cosmic rays in a frame"""

            MINI_BOX_HSZ = 5 # length degree of the mini box (final
                             # length is 2 * MINI_BOX_HSZ + 1)
                             
            
            REJECT_COEFF = 3.5 # Rejection coefficient 
            
            dimx = frames.shape[0]
            dimy = frames.shape[1]
            
            cr_map = np.zeros((dimx, dimy), dtype=np.bool)
            pre_crs = np.nonzero(pre_cr_map)
            del pre_cr_map
            
            ## checking pre-detected cosmic ray the classic way.
            for icr in range(len(pre_crs[0])):
                ii = pre_crs[0][icr]
                ij = pre_crs[1][icr]

                x_min, x_max, y_min, y_max = orb.utils.get_box_coords(
                    ii, ij, MINI_BOX_HSZ*2+1, 0, dimx, 0, dimy)
                
                box = frames[x_min:x_max, y_min:y_max, ik]

                median_box = np.median(
                    frames[x_min:x_max, y_min:y_max, :], axis=2)
                median_box[np.nonzero(median_box == 0)] = np.nan

                box /= median_box
                tested_pixel = box[ii-x_min, ij-y_min]

                # removing tested pixel to compute mean and std
                stat_box = np.copy(box)
                stat_box[ii-x_min, ij-y_min] = np.nan
                stat_box = np.sort(stat_box.flatten())[:-MINI_BOX_HSZ]
                
                box_median = orb.utils.robust_median(stat_box)
                box_std = orb.utils.robust_std(stat_box)

                # pre-detected cr is finally checked
                if (tested_pixel >
                    box_median + REJECT_COEFF * box_std):
                    cr_map[ii,ij] = True

            return cr_map


        def filter_frame(frame):
            """High pass filter applied on frame to help for cosmic
            ray detection
            """
            return frame - orb.utils.low_pass_image_filter(frame,deg=1)



        def check_cr_frame(frame, cr_map_frame, star_list, stars_fwhm):
            """Check pixels around the detected cosmic rays.
            """
            BASE_COEFF = 1. # Detection coeff
            BOX_SIZE = 3 # Size of the box around the cosmic ray to be
                         # checked

            STAR_BOX_SIZE_COEFF = 10 # Size coefficient of the box
                                    # around a star where all cosmic
                                    # rays are removed.

            star_box_size = math.ceil(STAR_BOX_SIZE_COEFF * stars_fwhm)
        
            dimx = frame.shape[0]
            dimy = frame.shape[1]
            cr_coords = np.nonzero(cr_map_frame)
            
            for icr in range(len(cr_coords[0])):
                ii = cr_coords[0][icr]
                ij = cr_coords[1][icr]
                x_min, x_max, y_min, y_max = orb.utils.get_box_coords(
                        ii, ij, BOX_SIZE, 0, dimx, 0, dimy)
                box = frame[x_min:x_max, y_min:y_max]
                cr_box = cr_map_frame[x_min:x_max, y_min:y_max]
                box_mask = np.zeros_like(box).astype(np.bool)
                box_mask[np.nonzero(cr_box > 0)] = True
                masked_box = np.ma.masked_array(box, mask=box_mask)
                median_box = np.ma.median(masked_box)
                std_box = np.ma.std(masked_box)
                
                # check around to detect adjacent cr
                stat_box = np.zeros_like(box, dtype=bool)
                stat_box[np.nonzero(
                    box > median_box + BASE_COEFF * std_box)] = True
                cr_map_frame[x_min:x_max, y_min:y_max] = stat_box

            # stars used for calibration are protected from cosmic-ray detection
            for istar in range(star_list.shape[0]):
                 ii = star_list[istar,0]
                 ij = star_list[istar,1]
                 x_min, x_max, y_min, y_max = orb.utils.get_box_coords(
                     ii, ij, star_box_size, 0, dimx, 0, dimy)
                 cr_map_frame[x_min:x_max, y_min:y_max] = False
            
            return cr_map_frame
        

        
        self._print_msg("Creating cosmic ray map", color=True)
        self._print_msg("First detection pass", color=True)

        star_list = orb.astrometry.load_star_list(star_list_path)
        
        cr_map = np.empty((self.dimx, self.dimy, self.dimz), dtype=np.bool)

        for iquad in range(0, self.QUAD_NB):
            x_min, x_max, y_min, y_max = self.get_quadrant_dims(iquad)
            iquad_data = self.get_data(x_min, x_max, 
                                       y_min, y_max, 
                                       0, self.dimz)
            quad_dimx = x_max - x_min

            ## Filtering frames first
            # Init multiprocessing server
            job_server, ncpus = self._init_pp_server()
            progress = ProgressBar(self.dimz)
            for iframe in range(0, self.dimz, ncpus):
                progress.update(
                    iframe,
                    info="filtering quad %d/%d"%(iquad+1, self.QUAD_NB))
                if iframe + ncpus >= self.dimz:
                    ncpus = self.dimz - iframe

                jobs = [(ijob, job_server.submit(
                    filter_frame, 
                    args=(iquad_data[:,:,iframe+ijob],),
                    modules=("import numpy as np",
                             "import orb.utils")))
                        for ijob in range(ncpus)]

                for ijob, job in jobs:
                    # filtered data is written in place of non filtered data
                    iquad_data[:,:,iframe+ijob] = job() 
                    
            self._close_pp_server(job_server)
            progress.end()

            ## Predetecting CR
            iquad_pre_cr_map = np.empty_like(iquad_data, dtype=bool)
            
            # Init multiprocessing server
            job_server, ncpus = self._init_pp_server()
        
            progress = ProgressBar(quad_dimx)
            for ii in range(0, quad_dimx, ncpus):
                progress.update(ii, info="CR predetection")
                
                if (ii + ncpus >= quad_dimx):
                    ncpus = quad_dimx - ii
                
                jobs = [(ijob, job_server.submit(
                    predetect_crs_in_column, 
                    args=(iquad_data[ii+ijob,:,:], z_coeff),
                    modules=("import numpy as np",
                             "import orb.utils",)))
                        for ijob in range(ncpus)]
                    
                for ijob, job in jobs:
                    iquad_pre_cr_map[ii+ijob,:,:] = job()
                
            progress.end()
            self._close_pp_server(job_server)
            self._print_msg("%d pre-detected cosmic rays in quad %d/%d"%(
                np.sum(iquad_pre_cr_map), iquad+1, self.QUAD_NB))

            # unfiltered data is reloaded
            iquad_data = self.get_data(x_min, x_max, 
                                       y_min, y_max, 
                                       0, self.dimz)
            
            ## Checking pre-detected CRs the classic way
            Z_STACK = 6
            
            # Init multiprocessing server
            job_server, ncpus = self._init_pp_server()
            progress = ProgressBar(self.dimz)
            for iframe in range(0, self.dimz, ncpus):
                progress.update(
                    iframe,
                    info="checking CRs in frames [%d/%d]"%(
                        iquad+1, self.QUAD_NB))
                if iframe + ncpus >= self.dimz:
                    ncpus = self.dimz - iframe

                z_min_list = list()
                z_max_list = list()
                for ijob in range(ncpus):
                    z_min = iframe + ijob - int(Z_STACK/2)
                    z_max = iframe + ijob + int(Z_STACK/2) + 1
                    if z_min < 0: z_min = 0
                    if z_max > self.dimz: z_max = self.dimz
                    z_min_list.append(z_min)
                    z_max_list.append(z_max)
                
                jobs = [(ijob, job_server.submit(
                    check_predected_crs_in_frame, 
                    args=(iquad_data[:,:,z_min_list[ijob]:z_max_list[ijob]],
                          iquad_pre_cr_map[:,:,iframe+ijob],
                          iframe+ijob-z_min_list[ijob]),
                    modules=("import numpy as np",
                             "import orb.utils")))
                        for ijob in range(ncpus)]

                for ijob, job in jobs:
                    cr_map[x_min:x_max, y_min:y_max, iframe+ijob] = job()
                    
            progress.end()     
            self._close_pp_server(job_server)
            self._print_msg("%d detected cosmic rays in quad %d/%d"%(
                np.sum(cr_map[x_min:x_max, y_min:y_max,:]),
                iquad+1, self.QUAD_NB))
            
        ## Check 'strange' frames with too much CRs
        self._print_msg("Re-checking strange frames", color=True)
        
        STRANGE_DETECT_COEFF = 1.
        CR_BOX_SIZE = 3
        LARGE_BOX_SIZE = 15
        
        cr_by_frame = [np.sum(cr_map[:,:,iz]) for iz in range(cr_map.shape[2])]
        cr_med = np.median(cr_by_frame)
        cr_std = orb.utils.robust_std(cr_by_frame)
        
        strange_frames = list(np.nonzero(
            cr_by_frame > cr_med + STRANGE_DETECT_COEFF * cr_std)[0])

        progress = ProgressBar(np.size(strange_frames))
        frame_nb = 0
        for iframe in strange_frames:
            cr_frame = np.copy(cr_map[:,:,iframe])
            cr_coords = np.nonzero(cr_frame)
            cr_pos = np.array([(cr_coords[0][icr], cr_coords[1][icr])
                                for icr in range(len(cr_coords[0]))])
            frame = self.get_data_frame(iframe)
            for istar in range(cr_pos.shape[0]):
                crx = cr_pos[istar,0]
                cry = cr_pos[istar,1]
                cr_level = frame[crx, cry]
                # define cr box
                x_min, x_max, y_min, y_max = orb.utils.get_box_coords(
                    crx, cry, CR_BOX_SIZE, 0,
                    cr_frame.shape[0], 0, cr_frame.shape[1])
                cr_box = frame[x_min:x_max, y_min:y_max]

                # define a large box around cr box
                x_min, x_max, y_min, y_max = orb.utils.get_box_coords(
                    crx, cry, LARGE_BOX_SIZE, 0,
                    cr_frame.shape[0], 0, cr_frame.shape[1])
                large_box = frame[x_min:x_max, y_min:y_max]

                # test
                large_mean = orb.utils.robust_mean(orb.utils.sigmacut(large_box))
                box_mean = (np.sum(cr_box) - cr_level) / (np.size(cr_box) - 1)
                if box_mean > 2.* large_mean:
                    cr_map[crx,cry,iframe] = 0

                elif cr_level < 2. * box_mean:
                    cr_map[crx,cry,iframe] = 0
                    
            frame_nb += 1
            progress.update(frame_nb, info="checking frame: %d"%iframe)
        progress.end()  
     
        ## Second pass : check around the detected cosmic rays
        self._print_msg("Checking CRs neighbourhood", color=True)
        
        # Init multiprocessing server
        job_server, ncpus = self._init_pp_server()
        progress = ProgressBar(self.dimz)
        for ik in range(0, self.dimz, ncpus):
            # No more jobs than frames to compute
            if (ik + ncpus >= self.dimz): 
                ncpus = self.dimz - ik
                
            frames = np.empty((self.dimx, self.dimy, ncpus), dtype=float)
            for ijob in range(ncpus): 
                frames[:,:,ijob] = self.get_data_frame(ik+ijob)
                
            cr_map_frames = np.copy(cr_map[:,:,ik: ik + ncpus + 1])
            
            jobs = [(ijob, job_server.submit(
                check_cr_frame, 
                args=(frames[:,:,ijob], 
                      cr_map_frames[:,:,ijob],
                      star_list, stars_fwhm_pix),
                modules=("import numpy as np",
                         "import math",
                         "import orb.utils",
                         "import orb.astrometry")))
                    for ijob in range(ncpus)]
            
            for ijob, job in jobs:
                cr_map[:,:,ik + ijob] = job()

            progress.update(ik, info="checking frame: %d"%ik)
            
        self._close_pp_server(job_server)
        progress.end()
        
        self._print_msg("Total number of detected cosmic rays: %d"%np.sum(
            cr_map), color=True)
        
        list_file = self.open_file(self._get_cr_map_list_path())
        
        ## Writing cosmic ray map to disk
        for iframe in range(self.dimz):
            cr_map_path = self._get_cr_map_frame_path(iframe)
            self.write_fits(cr_map_path,
                            cr_map[:,:,iframe].astype(np.uint8), 
                            silent=True,
                            fits_header=
                            self._get_basic_header(file_type="Cosmic ray map"),
                            overwrite=self.overwrite)
            list_file.write(cr_map_path + "\n")
        if self.indexer is not None:
            self.indexer['cr_map_list'] = self._get_cr_map_list_path()

    def check_bad_frames(self, cr_map_list_path=None, coeff=2.):
        """Check an interferogram cube for bad frames.

        If the number of detected cosmic rays is too important the
        frame is considered as bad

        :param cr_map_path: (Optional) Path to the cosmic ray map
        :param coeff: (Optional) Threshold coefficient (Default 2.)
        """
        self._print_msg("Checking bad frames")
        MIN_CR = 30.
        
        # Instanciating cosmic ray map cube
        if (cr_map_list_path is None):
                cr_map_list_path = self._get_cr_map_list_path()
        cr_map_cube = Cube(cr_map_list_path,
                           config_file_name=self.config_file_name)
        cr_map = cr_map_cube.get_all_data()
        cr_map_vector = np.sum(np.sum(cr_map, axis=0), axis=0)
        median_rc = np.median(cr_map_vector)
        pre_bad_frames_vector = np.nonzero(cr_map_vector > median_rc + coeff*median_rc)[0]
        bad_frames_vector = list()
        for ibad_frame in pre_bad_frames_vector:
            if cr_map_vector[ibad_frame] > MIN_CR:
                bad_frames_vector.append(ibad_frame)
        self._print_msg("Detected bad frames : " + str(bad_frames_vector))
        return np.array(bad_frames_vector)

    def create_hot_pixel_map(self, dark_image, bias_image):
        """Create a hot pixel map from a cube of dark frame

        :param bias_image: Master bias frame (can be set to None)
        :param dark_image: Master dark frame
        
        .. note:: A hot pixel map is a mask like frame (1 for a hot
           pixel, 0 elsewhere)"""
        nsigma = 5.0 # Starting sigma
        MIN_COEFF = 0.026 # Min percentage of hot pixels to find

        self._print_msg("Creating hot pixel map")

        if bias_image is not None:
            dark_image = np.copy(dark_image) - np.copy(bias_image)
        hp_map = np.zeros_like(dark_image).astype(np.uint8)
        dark_mean = np.mean(dark_image)
        dark_std = np.std(dark_image)

        nsigma_ok = False
        while not (nsigma_ok):    
            hp_map[np.nonzero(
                dark_image > (dark_mean + nsigma * dark_std))] = 1
            if (np.shape(np.nonzero(hp_map))[1]
                > MIN_COEFF * self.dimx * self.dimy):
                nsigma_ok = True
            else:
                if (nsigma > 0.0):
                    nsigma -= 0.01
                else:
                    nsigma_ok = True
                    hp_map = np.ones_like(dark_image).astype(np.uint8)
                    self._print_warning("No hot pixel found on frame")
        self._print_msg("Percentage of hot pixels : %.2f %%"%(
            float(np.shape(np.nonzero(hp_map))[1])
            / (self.dimx * self.dimy) * 100.))
        self.write_fits(self._get_hp_map_path(), hp_map,
                        fits_header=self._get_cr_map_frame_header(),
                        overwrite=self.overwrite)

    def get_noise_values(self, bias_path, dark_path, exposition_time,
                         dark_int_time, combine='average', reject='avsigclip'):
        """
        Return readout noise and dark current level from bias and dark
        frames.
        
        :param bias_path: Path to a list of bias files.
        
        :param dark_path: Path to a list of dark files.
        
        :param exposition_time: Integration time of the frames.

        :param dark_int_time: Integration time of the dark frames.

        :param reject: (Optional) Rejection operation for master
          frames creation. Can be 'sigclip', 'minmax', 'avsigclip' or
          None (default 'avsigclip'). See
          :py:meth:`orb.utils.create_master_frame`.
        
        :param combine: (Optional) Combining operation for master
          frames creation. Can be 'average' or 'median' (default
          'average'). See
          :py:meth:`orb.utils.create_master_frame`.

        :return: readout_noise, dark_current_level
        """
        BORDER_COEFF = 0.45 # Border coefficient to take only the
                            # center of the frames to compute noise
                            # levels
                           
        bias_image, master_bias_temp = self._load_bias(
            bias_path, return_temperature=True, combine=combine,
            reject=reject)
        
        bias_cube = Cube(bias_path,
                         config_file_name=self.config_file_name)
        
        min_x = int(bias_cube.dimx * BORDER_COEFF)
        max_x = int(bias_cube.dimx * (1. - BORDER_COEFF))
        min_y = int(bias_cube.dimy * BORDER_COEFF)
        max_y = int(bias_cube.dimy * (1. - BORDER_COEFF))
        
        readout_noise = [orb.utils.robust_std(bias_cube[min_x:max_x,
                                              min_y:max_y, ik])
                         for ik in range(bias_cube.dimz)]
        
        readout_noise = orb.utils.robust_mean(readout_noise)
        
        dark_cube = Cube(dark_path,
                         config_file_name=self.config_file_name)

        dark_current_level = [orb.utils.robust_median(
            (dark_cube[:,:,ik] - bias_image)[min_x:max_x, min_y:max_y])
                              for ik in range(dark_cube.dimz)]
        
        dark_current_level = orb.utils.robust_mean(dark_current_level)
        dark_current_level = (dark_current_level
                              / dark_int_time * exposition_time)
        
        return readout_noise, dark_current_level


    def get_bias_coeff_from_T(self, master_bias_temp, master_bias_level,
                              frame_temp, calibrated_params):
        """
        :param master_bias_temp: Temperature of the master bias frame.

        :param master_bias_level: Median of the master bias frame.

        :param frame_temp: Temperature of the frame to correct.

        :param calibrated_params: parameters [a, b] of the
          function bias_level(T) = aT + b. T is in degrees C and
          bias_level(T) is the median of the bias frame at the
          given temperature.
        """
        calib_master_bias_level = np.polyval(
            calibrated_params, master_bias_temp)
        calib_frame_bias_level = np.polyval(
            calibrated_params, frame_temp)
        return  calib_frame_bias_level / calib_master_bias_level

    def get_dark_coeff_from_T(self, master_dark_temp, master_dark_level,
                              frame_temp, activation_energy):
        """
         Return calibrated coefficient of the calibrated dark frame
         given the temperature of the frame to correct (see Widenhorn
         et al. 2002)

        :param frame_temp: Temperature of the frame to correct.
        
        :master_dark_level: Master dark level in counts
        
        :master_dark_temp: Master dark temperature in Celsius
            
        :activation_energy: Activation energy in eV
        """
        def dark_level(frame_temp, master_dark_level,
                       master_dark_temp, activation_energy):
            """Return calibrated dark level (see Widenhorn et al. 2002)

            :master_dark_level: Master dark level in counts

            :master_dark_temp: Master dark temperature in Celsius

            :activation_energy: Activation energy in eV
            """
            k = 8.62e-5 # eV/K
            level = (master_dark_level * np.exp(
                activation_energy * (1./(k * (master_dark_temp + 273.15))
                                     - 1./(k * (frame_temp + 273.15)))))

            if level > 0.: return level
            else: return 0.

        calib_frame_dark_level = dark_level(frame_temp, master_dark_level,
                                            master_dark_temp,
                                            activation_energy)

        return  calib_frame_dark_level/ master_dark_level
    
    def correct_frame(self, index, master_bias, master_dark, master_flat,
                      dark_int_time, flat_int_time, hp_map_path,
                      optimize_dark_coeff, exposition_time,
                      negative_values, master_dark_temp,
                      master_bias_temp, dark_activation_energy,
                      bias_calibration_params, master_bias_level,
                      master_dark_level):
        
        """Correct a frame for the bias, dark and flat field.
        
        :param index: Index of the frame to be corrected
        
        :param master_bias: Master Bias (if None, no correction is done)
        
        :param master_dark: Master Dark. Must be in counts/s and bias
          must have been removed. (if None, no dark and flat
          corrections are done)
        
        :param master_flat: Master Flat (if None, no flat correction
          is done)
        
        :param dark_int_time: Dark integration time
        
        :param flat_int_time: Flat integration time
        
        :param hp_map_path: Path to the hot pixel map
        
        :param optimize_dark_coeff: If True use a fast optimization
          routine to calculate the best coefficient for dark
          correction. This routine is used to correct for the images
          of the camera 2 on SpIOMM, because it has a varying dark and
          bias level and contains a lot of hot pixels (Default False).

        :param dark_activation_energy: Activation energy in eV. This
          is a calibration parameter used to guess the master dark
          coefficient to apply in case the temperature of the frame is
          different from the master dark temperature. Useful only if
          optimize_dark_coeff is True and the temperature of the dark
          frames and the interferogram frames is given in their header
          [keyword 'CCD-TEMP'] (Default None).

        :param bias_calibration_params: A tuple of 2 parameters [a,b]
          that are used to compute the bias coefficient for a varying
          temperature of the camera. Useful only if
          optimize_dark_coeff is True and the temperature of the bias
          frames and the interferogram frames is given in their header
          [keyword 'CCD-TEMP'] (Default None).

        :param master_dark_temp: Mean temperature of the master dark
          frame.

        :param master_bias_temp: Mean temperature of the master bias
          frame.

        :param master_bias_level: Median level of the master bias frame.

        :param master_dark_level: Median level of the master dark frame.
        
        :param exposition_time: (Optional) Integration time of the 
          frames (can be defined in the option file).

        :param negative_values: if False, replace negative values in
          the calculated interferogram by zero.

        .. note:: The correction steps are:
        
          * (If optimize_dark_coeff is True) : Dark and bias levels
            are corrected using calibrated functions and the level of
            hot pixels are optimized by minimizing their standard
            deviation.
          * Bias is substracted to dark and flat
          * Dark is substracted to flat if the integration 
            time of the flat is given
          * Flat is normalized (median = 1)
          * The corrected image is calculated
            :math:`frame=\\frac{frame - dark + bias}{flat}`.
          * Negative values are set to 0 by default
          
        """
        
        def _optimize_dark_coeff(frame, dark_frame, hp_map,
                                 only_hp=False):
            """Return an optimized coefficient to apply to the dark
            integration time.
            
            Useful if the frames contain a lot of hot pixels and a
            varying bias and dark level because of a varying
            temperature.

            :param frame: The frame to correct
            
            :param hp_map: Hot pixels map
                    
            :param only_hp: if True optimize the dark coefficient for
              the hot pixels of the frame. If False optimize the dark
              coefficient for the 'normal' pixels of the frame (default
              False).
            """
            def _coeff_test(dark_coeff, frame, dark_frame, hp_map, only_hp):
                test_frame = frame - (dark_frame * dark_coeff)
                if hp_map is not None:
                    if only_hp:
                        hp_frame = test_frame[np.nonzero(hp_map)]
                        # we try to minimize the std of the hot pixels in
                        # the frame 
                        std = np.sqrt(np.mean(
                            ((orb.utils.robust_median(hp_frame)
                              - orb.utils.robust_median(test_frame))**2.)))
                    else:
                        non_hp_frame = test_frame[np.nonzero(hp_map==0)]
                        non_hp_frame = non_hp_frame[np.nonzero(non_hp_frame)]
                        # We try to find the best dark coefficient to
                        # apply to the non hp frame
                        std = orb.utils.robust_std(non_hp_frame)
                        
                return std

            

            guess = [1.0]        
            result = optimize.fmin_powell(_coeff_test, guess,
                                          (frame, dark_frame, hp_map, only_hp),
                                          xtol=1e-5, ftol=1e-5, disp=False)
            return result
            
            
        frame = np.array(self.get_data_frame(index), dtype = float)
        
        if master_bias is not None: master_bias = np.copy(master_bias)
        if master_dark is not None: master_dark = np.copy(master_dark)
        if master_flat is not None: master_flat = np.copy(master_flat)
        
        # getting frame temperature
        frame_header = self.get_frame_header(index)
        if 'CCD-TEMP' in frame_header:
            frame_temp = frame_header["CCD-TEMP"]
        else:
            frame_temp = None

        # getting bias level
        frame_header = self.get_frame_header(index)
        if "BIAS-LVL" in frame_header:
            frame_bias_level = frame_header["BIAS-LVL"]
        else:
            frame_bias_level = None
        
        # bias substraction
        if master_bias is not None:
            bias_coeff = 1.0
            if (optimize_dark_coeff):
                if frame_bias_level is not None:
                    bias_coeff = frame_bias_level / master_bias_level
                elif ((bias_calibration_params is not None)
                      and (master_bias_temp is not None)
                      and (frame_temp is not None)):
                    bias_coeff = self.get_bias_coeff_from_T(
                        master_bias_temp,
                        master_bias_level,
                        frame_temp,
                        bias_calibration_params)
                
            frame -= master_bias * bias_coeff

        # computing dark image (bias substracted)
        if (master_dark is not None
            and exposition_time is not None):
            
            if optimize_dark_coeff:
                # load hot pixels map
                if hp_map_path is None:
                    hp_map = self.read_fits(self._get_hp_map_path())
                else: 
                    hp_map = self.read_fits(hp_map_path)
                # remove border on hp map
                hp_map_corr = np.copy(hp_map)
                hp_map_corr[0:self.dimx/5., :] = 0.
                hp_map_corr[:, 0:self.dimx/5.] = 0.
                hp_map_corr[4.*self.dimx/5.:, :] = 0.
                hp_map_corr[:, 4.*self.dimx/5.:] = 0.
                    
                # If we can use calibrated parameters, the dark frame
                # is scaled using the temperature difference between
                # the master dark and the frame.
                if ((dark_activation_energy is not None)
                    and (master_dark_temp is not None)
                    and (frame_temp is not None)):
                    dark_coeff = self.get_dark_coeff_from_T(
                        master_dark_temp, master_dark_level,
                        frame_temp, dark_activation_energy)
                    
                    dark_coeff *= exposition_time
                    
                # If no calibrated params are given the dark
                # coefficient to apply is guessed using an
                # optimization routine.
                else:
                    dark_coeff = _optimize_dark_coeff(frame, master_dark, 
                                                      hp_map_corr,
                                                      only_hp=False)
                    
                temporary_frame = frame - (master_dark * dark_coeff)

                # hot pixels correction
                temporary_frame = orb.utils.correct_hot_pixels(
                    temporary_frame, hp_map)
                
                ## # hot pixels only are now corrected using a special
                ## # dark coefficient that minimize their std
                ## hp_dark_coeff = _optimize_dark_coeff(
                ##     frame, master_dark, hp_map_corr, only_hp=True)
                ## hp_frame = (frame
                ##             - master_dark * hp_dark_coeff
                ##             - orb.utils.robust_median(master_dark) * dark_coeff)
                ## temporary_frame[np.nonzero(hp_map)] = hp_frame[
                ##     np.nonzero(hp_map)]
                
                frame = temporary_frame 

            # else: simple dark substraction
            else:
                frame -= (master_dark * exposition_time)
                

        # computing flat image
        if master_flat is not None:
            if (dark_int_time is not None) and (flat_int_time is not None):
                dark_flat_coeff = float(flat_int_time / float(dark_int_time))
                dark_master_flat = master_dark * dark_flat_coeff
                master_flat = master_flat - dark_master_flat
                
            if master_bias is not None:
                master_flat -= master_bias
                
            # flat normalization
            master_flat /= np.median(master_flat)
            # flat correction
            flat_zeros = np.nonzero(master_flat==0)
            # avoid dividing by zeros
            master_flat[flat_zeros] = 1.
            frame /= master_flat
            # zeros are replaced by NaNs in the final frame
            frame[flat_zeros] = np.nan

        return frame



    def correct(self, bias_path=None, dark_path=None, flat_path=None,
                cr_map_list_path=None, alignment_vector_path=None,
                dark_int_time=None, flat_int_time=None,
                exposition_time=None, bad_frames_vector=[],
                optimize_dark_coeff=False,
                dark_activation_energy=None,
                bias_calibration_params=None, negative_values=False,
                z_range=[], order=1, zeros=False, combine='average',
                reject='avsigclip', flat_smooth_deg=0):
        
        """Correct raw data for bias, dark, flat, cosmic rays and
        alignment using the precomputed alignment vector and the
        cosmic ray map.
        
        :param bias_path: (Optional) Path to a list of bias files. If
          none given no correction is done.
        
        :param dark_path: (Optional) Path to a list of dark files. If
          none given no dark and flat corrections are done.
  
        :param flat_path: (Optional) Path to a list of flat files. If
          none given no flat correction is done.
        
        :param cr_map_list_path: (Optional) Path to the cosmic ray map
          list of files, if none given the default path is used.
          
        :param alignment_vector_path: (Optional) Path to the alignment
          vector file, if none given the default path is used.
          
        :param dark_int_time: (Optional) Integration time of the dark
          frames. Used to remove the dark pattern from a flat with a
          different integration time. User must specify flat_int_time.
          
        :param flat_int_time: (Optional) Integration time of the flat
          frames. see dark_int_time.
          
        :param bad_frames_vector: (Optional) Contains the index of the
          frames to be replaced by zeros.
          
        :param optimize_dark_coeff: (Optional) If True use a fast optimization
          routine to calculate the best coefficient for dark
          correction. This routine is used to correct for the images
          of the camera 2 on SpIOMM, because it contains a lot of hot
          pixels (Default False).

        :param dark_activation_energy: Activation energy in eV. This is a
          calibration parameter used to guess the master dark
          coefficient to apply in case the temperature of the frame is
          different from the master dark temperature. Useful only if
          optimize_dark_coeff is True and the temperature of the dark
          frames and the interferogram frames is given in their header
          [keyword 'CCD-TEMP'] (Default None).

        :param bias_calibration_params: (Optional) a tuple of 2
          parameters [a,b] that are used to compute the bias
          coefficient for a varying temperature of the camera. Useful
          only if optimize_dark_coeff is True and the temperature of
          the bias frames and the interferogram frames is given in
          their header [keyword 'CCD-TEMP'] (Default None).

        :param exposition_time: (Optional) Integration time of the 
          frames (can be defined in the option file).

        :param negative_values: (Optional) If False, replace negative values in
          the calculated interferogram by zero (Default False).

        :param z_range: (Optional) 1d array containing the index of
          the frames to be computed.

        :param order: (Optional) Interpolation order (Default 1). Be
          careful in using an interpolation order greater than 1 with
          images containing stars.

        :param zeros: (Optional) If True, cosmic rays are replaced by
          zeros. If False, cosmic rays are replaced by the median of
          the neighbouring region (default False).

        :param reject: (Optional) Rejection operation for master
          frames creation. Can be 'sigclip', 'minmax', 'avsigclip' or
          None (default 'avsigclip'). See
          :py:meth:`orb.utils.create_master_frame`.
        
        :param combine: (Optional) Combining operation for master
          frames creation. Can be 'average' or 'median' (default
          'average'). See
          :py:meth:`orb.utils.create_master_frame`.

        :param flat_smooth_deg: (Optional) If > 0 smooth the master
          flat (help removing possible fringe pattern) (default
          0). See :py:meth:`process.RawData._load_flat`.

        .. note:: Frames considered as bad (which index are in
          ``bad_frames_vector`` or not in the ``z_range`` vector) are just
          replaced by frames of zeros.

        .. note:: The creation of the corrected interferogram frames
          walks through 2 steps:

          1. Correction for bias, dark, and flat field. Please refer
             to: :py:meth:`process.RawData.correct_frame`.
               
          2. Alignment of the frame using linear interpolation by
             default. A higher order interpolation can be used if the
             field contains no star like object. By default cosmic
             rays are replaced by the weighted average of the
             neighbouring region. Weights are computed from a gaussian
             kernel.
             
        .. seealso:: :py:meth:`process.RawData.correct_frame` 
        .. seealso:: :py:meth:`process.RawData.create_cosmic_ray_map`
        .. seealso:: :py:meth:`process.RawData.create_alignment_vector`
        """

        def _correct_frame(frame, ik, dimx, dimy, 
                           border_size, deg, alignment_vector_ii, 
                           cr_map_ii, bad_frames_vector, order,
                           zeros):
            """Process and return one frame of the interferogram. 
            This function is used for parallel processing.
            """
            mask_frame = np.zeros_like(frame, dtype=float)
            
            MEDIAN_DEG = 2
            x_range = range(border_size, int(dimx - border_size - 1L))
            y_range = range(border_size, int(dimy - border_size - 1L))
            x_min = np.min(x_range)
            x_max = np.max(x_range) + 1L
            y_min = np.min(y_range)
            y_max = np.max(y_range) + 1L
            plain_frame = np.empty((dimx, dimy), dtype=float)
            plain_frame.fill(np.nan)
            plain_mask_frame = np.zeros((dimx, dimy), dtype=float)
            
            if bad_frames_vector is None:
                bad_frames_vector = []
                
            if (ik not in bad_frames_vector): # we don't work on bad frames
                bad_pixels = np.nonzero(cr_map_ii)
                dx = alignment_vector_ii[0]
                dy = alignment_vector_ii[1]

                ## CR CORRECTION: CRs are replaced by a weighted
                # average of the neighbouring region. Weights are
                # calculated from a 2d gaussian kernel.
                for ibp in range(len(bad_pixels[0])):
                    ix = bad_pixels[0][ibp]
                    iy = bad_pixels[1][ibp]
                    mask_frame[ix, iy] = 1 # masking cr in mask frame
                    if (ix < x_max and iy < y_max
                        and ix >= x_min and iy >= y_min):
                        (med_x_min, med_x_max,
                         med_y_min, med_y_max) = orb.utils.get_box_coords(
                            ix, iy, MEDIAN_DEG*2+1,
                            x_min, x_max, y_min, y_max)
                        box = frame[med_x_min:med_x_max,
                                    med_y_min:med_y_max]
             
                        # definition of the kernel. It must be
                        # adjusted to the real box
                        ker = orb.cutils.gaussian_kernel(MEDIAN_DEG)
                        if (box.shape[0] != MEDIAN_DEG*2+1
                            or box.shape[1] != MEDIAN_DEG*2+1):
                            if ix - med_x_min != MEDIAN_DEG:
                                ker = ker[MEDIAN_DEG - (ix - med_x_min):,:]
                            if iy - med_y_min != MEDIAN_DEG:
                                ker = ker[:,MEDIAN_DEG - (iy - med_y_min):]
                            if med_x_max - ix != MEDIAN_DEG + 1:
                                ker = ker[:- (MEDIAN_DEG + 1
                                              - (med_x_max - ix)),:]
                            if med_y_max - iy != MEDIAN_DEG + 1:
                                ker = ker[:,:- (MEDIAN_DEG + 1
                                                - (med_y_max - iy))]
                        
                        # cosmic rays are removed from the
                        # weighted average (their weight is set to
                        # 0)
                        ker *=  1 - cr_map_ii[med_x_min:med_x_max,
                                              med_y_min:med_y_max]

                        # pixel is replaced by the weighted average
                        if np.sum(ker) != 0:
                            frame[ix, iy] = np.sum(box * ker)/np.sum(ker)
                        else:
                            # if no good pixel around can be found
                            # the pixel is replaced by the median
                            # of the whole box
                            frame[ix, iy] = np.median(box)

                ## SHIFT
                if (dx != 0.) and (dy != 0.):
                    
                    frame = orb.utils.shift_frame(frame, dx, dy, 
                                                  x_min, x_max, 
                                                  y_min, y_max, 1)
                    
                    mask_frame = orb.utils.shift_frame(mask_frame, dx, dy, 
                                                       x_min, x_max, 
                                                       y_min, y_max, 1)
                else:
                    frame = frame[x_min:x_max, y_min:y_max]
                    mask_frame = mask_frame[x_min:x_max, y_min:y_max]

                ## FINAL CORRECTION (If zeros == True)
                if zeros:
                    # if required we eliminate the cosmic rays by
                    # setting the region around to zero
                    for ibp in range(len(bad_pixels[0])):
                        ix = bad_pixels[0][ibp] - x_min - dx
                        iy = bad_pixels[1][ibp] - y_min - dy
                        frame[ix-deg:ix+deg+1L,
                              iy-deg:iy+deg+1L] = 0.
                        
                plain_frame[x_min:x_max, y_min:y_max] = frame
                plain_mask_frame[x_min:x_max, y_min:y_max] = mask_frame

            return plain_frame, plain_mask_frame
 

        DEG = 1L # radius of the zone considered as bad around a cosmic ray
        CENTER_SIZE_COEFF = 0.1 # size ratio of the center region used
                                # for frames stats

        self._print_msg("Creating interferogram")
        
        x_min, x_max, y_min, y_max = orb.utils.get_box_coords(
            self.dimx/2., self.dimy/2.,
            max((self.dimx, self.dimy))*CENTER_SIZE_COEFF,
            0, self.dimx, 0, self.dimy)
         
        ### load needed data ##################################

        # check existence of dark and bias calibration parameters in
        # case of an optimization of the bias level and the dark level
        if optimize_dark_coeff:
            if dark_activation_energy is None:
                self._print_warning("No dark activation energy have been passed. The dark level will have to be guessed (less precise)")
            else:
                self._print_msg("Dark activation energy (in eV): %s"%str(
                    dark_activation_energy))
            if bias_calibration_params is None:
                self._print_warning("No bias calibration parameters have been passed. The bias level will not be optimized (less precise)")
            else:
                self._print_msg("Bias calibration parameters: %s"%str(
                    bias_calibration_params))
                
        # load master bias
        if (bias_path is not None):
            master_bias, master_bias_temp = self._load_bias(
                bias_path, return_temperature=True, combine=combine,
                reject=reject)
            master_bias_level = orb.utils.robust_median(master_bias[x_min:x_max,
                                                          y_min:y_max])
            self._print_msg('Master bias median level at the center of the frame: %f'%master_bias_level)
            if optimize_dark_coeff and master_bias_temp is None:
                self._print_warning("The temperature of the master bias could not be defined. The bias level will not be optimized (less precise)")
        else:
            master_bias = None
            master_bias_temp = None
            master_bias_level = None
            self._print_warning("no bias list given, there will be no bias correction of the images")
            
        # load master dark (bias is substracted and master dark is
        # divided by the dark integration time)
        if dark_path is not None:
            master_dark, master_dark_temp = self._load_dark(
                dark_path, return_temperature=True, combine=combine,
                reject=reject)
            master_dark_uncorrected = np.copy(master_dark)
            
            if optimize_dark_coeff:
                # remove bias
                if master_dark_temp is None and master_bias is not None:
                    self._print_warning("The temperature of the master dark could not be defined. The dark level will have to be guessed (less precise)")
                    master_dark -= master_bias
                elif (bias_calibration_params is not None
                      and master_bias is not None):
                    master_bias_coeff = self.get_bias_coeff_from_T(
                        master_bias_temp, master_bias_level,
                        master_dark_temp, bias_calibration_params)
                    master_dark -= master_bias * master_bias_coeff
                
            elif master_bias is not None:
                master_dark -= master_bias

            # master dark in counts/s
            master_dark /= dark_int_time
            
            master_dark_level = orb.utils.robust_median(master_dark[
                x_min:x_max, y_min:y_max])
            self._print_msg('Master dark median level at the center of the frame: %f'%master_dark_level)
                
        else:
            master_dark = None
            master_dark_temp = None
            master_dark_level = None
            self._print_warning("no dark list given, there will be no dark corrections of the images")

        # load master flat
        if (flat_path is not None):
            master_flat = self._load_flat(flat_path, combine=combine,
                                          reject=reject,
                                          smooth_deg=flat_smooth_deg)
        else:
            master_flat = None
            self._print_warning("No flat list given, there will be no flat field correction of the images")
            
        # load alignment vector
        if (alignment_vector_path is None):
            alignment_vector_path = self._get_alignment_vector_path() 
        alignment_vector = self._load_alignment_vector(alignment_vector_path)
        if (alignment_vector is None):
            alignment_vector = np.zeros((self.dimz, 2), dtype = float)
            self._print_warning("No alignment vector loaded : there will be no alignment of the images")

        # create hot pixel map
        hp_map_path = None
        if optimize_dark_coeff:
            if master_dark is not None:
                self.create_hot_pixel_map(master_dark_uncorrected, master_bias)
                hp_map_path=self._get_hp_map_path()
            else:
                self._print_warning("No dark or bias frame given : The hot pixel map cannot be created")
        
        # define the nice zone (without extrapolations due to
        # disalignment)
        border_size = int(math.ceil(np.max(alignment_vector)) + 1L)
        if (DEG > border_size):
            border_size = DEG + 1L

        if (z_range == []):
            z_min = 0
            z_max = self.dimz
        else:
            z_min = min(z_range)
            z_max = max(z_range)
            
        # Create the file containing the list of the interferogram
        # frames
        image_list_file = self.open_file(self._get_interfero_list_path())

        cr_map_cube = None
        
        # Instanciating cosmic ray map cube
        if (cr_map_list_path is None):
            cr_map_list_path = self._get_cr_map_list_path()
            if os.path.exists(cr_map_list_path):
                cr_map_cube = Cube(cr_map_list_path,
                                    config_file_name=self.config_file_name)
            else:
                self._print_warning("No cosmic ray map loaded")
                
        self._print_msg("computing interferogram")

        # Multiprocessing server init
        job_server, ncpus = self._init_pp_server() 
        ncpus_max = ncpus

        # Interferogram creation
        progress = ProgressBar(int((z_max - z_min) / ncpus_max))
        for ik in range(z_min, z_max, ncpus):
            
            # No more jobs than frames to compute
            if (ik + ncpus >= z_max): 
                ncpus = z_max - ik
                
            frames = np.empty((self.dimx, self.dimy, ncpus), dtype=float)
            mask_frames = np.empty((self.dimx, self.dimy, ncpus), dtype=float)
            cr_maps = np.zeros((self.dimx, self.dimy, ncpus), dtype=np.bool)
            
            for icpu in range(ncpus):
                if cr_map_cube is not None:
                    cr_maps[:,:,icpu] = cr_map_cube.get_data_frame(ik+icpu)

            # 1 - frames correction for bias, dark, flat.
            jobs = [(ijob, job_server.submit(
                self.correct_frame,
                args=(ik + ijob, 
                      master_bias, 
                      master_dark, 
                      master_flat, 
                      dark_int_time, 
                      flat_int_time, 
                      hp_map_path, 
                      optimize_dark_coeff,
                      exposition_time,
                      negative_values,
                      master_dark_temp,
                      master_bias_temp,
                      dark_activation_energy,
                      bias_calibration_params,
                      master_bias_level,
                      master_dark_level),
                modules=("numpy as np", 
                         "from scipy import optimize",
                         "import orb.utils")))
                    for ijob in range(ncpus)]
            
            for ijob, job in jobs:
                frames[:,:,ijob] = job()

            # 2 - frames alignment and correction for cosmic rays
            jobs = [(ijob, job_server.submit(
                _correct_frame, 
                args=(frames[:,:,ijob], 
                      ik + ijob, 
                      self.dimx, self.dimy, 
                      border_size, DEG, 
                      alignment_vector[ik + ijob,:], 
                      cr_maps[:,:,ijob], 
                      bad_frames_vector, order, zeros),
                modules=(
                    "numpy as np",
                    "import orb.utils",
                    "import orb.cutils",
                    "from scipy import ndimage",))) 
                    for ijob in range(ncpus)]

            for ijob, job in jobs:
                frames[:,:,ijob], mask_frames[:,:,ijob] = job()

            for ijob in range(ncpus):
                interfero_frame_path = self._get_interfero_frame_path(ik + ijob)
                image_list_file.write(interfero_frame_path + "\n")
                self.write_fits(
                    interfero_frame_path, frames[:,:,ijob], 
                    silent=True,
                    fits_header=self._get_interfero_frame_header(),
                    overwrite=self.overwrite,
                    mask=mask_frames[:,:,ijob], record_stats=True)
            progress.update(int((ik - z_min) / ncpus_max), 
                            info="frame : " + str(ik))
            
        image_list_file.close()
        self._close_pp_server(job_server)
        progress.end()

        # check median level of frames (Because bad bias frames can
        # cause a negative median level for the frames of camera 2)
        self._print_msg('Checking frames level')
        interf_cube = Cube(self._get_interfero_list_path(),
                           config_file_name=self.config_file_name)
        zmedian = interf_cube.get_zmedian()
        corr_level = -np.min(zmedian) + 10. # correction level

        # correct frames if nescessary by adding the same level to every frame
        if np.min(zmedian) < 0.:
            self._print_warning('Negative median level of some frames. Level of all frames is being added %f counts'%(corr_level))
            progress = ProgressBar(interf_cube.dimz)
            for iz in range(interf_cube.dimz):
                progress.update(iz, info='Correcting negative level of frames')
                frame = interf_cube.get_data_frame(iz) + corr_level
                mask = interf_cube.get_data_frame(iz, mask=True)
                interfero_frame_path = self._get_interfero_frame_path(iz)
                self.write_fits(
                    interfero_frame_path, frame, mask=mask,
                    fits_header=self._get_interfero_frame_header(),
                    overwrite=True, silent=True, record_stats=True)
            progress.end()
        
        
        if self.indexer is not None:
            self.indexer['interfero_list'] = self._get_interfero_list_path()
            
        self._print_msg("Interferogram computed")

        # create energy map
        energy_map = interf_cube.get_interf_energy_map()
        self.write_fits(
            self._get_energy_map_path(), energy_map,
            fits_header=self._get_energy_map_header(),
            overwrite=True, silent=False)
        
        if self.indexer is not None:
            self.indexer['energy_map'] = self._get_energy_map_path()
            
        # Create deep frame
        deep_frame = interf_cube.get_mean_image()
        
        self.write_fits(
            self._get_deep_frame_path(), deep_frame,
            fits_header=self._get_deep_frame_header(),
            overwrite=True, silent=False)
        
        if self.indexer is not None:
            self.indexer['deep_frame'] = self._get_deep_frame_path()
        
            

##################################################
#### CLASS Laser #################################
##################################################

class CalibrationLaser(Cube):
    """ ORBS calibration laser processing class.

    CalibrationLaser class is aimed to compute the calibration laser map that
    is used to correct for the **off-axis effect**.

    .. note:: The **off-axis effect** comes from the angle between one
     pixel of a camera and the optical axis of the interferometer. For
     a given displacement of the mirror (step) the optical path
     difference 'seen' by a pixel is different and depends on the
     off-axis angle. The effect on the spectrum corresponds to a
     changing step in wavelength (between two channels) and thus an
     expanded spectrum relatively to its theoretical shape.

     The **calibration laser cube** is an interferogram cube taken with a
     monochromatic light. The real position of the emission line (its
     channel) help us to correct for the step variations using the
     formula :

     .. math::
     
        step_{real} = step_{th} * \\frac{\\lambda_{LASER}}{channel}
    """

    x_center = None
    y_center = None
    pix_size = None
    
    def _get_calibration_laser_map_path(self):
        """Return the default path to the calibration laser map."""
        return self._data_path_hdr + "calibration_laser_map.fits"
    
    def _get_calibration_laser_map_header(self):
        """Return the header of the calibration laser map."""
        return (self._get_basic_header('Calibration laser map')
                + self._calibration_laser_header)

    def _get_calibration_laser_fitparams_path(self):
        """Return the path to the file containing the fit parameters
        of the calibration laser cube."""
        return self._data_path_hdr + "calibration_laser_fitparams.fits"
    
    def _get_calibration_laser_fitparams_header(self):
        """Return the header of the file containing the fit parameters
        of the calibration laser cube."""
        return (self._get_basic_header('Calibration laser fit parameters')
                + self._calibration_laser_header)

    def _get_calibration_laser_spectrum_list_path(self):
        """Return the path to the calibration laser spectrum list."""
        return self._data_path_hdr + "calibration_laser_spectrumlist"
    
    def _get_calibration_laser_spectrum_frame_path(self, index):
        """Return the default path to the reduced calibration laser frame.

        :param index: Index of the frame.
        """
        return os.path.join(self._data_path_hdr,
                            'CALIBRATION_LASER_SPECTRUM',
                            "calibration_laser_spectrum_{:04d}.fits".format(index))

    def _get_calibration_laser_spectrum_frame_header(self, index, axis):
        """Return the header of a calibration spectrum frame.

        :param index: Index of the frame.
        :param axis: Wavenumber axis.
        """
        return (self._get_basic_header('Calibration laser spectrum frame')
                + self._project_header
                + self._calibration_laser_header
                + self._get_basic_frame_header(self.dimx, self.dimy)
                + self._get_basic_spectrum_frame_header(index, axis,
                                                        wavenumber=True))

    def create_calibration_laser_map(self, order=30, step=9765,
                                     get_calibration_laser_spectrum=False,
                                     fast=True):
        """ Create the calibration laser map.

        Compute the spectral cube from the calibration laser cube and
        create the calibration laser map containing the fitted central
        position of the emission line for each pixel of the image
        plane (x/y axes).

        :param order: (Optional) Folding order
        :param step: (Optional) Step size in um
        
        :param get_calibration_laser_spectrum: (Optional) If True return the
          calibration laser spectrum

        :param fast: (Optional) If False a sinc^2 is fitted so the fit
          is better but the procedure becomes slower. If True a
          gaussian is fitted (default True).
        """

        def _find_max_in_column(column_data, step, order, cm1_axis,
                                get_calibration_laser_spectrum, fast):
            """Return the fitted central position of the emission line"""
            dimy = column_data.shape[0]
            dimz = column_data.shape[1]
            BORDER = int(0.1 * dimz) + 1
            max_array_column = np.empty((dimy), dtype=float)
            fitparams_column = np.empty((dimy, 8), dtype=float)
            interpol_cm1_axis = interpolate.interp1d(
                np.arange(dimz), cm1_axis,
                bounds_error=False, fill_value=np.nan)
                        
            # FFT of the interferogram
            column_spectrum = orb.utils.cube_raw_fft(column_data, apod=None)
            if (int(order) & 1):
                    column_spectrum = column_spectrum[::-1]
            for ij in range(column_data.shape[0]):
                spectrum_vector = column_spectrum[ij,:]
                # defining window
                max_index = np.argmax(spectrum_vector)
                range_min = max_index - BORDER
                if (range_min < 0):
                    range_min = 0
                range_max = max_index + BORDER + 1L
                if (range_max > len(spectrum_vector)):
                    range_max = len(spectrum_vector)

                # gaussian fit (fast)
                if fast:
                    fitp = orb.utils.fit_lines_in_vector(
                        spectrum_vector, [max_index], fmodel='gaussian',
                        fwhm_guess=2.4,
                        poly_order=0,
                        signal_range=[range_min, range_max],
                        wavenumber=True)

                # or sinc2 fit (slow)
                else:
                    fitp = orb.utils.fit_lines_in_vector(
                        spectrum_vector, [max_index], fmodel='sinc2',
                        observation_params=[step, order],
                        fwhm_guess=2.,
                        poly_order=0,
                        signal_range=[range_min, range_max],
                        wavenumber=True)
                    
                if (fitp != []):
                    max_index_fit = fitp['lines-params'][0][2]
                    max_array_column[ij] = 1e7 / interpol_cm1_axis(
                        max_index_fit)
                    if 'lines-params-err' in fitp:
                        fitparams_column[ij,:] = np.array(
                            list(fitp['lines-params'][0])
                            + list(fitp['lines-params-err'][0]))
                    else:
                        fitparams_column.fill(np.nan)
                        fitparams_column[ij,:4] = fitp['lines-params'][0]
                else:
                    max_array_column[ij] = np.nan
                    fitparams_column[ij,:].fill(np.nan)

            # check if fit range is large enough
            fwhm_median = np.median(fitparams_column[:,3])
            if fwhm_median is not np.nan:
                if (range_max - range_min) < 5. * fwhm_median:
                    import warnings
                    warnings.warn('fit range is not large enough: median fwhm ({}) > 5xrange ({})'.format(
                        fwhm_median, range_max - range_min))
                    
            if not get_calibration_laser_spectrum:
                return max_array_column, fitparams_column
            else:
                return max_array_column, fitparams_column, column_spectrum

        self._print_msg("Computing calibration laser map")
       
        order = float(order)
        step = float(step)
        
        # create the fft axis in cm1
        cm1_axis = orb.utils.create_cm1_axis(
            self.dimz, step, order)

        fitparams = np.empty((self.dimx, self.dimy, 8), dtype=float)
        max_array = np.empty((self.dimx, self.dimy), dtype=float)
        for iquad in range(0, self.QUAD_NB):
            x_min, x_max, y_min, y_max = self.get_quadrant_dims(iquad)
            iquad_data = self.get_data(x_min, x_max, 
                                       y_min, y_max, 
                                       0, self.dimz)
            # init multiprocessing server
            job_server, ncpus = self._init_pp_server()

            progress = ProgressBar(x_max - x_min)
            for ii in range(0, x_max - x_min, ncpus):
                # create no more jobs than work to do
                if (ii + ncpus >= x_max - x_min): 
                    ncpus = x_max - x_min - ii
                # create jobs
                jobs = [(ijob, job_server.submit(
                    _find_max_in_column, 
                    args=(iquad_data[ii+ijob,:,:],
                          step, order, cm1_axis,
                          get_calibration_laser_spectrum, fast),
                    modules=("numpy as np",
                             "math",
                             "from scipy import interpolate, fftpack",
                             "import orb.utils",))) 
                        for ijob in range(ncpus)]

                # execute jobs
                for ijob, job in jobs:
                    if not get_calibration_laser_spectrum:
                        (max_array[x_min + ii + ijob, y_min:y_max],
                         fitparams[x_min + ii + ijob, y_min:y_max,:]) = job()
                    else:
                        (max_array[x_min + ii + ijob, y_min:y_max],
                         fitparams[x_min + ii + ijob, y_min:y_max,:],
                         iquad_data[ii+ijob,:,:]) = job()
                        
                progress.update(ii, info="quad %d/%d, column : %d"%(
                    iquad+1L, self.QUAD_NB, ii))
            self._close_pp_server(job_server)
            progress.end()

            if get_calibration_laser_spectrum:
                progress = ProgressBar(self.dimz)
                ## SAVE returned data by quadrants
                for iframe in range(self.dimz):
                    progress.update(iframe, info='Saving data')
                    frame_path = self._get_calibration_laser_spectrum_frame_path(
                        iframe)

                    # save data in a *.IQUAD file
                    self.write_fits(
                        frame_path+'.%d'%(iquad), iquad_data[:,:,iframe],
                        silent=True, overwrite=True)
                progress.end()

        # Correct non-fitted values by interpolation
        max_array = orb.utils.correct_map2d(max_array, bad_value=np.nan)
        max_array = orb.utils.correct_map2d(max_array, bad_value=0.)

        # Write calibration laser map to disk
        self.write_fits(self._get_calibration_laser_map_path(), max_array,
                        fits_header=self._get_calibration_laser_map_header(),
                        overwrite=self.overwrite)

        # write fit params
        self.write_fits(
                self._get_calibration_laser_fitparams_path(), fitparams,
                fits_header=self._get_calibration_laser_fitparams_header(),
                overwrite=self.overwrite)

        if self.indexer is not None:
            self.indexer['calibration_laser_map'] = (
                self._get_calibration_laser_map_path())

        # merge *.IQUAD files
        if get_calibration_laser_spectrum:
            progress = ProgressBar(self.dimz)
            for iframe in range(self.dimz):
                progress.update(iframe, info='Merging quads')
                frame = np.empty((self.dimx, self.dimy), dtype=float)
                spectrum_frame_path = self._get_calibration_laser_spectrum_frame_path(
                    iframe)
                for iquad in range(0, self.QUAD_NB):
                    x_min, x_max, y_min, y_max = self.get_quadrant_dims(iquad)
                    frame[x_min:x_max, y_min:y_max] = self.read_fits(
                        spectrum_frame_path+'.%d'%(iquad), delete_after=True)
                self.write_fits(
                    spectrum_frame_path, frame,
                    silent=True,
                    fits_header=self._get_calibration_laser_spectrum_frame_header(
                        iframe, cm1_axis),
                    overwrite=True)

            progress.end()

            # write list of spectrum files
            list_file_path = self._get_calibration_laser_spectrum_list_path()
            list_file = self.open_file(list_file_path)
            for iframe in range(self.dimz):
                spectrum_frame_path = self._get_calibration_laser_spectrum_frame_path(
                    iframe)
                list_file.write('%s\n'%spectrum_frame_path)

            list_file.close()


##################################################
#### CLASS Interferogram #########################
##################################################

class Interferogram(Cube):
    """ORBS interferogram processing class.

    .. note:: Interferogram data is defined as data already processed
       (corrected and aligned frames) by :class:`process.RawData` and
       ready to be transformed to a spectrum by a Fast Fourier
       Transform (FFT).
    """


    def _get_transmission_vector_path(self):
        """Return the path to the transmission vector"""
        return self._data_path_hdr + "transmission_vector.fits"

    def _get_transmission_vector_header(self):
        """Return the header of the transmission vector"""
        return (self._get_basic_header('Transmission vector')
                + self._project_header)
    
    def _get_stray_light_vector_path(self):
        """Return the path to the stray light vector"""
        return self._data_path_hdr + "stray_light_vector.fits"

    def _get_stray_light_vector_header(self):
        """Return the header of the stray light vector"""
        return (self._get_basic_header('stray light vector')
                + self._project_header)

    def _get_extracted_star_spectra_path(self):
        """Return the path to the extracted star spectra"""
        return self._data_path_hdr + "extracted_star_spectra.fits"

    def _get_extracted_star_spectra_header(self):
        """Return the header to the extracted star spectra"""
        return (self._get_basic_header('Extracted star spectra')
                + self._project_header
                + self._calibration_laser_header
                + self._get_fft_params_header('2.0'))

    def _get_corrected_interferogram_list_path(self):
        """Return the default path to the corrected interferogram list"""
        return self._data_path_hdr + "corr_interf.list"

    
    def _get_corrected_interferogram_frame_path(self, frame_index):
        """Return the default path to a spectrum frame given its
        index.
        
        :param frame_index: Index of the frame
        """
        corr_interf_dirname = os.path.dirname(self._data_path_hdr)
        corr_interf_basename = os.path.basename(self._data_path_hdr)
        return (corr_interf_dirname + "/CORRECTED_INTERFEROGRAM/"
                + corr_interf_basename
                + "corrected_interferogram%04d.fits"%frame_index)

    def _get_corrected_interferogram_frame_header(self):
        """Return the header of a corrected interferogram frame"""
        return (self._get_basic_header('Corrected interferogram frame')
                + self._project_header
                + self._get_basic_frame_header(self.dimx, self.dimy))
        
    def _get_spectrum_list_path(self, stars_cube=False,  phase=False):
        """Return the default path to the spectrum list.

        :param stars_cube: (Optional) The spectrum computed
          contains only the spectrum of some stars. The default path
          name is changed (default False).
        :param phase: (Optional) If True the path is changed for a
          phase cube (default False).
        """

        if not phase: cube_type = "spectrum"
        else: cube_type = "phase"
            
        if stars_cube:
            stars_header = "stars_"
        else:
            stars_header = ""
       
        return self._data_path_hdr + stars_header + "%s.list"%cube_type
       

    def _get_spectrum_frame_path(self, frame_index, stars_cube=False,
                                 phase=False):
        """Return the default path to a spectrum frame given its
        index.

        :param frame_index: Index of the frame
        :param stars_cube: (Optional) The spectrum computed
          contains only the spectrum of some stars. The default path
          name is changed (default False).
        :param phase: (Optional) If True the path is changed for a
          phase cube (default False).
        """
        if not phase: cube_type = "spectrum"
        else: cube_type = "phase"
        
        if stars_cube:
            dir_header = "STARS_"
            stars_header = "stars_"
        else:
            dir_header = ""
            stars_header = ""
            
        spectrum_dirname = os.path.dirname(self._data_path_hdr)
        spectrum_basename = os.path.basename(self._data_path_hdr)
        
        return (spectrum_dirname + "/" + dir_header
                + "%s/"%cube_type.upper()
                + spectrum_basename + stars_header 
                + "%s%04d.fits"%(cube_type, frame_index))


    def _get_spectrum_frame_header(self, frame_index, axis,
                                   apodization_function, phase=False,
                                   wavenumber=False):
        """Return the header of the spectral frames.
        
        :param frame_index: Index of the frame.
        
        :param axis: Spectrum axis (must be in wavelength or in
          wavenumber).
        
        :param phase: (Optional) If True the path is changed for a
          phase cube (default False).

        :param wavenumber: (Optional) If True the axis is considered
          to be in wavenumber. If False the axis is considered to be
          in wavelength (default False).
        """
        if not phase: cube_type = "Spectrum"
        else: cube_type = "Phase"
        
        return (self._get_basic_header("%s frame"%cube_type)
                + self._project_header
                + self._calibration_laser_header
                + self._get_basic_frame_header(self.dimx, self.dimy)
                + self._get_basic_spectrum_frame_header(frame_index, axis,
                                                        wavenumber=wavenumber)
                + self._get_fft_params_header(apodization_function))

    def _get_spectrum_path(self, stars_cube=False, phase=False):
        """Return the default path to the spectral cube.
        
        :param stars_cube: (Optional) The spectrum computed
          contains only the spectrum of some stars. The default path
          name is changed (default False).
        :param phase: (Optional) If True the path is changed for a
          phase cube (default False).
        """
        if not phase: cube_type = "spectrum"
        else: cube_type = "phase"
        
        if stars_cube:
            stars_header = "stars_"
        else:
            stars_header = ""
        return self._data_path_hdr + stars_header + "%s.fits"%cube_type
 
    def _get_spectrum_header(self, axis, apodization_function,
                             stars_cube=False, phase=False,
                             wavenumber=False):
        """Return the header of the spectal cube.
        
        :param axis: Spectrum axis (must be in wavelength or in
          wavenumber).
        
        :param stars_cube: (Optional) The spectrum computed
          contains only the spectrum of some stars. The default path
          name is changed (default False).
          
        :param phase: (Optional) If True the path is changed for a
          phase cube (default False).

        :param wavenumber: (Optional) If True the axis is considered
          to be in wavenumber. If False the axis is considered to be
          in wavelength (default False).
        """
        if not phase: cube_type = "Spectrum"
        else: cube_type = "Phase"
        
        if stars_cube:
            header = self._get_basic_header('Stars %s cube'%cube_type)
        else:
            header = self._get_basic_header('%s cube'%cube_type)
        
        return (header
                + self._project_header
                + self._calibration_laser_header
                + self._get_basic_frame_header(self.dimx, self.dimy)
                + self._get_basic_spectrum_cube_header(axis,
                                                       wavenumber=wavenumber)
                + self._get_fft_params_header(apodization_function))

    def compute_phase_coeffs_vector(self, phase_map_paths,
                                    residual_map_path=None):
        """Return a vector containing the mean of the phase
        coefficients for each given phase map.

        :param phase_maps: Tuple of phase map paths. Coefficients are
          sorted in the same order as the phase maps.

        :param residual_map: (Optional) If given this map is used to
          get only the well fitted coefficients in order to compute a
          more precise mean coefficent.
        """
        BEST_RATIO = 0.2 # Max ratio of coefficients considered as good
        
        self._print_msg("Computing phase coefficients of order > 0", color=True)
        
        res_map = self.read_fits(residual_map_path)
        res_map[np.nonzero(res_map == 0)] = np.nanmax(res_map)
        res_map[np.nonzero(np.isnan(res_map))] = np.nanmax(res_map)
        res_distrib = res_map[np.nonzero(~np.isnan(res_map))].flatten()
        # residuals are sorted and sigma-cut filtered 
        best_res_distrib = orb.utils.sigmacut(
            np.partition(
                res_distrib,
                int(BEST_RATIO * np.size(res_distrib)))[
                :int(BEST_RATIO * np.size(res_distrib))], sigma=2.5)
        res_map_mask = np.ones_like(res_map, dtype=np.bool)
        res_map_mask[np.nonzero(
            res_map > orb.utils.robust_median(best_res_distrib))] = 0
        
        
        self._print_msg("Number of well fitted phase vectors used to compute phase coefficients: %d"%len(np.nonzero(res_map_mask)[0]))

        phase_coeffs = list()
        order = 1
        for iphase_map_path in phase_map_paths:
            phase_map = self.read_fits(iphase_map_path)
            # Only the pixels with a good residual coefficient are used 
            clean_phase_map = phase_map[np.nonzero(res_map_mask)]
            median_coeff = np.median(clean_phase_map)
            std_coeff = np.std(clean_phase_map)

            # phase map is sigma filtered to remove bad pixels
            clean_phase_map = [coeff for coeff in clean_phase_map
                               if ((coeff < median_coeff + 2. * std_coeff)
                                   and (coeff > median_coeff - 2.* std_coeff))]

            phase_coeffs.append(np.mean(clean_phase_map))
            self._print_msg("Computed phase coefficient of order %d: %f (std: %f)"%(order, np.mean(clean_phase_map), np.std(clean_phase_map)))
            if np.std(clean_phase_map) >= abs(np.mean(clean_phase_map)):
                self._print_warning("Phase map standard deviation (%f) is greater than its mean value (%f) : the returned coefficient is not well determined and phase correction might be uncorrect"%(np.std(clean_phase_map), np.mean(clean_phase_map)))
            order += 1

        return phase_coeffs


    def create_correction_vectors(self, star_list_path,
                                  fwhm_arc, fov, profile_name='gaussian',
                                  moffat_beta=3.5, step_number=None,
                                  bad_frames_vector=[],
                                  aperture_photometry=True):
        """Create a sky transmission vector computed from star
        photometry and an stray light vector computed from the median
        of the frames.

        :param star_list_path: Path to a list of star positions.
        
        :param box_size: (Optional) The size of the box in pixel
            around each given star used to fit a 2D gaussian (default
            15 pixels). Choose it to be between 3 and 6 times the
            FWHM.

        :param step_number: (Optional) 'Full' number of steps if the
          cube was complete. Might be different from the 'real' number
          of steps obtained. Helps in finding ZPD (default None).

        :param bad_frames_vector: (Optional) Contains the index of the
          frames considered as bad (default []).

        :param aperture_photometry: If True, flux of stars is computed
          by aperture photometry. Else, The flux is evaluated given
          the fit parameters.
        
        .. note:: The sky transmission vector gives the absorption
          caused by clouds or airmass variation.

        .. note:: The stray light vector gives the counts added
          homogeneously to each frame caused by a cloud reflecting
          light coming from the ground, the moon or the sun.

        .. warning:: This method is intented to be used to correct a
          'single camera' interferogram cube. In the case of a merged
          interferogram this is already done by the
          :py:meth:`process.InterferogramMerger.merge` with a far
          better precision (because both cubes are used to compute it)
        """
        # Length ratio of the ZPD over the entire cube. This is used
        # to correct the external illumination vector
        ZPD_SIZE = float(self._get_tuning_parameter('ZPD_SIZE', 0.20))
        
        # number of pixels used on each side to smooth the
        # transmission vector
        SMOOTH_DEG = int(self._get_tuning_parameter('SMOOTH_DEG', 1))

        def _sigmean(frame):
            return orb.utils.robust_mean(orb.utils.sigmacut(frame))
        
        self._print_msg("Creating correction vectors", color=True)


        if aperture_photometry:
            self._print_msg('Star flux evaluated by aperture photometry')
            photometry_type = 'aperture_flux'
        else:
            self._print_msg('Star flux evaluated from fit parameters')
            photometry_type = 'flux'

        ## Computing stray light vector
        self._print_msg("Computing stray light vector")
        # Multiprocessing server init
        job_server, ncpus = self._init_pp_server() 
        
        stray_light_vector = np.empty(self.dimz, dtype=float)
        progress = ProgressBar(self.dimz)
        for ik in range(0, self.dimz, ncpus):
            # No more jobs than frames to compute
            if (ik + ncpus >= self.dimz): 
                ncpus = self.dimz - ik

            jobs = [(ijob, job_server.submit(
                _sigmean,
                args=(self.get_data_frame(ik+ijob),),
                modules=('import orb.utils',)))
                    for ijob in range(ncpus)]

            for ijob, job in jobs:
                stray_light_vector[ik+ijob] = job()
                
            progress.update(ik, info='Computing frame %d'%ik)
            
        self._close_pp_server(job_server)
        progress.end()

        ## get stars photometry to compute transmission vector
        self._print_msg("Computing transmission vector")
        astrom = Astrometry(self, fwhm_arc, fov,
                            profile_name=profile_name,
                            moffat_beta=moffat_beta,
                            data_prefix=self._data_prefix,
                            star_list_path=star_list_path,
                            logfile_name=self._logfile_name,
                            box_size_coeff=7,
                            tuning_parameters=self._tuning_parameters,
                            config_file_name=self.config_file_name)

        ## astrom.fit_stars_in_cube(local_background=False,
        ##                          fix_aperture_size=True,
        ##                          precise_guess=True,
        ##                          multi_fit=True)
        
        astrom.load_fit_results(astrom._get_fit_results_path())
        
        photom = astrom.fit_results[:,:,photometry_type]

        for iph in range(photom.shape[0]):
            photom[iph,:] /= np.median(photom[iph,:])
        
        transmission_vector = np.array(
            [orb.utils.robust_mean(orb.utils.sigmacut(photom[:,iz]))
             for iz in range(self.dimz)])
        
        # correct for zeros, bad frames and NaN values
        bad_frames_vector = [bad_frame
                             for bad_frame in bad_frames_vector
                             if (bad_frame < step_number and bad_frame >= 0)]
        
        transmission_vector[bad_frames_vector] = np.nan
        stray_light_vector[bad_frames_vector] = np.nan
        
        transmission_vector = orb.utils.correct_vector(
            transmission_vector, bad_value=0., polyfit=False, deg=1)
        stray_light_vector = orb.utils.correct_vector(
            stray_light_vector, bad_value=0., polyfit=False, deg=1)
        
        # correct for ZPD
        zmedian = self.get_zmedian(nozero=True)
        zpd_index = orb.utils.find_zpd(zmedian,
                                       step_number=step_number)
        self._print_msg('ZPD index: %d'%zpd_index)
        
        zpd_min = zpd_index - int((ZPD_SIZE * step_number)/2.)
        zpd_max = zpd_index + int((ZPD_SIZE * step_number)/2.) + 1
        if zpd_min < 1: zpd_min = 1
        if zpd_max > self.dimz:
            zpd_max = self.dimz - 1
        
        transmission_vector[zpd_min:zpd_max] = 0.
        transmission_vector = orb.utils.correct_vector(
            transmission_vector, bad_value=0., polyfit=True, deg=3)
        stray_light_vector[zpd_min:zpd_max] = 0.
        stray_light_vector = orb.utils.correct_vector(
            stray_light_vector, bad_value=0., polyfit=True, deg=3)
        
        
        # smooth
        if SMOOTH_DEG > 0:
            transmission_vector = orb.utils.smooth(transmission_vector,
                                                   deg=SMOOTH_DEG)
            stray_light_vector = orb.utils.smooth(stray_light_vector,
                                                  deg=SMOOTH_DEG)
            
        # normalization of the transmission vector
        transmission_vector /= orb.utils.robust_median(transmission_vector)

        # save correction vectors
        self.write_fits(self._get_transmission_vector_path(),
                        transmission_vector,
                        fits_header= self._get_transmission_vector_header(),
                        overwrite=self.overwrite)
        if self.indexer is not None:
            self.indexer['transmission_vector'] = (
                self._get_transmission_vector_path())
        
        self.write_fits(self._get_stray_light_vector_path(),
                        stray_light_vector,
                        fits_header= self._get_stray_light_vector_header(),
                        overwrite=self.overwrite)
        if self.indexer is not None:
            self.indexer['stray_light_vector'] = (
                self._get_stray_light_vector_path())

    def correct_interferogram(self, transmission_vector_path,
                              stray_light_vector_path):
        """Correct an interferogram cube for for variations
        of sky transission and stray light.

        :param sky_transmission_vector_path: Path to the transmission
          vector.All the interferograms of the cube are divided by
          this vector. The vector must have the same size as the 3rd
          axis of the cube (the OPD axis).

        :param stray_light_vector_path: Path to the stray light
          vector. This vector is substracted from the interferograms
          of all the cube. The vector must have the same size as the
          3rd axis of the cube (the OPD axis).

        .. note:: The sky transmission vector gives the absorption
          caused by clouds or airmass variation.

        .. note:: The stray light vector gives the counts added
          homogeneously to each frame caused by a cloud reflecting
          light coming from the ground, the moon or the sun.

        .. seealso:: :py:meth:`process.Interferogram.create_correction_vectors`
        """
        
        def _correct_frame(frame, transmission_coeff, stray_light_coeff):
            if not np.all(frame==0.):
                return (frame - stray_light_coeff) / transmission_coeff
            else:
                return frame

        self._print_msg('Correcting interferogram', color=True)

        # Avoid transmission correction (useful for testing purpose)
        NO_TRANSMISSION_CORRECTION = bool(int(
            self._get_tuning_parameter('NO_TRANSMISSION_CORRECTION', 0)))
        if NO_TRANSMISSION_CORRECTION:
            self._print_warning('No transmission correction')
            
        transmission_vector = self.read_fits(transmission_vector_path)
        if NO_TRANSMISSION_CORRECTION:
            transmission_vector.fill(1.)
            
        stray_light_vector = self.read_fits(stray_light_vector_path)
        
        # Multiprocessing server init
        job_server, ncpus = self._init_pp_server() 

        corr_interf_list_file = self.open_file(
            self._get_corrected_interferogram_list_path())

        # Interferogram creation
        progress = ProgressBar(self.dimz)
        for ik in range(0, self.dimz, ncpus):
            # No more jobs than frames to compute
            if (ik + ncpus >= self.dimz): 
                ncpus = self.dimz - ik

            frames = np.empty((self.dimx, self.dimy, ncpus), dtype=float)
            
            jobs = [(ijob, job_server.submit(
                _correct_frame,
                args=(np.array(self.get_data_frame(ik+ijob)),
                      transmission_vector[ik+ijob],
                      stray_light_vector[ik+ijob]),
                modules=('import numpy as np',)))
                    for ijob in range(ncpus)]

            for ijob, job in jobs:
                frames[:,:,ijob] = job()
                
            for ijob in range(ncpus):
                corr_interf_frame_path = (
                    self._get_corrected_interferogram_frame_path(ik + ijob))
                
                corr_interf_list_file.write(corr_interf_frame_path + "\n")
                self.write_fits(
                    corr_interf_frame_path, frames[:,:,ijob], 
                    silent=True,
                    fits_header=self._get_corrected_interferogram_frame_header(),
                    overwrite=self.overwrite)
            progress.update(ik, info="Correcting frame %d"%ik)

        progress.end()
        corr_interf_list_file.close()

        if self.indexer is not None:
            self.indexer['corr_interf_list'] = (
                self._get_corrected_interferogram_list_path())
            
        self._close_pp_server(job_server)
            

    def compute_spectrum(self, calibration_laser_map_path, bin, step, order,
                         nm_laser, zpd_shift=None, polyfit_deg=1,
                         n_phase=None, bad_frames_vector=None,
                         window_type=None, stars_cube=False,
                         phase_cube=False, phase_map_0_path=None,
                         phase_coeffs=None, filter_file_path=None,
                         balanced=True, smoothing_deg=2, fringes=None,
                         wavenumber=False):
        
        """Compute the spectrum from the corrected interferogram
        frames. Can be used to compute spectrum for camera 1, camera 2
        or merged interferogram.

        :param calibration_laser_map_path: Path to the calibration
          map. If set to None, the spectrum cube will not be
          calibrated in wavelength.

        :param bin: The binning of the interferogram frames (equal to
          the binning of the camera 1)
          
        :param order: Folding order
          
        :param step: Step size in nm

        :param zpd_shift: (Optional) Shift of the ZPD in
          frames. Automaticaly computed if none given.

        :param window_type: (Optional) Apodization window to be used
          (Default None, no apodization)

        :param n_phase: (Optional) Number of points around ZPD to use
          for phase correction. If 0, no phase correction will be done
          and the resulting spectrum will be the absolute value of the
          complex spectrum. If None, the number of points is set to 50
          percent of the interferogram length (default None).

        :param polyfit_deg: (Optional) Degree of the polynomial fit to
          the computed phase. If < 0, no fit will be performed
          (Default 1).

        :param bad_frames_vector: (Optional) Mask-like vector
          containing ones for bad frames. Bad frames are replaced by
          zeros using a special function that smoothes transition
          between good parts and zeros (default None).

        :param stars_cube: (Optional) If True the process is optimized
          for an interferogram cube containing only the interferogram
          of some stars (This type of cube is mostly filled with
          zeros). The resulting spectrum cube will be saved with a
          different name (default False).

        :param phase_cube: (Optional) If True, only the phase cube is
          returned. The number of points of the phase can be defined
          with the option n_phase. The option polyfit_deg is
          automatically set to -1 and the phase is returned without
          being fitted (default False).

        :param phase_map_0_path: (Optional) This map contains the 0th
          order coefficient of the phase. It must have the same
          dimensions as the frames of the interferogram cube (default
          None).

        :param phase_coeffs: (Optional) Phase coefficiens other than
          the 0th order coefficient which is given by the phase
          map_0. The phase coefficients are defined for a fixed number
          of phase points and a given zpd shift. To avoid errors use
          the same number of phase points for the spectrum computation
          and for the phase computation. Try also to keep track of the
          shift use to compute the phase cube (default None).

        :param filter_file_path: (Optional) Path to the filter
          file. If given the filter edges are used to give a weight to
          the phase points. See
          :meth:`process.Spectrum.correct_filter` for more information
          about the filter file.

        :param balanced: (Optional) If False, the interferogram is
          considered as unbalanced. It is flipped before its
          transformation to get a positive spectrum. Note that a
          merged interferogram is balanced (default True).

        :param smoothing_deg: (Optional) Degree of zeros smoothing. A
          higher degree means a smoother transition from zeros parts
          (bad frames) to non-zero parts (good frames) of the
          interferogram. Good parts on the other side of the ZPD in
          symmetry with zeros parts are multiplied by 2. The same
          transition is used to multiply interferogram points by zero
          and 2 (default 2).

        :param fringes: (Optional) If not None, must be an array
          giving for each fringe to remove its frequency and
          intensity. The array must be like [[freq1, amp1], [freq2,
          amp2], [freq3, amp3], ...]. Fringes are removed by dividing
          the interferograms by a sinusoidal function representing a
          periodically variable modulation efficiency (default None).
          
        :param wavenumber: (Optional) If True, the returned spectrum
          is projected onto its original wavenumber axis (emission
          lines and especially unapodized sinc emission lines are thus
          symetric which is not the case if the spectrum is projected
          onto a, more convenient, regular wavelength axis) (default
          False).
    
        .. Note:: External phase computation:

          In order to achieve a better phase correction it can be
          useful to compute some of the phase coefficients from an
          external source. Two parameters must be used **together** :
          `phase_map_path` and `phase_coeffs` which can be computed
          using :class:`process.Phase`.
        
        .. Note:: Spectrum computation walks through 8 steps:
        
           1. Mean interferogram subtraction to suppress the
              zero-frequency term in the spectrum
           
           2. Low order polynomial subtraction to suppress low
              frequency noise in the spectrum
           
           3. Apodization (the user can choose which apodization
              function to use)
           
           4. Zero-padding to have two times more points in the
              interferogram in order to keep the same resolution during
              the Fourier transform.

           5. ZPD shift to correct for a non-centered ZPD.
           
           6. Fast Fourier Transform of the interferogram
           
           7. Phase correction (if the user chooses to get the real
              part of the spectrum with phase correction instead of the
              power spectrum)

           8. Wavelength correction using the data obtained with the
              calibration cube.

        .. seealso:: :meth:`orb.utils.transform_interferogram`
        .. seealso:: :class:`process.Phase`
        """

        def _compute_spectrum_in_column(nm_laser, 
                                        calibration_laser_map_column, step,
                                        order, 
                                        data, window_type, zpd_shift,
                                        polyfit_deg, n_phase,
                                        bad_frames_vector, phase_map_column,
                                        phase_coeffs, return_phase,
                                        balanced, filter_min, filter_max,
                                        smoothing_deg, fringes, wavenumber):
            """Compute spectrum in one column. Used to parallelize the
            process"""
            dimz = data.shape[1]
            if not return_phase:
                spectrum_column = np.zeros_like(data)
            else:
                spectrum_column = np.zeros((data.shape[0],
                                            n_phase))
                
            for ij in range(data.shape[0]):
                # throw out interferograms with less than half non-zero values
                # (zero values are considered as bad points : cosmic rays, bad
                # frames etc.)
                if len(np.nonzero(data[ij,:])[0]) > dimz/2.:
                    
                    # Compute external phase vector from given coefficients
                    if phase_map_column is not None and phase_coeffs is not None:
                        coeffs_list = list()
                        coeffs_list.append(phase_map_column[ij])
                        coeffs_list += phase_coeffs
                        ext_phase = np.polynomial.polynomial.polyval(
                            np.arange(dimz), coeffs_list)
                            
                    else:
                        ext_phase = None

                    # Weights definition if the phase has to be
                    # defined for each pixel (no external phase
                    # provided)
                    weights = np.zeros(n_phase)
                    if (ext_phase is None
                        and n_phase != 0
                        and filter_min is not None
                        and filter_max is not None):
                        weights += 1e-20
                        filter_min_pix, filter_max_pix = (
                            orb.utils.get_filter_edges_pix(
                                None,
                                calibration_laser_map_column[ij] / nm_laser,
                                step, order, n_phase,
                                filter_min=filter_min,
                                filter_max=filter_max))
                        weights[filter_min_pix:filter_max_pix] = 1.

                    interf = np.copy(data[ij,:])

                    # defringe
                    if fringes is not None and not return_phase:
                        for ifringe in range(len(fringes)):
                            fringe_vector = orb.utils.variable_me(
                                dimz, [fringes[ifringe, 0],
                                       fringes[ifringe, 1], 0.])
                            
                            interf = interf / fringe_vector
                    
                    # Spectrum computation
                    spectrum_column[ij,:] = orb.utils.transform_interferogram(
                        interf, nm_laser, calibration_laser_map_column[ij],
                        step, order, window_type, zpd_shift,
                        bad_frames_vector=bad_frames_vector,
                        n_phase=n_phase,
                        polyfit_deg=polyfit_deg,
                        ext_phase=ext_phase,
                        return_phase=return_phase,
                        balanced=balanced,
                        weights=weights,
                        smoothing_deg=smoothing_deg,
                        wavenumber=wavenumber)
                        
            return spectrum_column
            
        # Ratio of the phase length over the interferogram length. It
        # must be no greater than 1 because phase vector can be no
        # greater than the interferogram length.
        PHASE_LEN_RATIO = .7

        if not phase_cube:
            self._print_msg("Computing spectrum", color=True)
        else: 
            self._print_msg("Computing phase", color=True)
            polyfit_deg = -1 # no fit must be made when computing a
                             # phase cube
            
        order = float(order)
        step = float(step)
        
        ## Defining the number of points for the phase computation.
        # The number of points by default is greater for phase
        # cube computation than phase correction
        if n_phase is None:
            n_phase = int(PHASE_LEN_RATIO * float(self.dimz))
            
        if n_phase > self.dimz:
            n_phase = self.dimz
            self._print_warning("The number of points for the phase computation is too high (it can be no greater than the interferogram length). Phase is computed with the maximum number of points available (%d)"%n_phase)
            
        self._print_msg("Phase will be computed with %d points"%n_phase)

        ## Calibration map loading and interpolation
        if calibration_laser_map_path is not None:
            self._print_msg("loading calibration laser map")
            wavelength_calibration = True
            calibration_laser_map = self.read_fits(calibration_laser_map_path)
            if (calibration_laser_map.shape[0] != self.dimx):
                calibration_laser_map = orb.utils.interpolate_map(
                    calibration_laser_map, self.dimx, self.dimy)
        else:
            # no calibration: the calibration laser wavelength is set
            # to the real one (laser_nm) so that no calibration has to
            # be done.
            self._print_warning('No wavelength calibration')
            wavelength_calibration = False
            calibration_laser_map = np.empty(
                (self.dimx, self.dimy), dtype=float)
            calibration_laser_map.fill(nm_laser)
            
        ## Defining regular wavelength axis
        if not phase_cube:
            axis_len = self.dimz
        else:
            axis_len = n_phase
        
        #############################
        ## Note: variable names are all "spectrum" related even if it
        ## is possible to get only the phase cube. Better for the
        ## clarity of the code
        #############################

        ## Searching ZPD shift 
        if zpd_shift is None:
            zpd_shift = orb.utils.find_zpd(self.get_zmedian(nozero=True),
                                           return_zpd_shift=True)

        self._print_msg("Zpd will be shifted from %d frames"%zpd_shift)

        ## Loading phase map and phase coefficients
        if (phase_map_0_path is not None and phase_coeffs is not None
            and n_phase > 0):
            phase_map_0 = self.read_fits(phase_map_0_path)
        else:
            phase_map_0 = np.zeros((self.dimx, self.dimy), dtype=float)
            phase_coeffs = None
            
        ## Check spectrum polarity
            
        # Note: The Oth order phase map is defined modulo pi. But a
        # difference of pi in the 0th order of the phase vector change
        # the polarity of the spectrum (the returned spectrum is
        # reversed). As there is no way to know the correct phase,
        # spectrum polarity must be tested. We get the mean
        # interferogram and transform it to check.
        if (phase_map_0_path is not None and phase_coeffs is not None
                and n_phase > 0):
            
            self._print_msg("Check spectrum polarity")
            
            # get mean interferogram
            mean_interf = self.get_zmean(nozero=True)

            # create mean phase vector
            
            coeffs_list_mean = list()
            coeffs_list_mean.append(np.mean(phase_map_0))
            coeffs_list_mean += phase_coeffs
            mean_phase_vector = np.polynomial.polynomial.polyval(
                np.arange(self.dimz),
                coeffs_list_mean)

            # transform interferogram and check polarity
            mean_spectrum = orb.utils.transform_interferogram(
                mean_interf, nm_laser, nm_laser, step, order, '2.0', zpd_shift,
                n_phase=n_phase, ext_phase=mean_phase_vector,
                return_phase=False, balanced=balanced, wavenumber=wavenumber)

            if np.mean(mean_spectrum) < 0:
                self._print_msg("Negative polarity : 0th order phase map has been corrected (add PI)")
                phase_map_0 += math.pi
      
        ## Spectrum computation

        # Print some informations about the spectrum transformation
        
        self._print_msg("Apodization function: %s"%window_type)
        self._print_msg("Zeros smoothing degree: %d"%smoothing_deg)
        self._print_msg("Folding order: %f"%order)
        self._print_msg("Step size: %f"%step)
        self._print_msg("Bad frames: %s"%str(np.nonzero(bad_frames_vector)[0]))
        self._print_msg("Wavenumber output: {}".format(wavenumber))
        self._print_msg("Wavelength calibration: {}".format(
            wavelength_calibration))
        if fringes is not None:
            if not phase_cube:
                self._print_msg("Fringes:")
                for ifringe in range(fringes.shape[0]):
                    self._print_msg("fringe %d: %s"%(ifringe, str(fringes[ifringe,:])))
            else:
                self._print_warning(
                    "Defringing will not be done before phase computation")
        
        # get filter min and filter max edges for weights definition
        # in case no external phase is provided
        if n_phase != 0 and filter_file_path is not None:
            (filter_nm, filter_trans,
             filter_min, filter_max) = orb.utils.read_filter_file(
                filter_file_path)
        else:
            filter_min = None
            filter_max = None

        if not wavenumber:
            axis = orb.utils.create_nm_axis(axis_len, step, order)
        else:
            axis = orb.utils.create_cm1_axis(axis_len, step, order)
        
        for iquad in range(0, self.QUAD_NB):
            x_min, x_max, y_min, y_max = self.get_quadrant_dims(iquad)
            iquad_data = self.get_data(x_min, x_max, 
                                       y_min, y_max, 
                                       0, self.dimz)
                       
            # multi-processing server init
            job_server, ncpus = self._init_pp_server()
            progress = ProgressBar(x_max - x_min)
            for ii in range(0, x_max - x_min, ncpus):
                # no more jobs than columns
                if (ii + ncpus >= x_max - x_min): 
                    ncpus = x_max - x_min - ii
                    
                # jobs creation      
                jobs = [(ijob, job_server.submit(
                    _compute_spectrum_in_column, 
                    args=(nm_laser, 
                          calibration_laser_map[x_min + ii + ijob,
                                                y_min:y_max], 
                          step, order, iquad_data[ii+ijob,:,:], 
                          window_type, zpd_shift, polyfit_deg,
                          n_phase, bad_frames_vector,
                          phase_map_0[x_min + ii + ijob, y_min:y_max],
                          phase_coeffs, phase_cube, balanced,
                          filter_min, filter_max, smoothing_deg,
                          fringes, wavenumber), 
                    modules=("import numpy as np", "import math",  
                             "from scipy import interpolate", 
                             "from scipy import fftpack, signal", 
                             "import orb.utils")))
                        for ijob in range(ncpus)]

                for ijob, job in jobs:
                    # spectrum comes in place of the interferograms
                    # to avoid using too much memory
                    iquad_data[ii+ijob,:,0:axis_len] = job()

                progress.update(ii, info="Quad %d/%d column : %d"%(
                        iquad+1L, self.QUAD_NB, ii))
            self._close_pp_server(job_server)
            progress.end()
            
            ## SAVE returned data by quadrants
            progress = ProgressBar(axis_len)
            for iframe in range(axis_len):
                progress.update(iframe, info='Saving data')
                spectrum_frame_path = self._get_spectrum_frame_path(
                    iframe, stars_cube=stars_cube, phase=phase_cube)
                
                # save data in a *.IQUAD file
                self.write_fits(
                    spectrum_frame_path+'.%d'%(iquad), iquad_data[:,:,iframe],
                    silent=True, overwrite=True)
            progress.end()

        # merge *.IQUAD files
        progress = ProgressBar(axis_len)
        for iframe in range(axis_len):
            progress.update(iframe, info='Merging quads')
            frame = np.empty((self.dimx, self.dimy), dtype=float)
            spectrum_frame_path = self._get_spectrum_frame_path(
                iframe, stars_cube=stars_cube, phase=phase_cube)
            for iquad in range(0, self.QUAD_NB):
                x_min, x_max, y_min, y_max = self.get_quadrant_dims(iquad)
                frame[x_min:x_max, y_min:y_max] = self.read_fits(
                    spectrum_frame_path+'.%d'%(iquad), delete_after=True)
            self.write_fits(
                spectrum_frame_path, frame,
                silent=True,
                fits_header=self._get_spectrum_frame_header(
                    iframe, 
                    axis, window_type, wavenumber=wavenumber),
                overwrite=True)
                
        progress.end()
        
        # write list of spectrum files
        list_file_path = self._get_spectrum_list_path(stars_cube=stars_cube,
                                                      phase=phase_cube)
        list_file = self.open_file(list_file_path)
        for iframe in range(axis_len):
            spectrum_frame_path = self._get_spectrum_frame_path(
                iframe, stars_cube=stars_cube, phase=phase_cube)
            list_file.write('%s\n'%spectrum_frame_path)
                
        list_file.close()

        # Create indexer key
        if not phase_cube:
            self._print_msg("Spectrum computed")
            list_file_key = 'spectrum_list'
            if stars_cube: list_file_key = 'stars_' + list_file_key
        else:
            self._print_msg("Phase computed")
            list_file_key = 'phase_list'
            if stars_cube: list_file_key = 'stars_' + list_file_key
            

        if self.indexer is not None:
                self.indexer[list_file_key] = list_file_path


    def extract_stars_spectrum(self, star_list_path, fwhm_arc, fov,
                               transmission_vector_path,
                               stray_light_vector_path,
                               calibration_laser_map_path, step,
                               order, nm_laser, filter_file_path,
                               step_nb, window_type=None,
                               bad_frames_vector=None,
                               smoothing_deg=2,
                               aperture=True, profile_name='gaussian',
                               moffat_beta=3.5, filter_correct=True,
                               flat_spectrum_path=None, aper_coeff=3.,
                               saturation=None):
        
        """
        Extract the spectrum of the stars in a list of stars location
        list by photometry.

        This method may be used after
        :py:meth:`process.Interferogram.correct_interferogram` has
        created the nescessary data: transmission vector and added
        light vector.
        
        :param star_list_path: Path to a list of star positions. A
          list of star positions can also be given as a list of tuples
          [(x0, y0), (x1, y1), ...].
        
        :param fwhm_arc: rough FWHM of the stars in arcsec
        
        :param fov: Field of view of the frame in arcminutes (given
          along x axis.

        :param transmission_vector_path: Variation of the sky
          transmission. Must have the same size as the interferograms
          of the cube.

        :param stray_light_vector_path: stray light vector. Must have
          the same size as the interferograms of the cube.

        :param calibration_laser_map_path: Path to the calibration
          laser map.
          
        :param order: Folding order
          
        :param step: Step size in nm

        :param filter_file_path: Path to the filter file. If given the
          filter edges can be used to give a weight to the phase
          points. See :meth:`process.Spectrum.correct_filter` for more
          information about the filter file.

        :param step_nb: Full number of steps in the interferogram. Can
          be greater than the real number of steps if the cube has
          been stopped before the end. Missing steps will be replaced
          by zeros.
          
        :param window_type: (Optional) Apodization window to be used
          (Default None, no apodization)

        :param bad_frames_vector: (Optional) Mask-like vector
          containing ones for bad frames. Bad frames are replaced by
          zeros using a special function that smoothes transition
          between good parts and zeros (default None).

        :param aperture: (Optional) If True, flux of stars is computed
          by aperture photometry. Else, The flux is evaluated given
          the fit parameters (default True).

        :param profile_name: (Optional) PSF profile to use to fit
          stars. Can be 'gaussian' or 'moffat' (default
          'gaussian'). See:
          :py:meth:`orb.astrometry.Astrometry.fit_stars_in_frame`.
          
        :param moffat_beta: (Optional) Beta parameter to use for
          moffat PSF (default 3.5).

        :param filter_correct: (Optional) If True returned spectra
          are corrected for filter. Points out of the filter band
          are set to NaN (default True).

        :param flat_spectrum_path: (Optional) Path to a list of flat
          spectrum frames. This is used to further correct the
          resulting stars spectrum for fringing effects (default None).

        :param aper_coeff: (Optional) Aperture coefficient. The
          aperture radius is Rap = aper_coeff * FWHM. Better when
          between 1.5 to reduce the variation of the collected photons
          with varying FWHM and 3. to account for the flux in the
          wings (default 3., better for star with a high SNR).

        :param saturation: (Optional) If not None, all pixels above
          the saturation level are removed from the fit (default None).
        """
        
        PHASE_LEN_COEFF = 0.8 # Ratio of the number of points used to
                              # define phase over the total number of
                              # points of the interferograms
        
        # Loading flat spectrum cube
        if flat_spectrum_path is not None:
            flat_cube = Cube(flat_spectrum_path,
                             config_file_name=self.config_file_name)
        else:
            flat_cube = None
    
        ## COMPUTING STARS INTERFEROGRAM
        self._print_msg("Computing stars photometry")
        
        if aperture:
            self._print_msg('Star flux evaluated by aperture photometry')
            photometry_type = 'aperture_flux'
        else:
            self._print_msg('Star flux evaluated by profile fitting')
            photometry_type = 'flux'

        if isinstance(star_list_path, str):
            star_list = orb.astrometry.load_star_list(star_list_path)
        else:
            star_list = star_list_path
        
        astrom = Astrometry(self, fwhm_arc, fov,
                            profile_name=profile_name,
                            moffat_beta=moffat_beta,
                            data_prefix=self._data_prefix + 'cam1.',
                            logfile_name=self._logfile_name,
                            tuning_parameters=self._tuning_parameters,
                            config_file_name=self.config_file_name)
        astrom.reset_star_list(star_list)

        # Fit stars and get stars photometry
        astrom.fit_stars_in_cube(local_background=False,
                                 fix_aperture_size=False,
                                 precise_guess=True,
                                 aper_coeff=aper_coeff,
                                 multi_fit=True,
                                 saturation=saturation)
        
        astrom.load_fit_results(astrom._get_fit_results_path())
        photom = astrom.fit_results[:,:,photometry_type]

        if astrom.star_nb == 1:
            photom = photom[np.newaxis, :]
            
        transmission_vector = np.squeeze(
            self.read_fits(transmission_vector_path))
        stray_light_vector = np.squeeze(
            self.read_fits(stray_light_vector_path))

        # compute equivalent surface to substract stray light
        # correctly from the integrated flux
        surf_eq = (4. * math.pi *  orb.utils.robust_median(
            (astrom.fit_results[:,:,'fwhm']
             / orb.constants.FWHM_COEFF)**2.))
        
        star_interf_list = list()
        for istar in range(astrom.star_list.shape[0]):
            star_interf_list.append([
                (photom[istar,:] / transmission_vector)
                - stray_light_vector * surf_eq,
                star_list[istar]])

        ## COMPUTING STARS SPECTRUM
            
        # Loading calibration laser map
        self._print_msg("loading calibration laser map")
        calibration_laser_map = self.read_fits(calibration_laser_map_path)
        if (calibration_laser_map.shape[0] != self.dimx):
            calibration_laser_map = orb.utils.interpolate_map(
                calibration_laser_map, self.dimx, self.dimy)
            
        ## Searching ZPD shift 
        zpd_shift = orb.utils.find_zpd(self.get_zmedian(nozero=True),
                                       return_zpd_shift=True,
                                       step_number=step_nb)
        
        
        self._print_msg('Auto-phase: phase will be computed for each star independantly (No use of external phase)')
            
        ## Spectrum computation

        # Print some information about the spectrum transformation
        self._print_msg("Apodization function: %s"%window_type)
        self._print_msg("Zeros smoothing degree: %d"%smoothing_deg)
        self._print_msg("Folding order: %f"%order)
        self._print_msg("Step size: %f"%step)
        self._print_msg("Bad frames: %s"%str(np.nonzero(bad_frames_vector)[0]))

        # get filter min and filter max edges for weights definition
        # in case no external phase is provided
        (filter_nm, filter_trans,
         filter_min, filter_max) = orb.utils.read_filter_file(filter_file_path)

        # load filter function for filter correction
        if filter_correct:
            (filter_function,
             filter_min_pix, filter_max_pix) = orb.utils.get_filter_function(
                filter_file_path, step, order, step_nb)

        star_spectrum_list = list()
        for istar in range(len(star_interf_list)):
            star_interf = star_interf_list[istar][0]
            star_x, star_y = star_interf_list[istar][1]

            # Add missing steps
            if np.size(star_interf) < step_nb:
                temp_interf = np.zeros(step_nb)
                temp_interf[:np.size(star_interf)] = star_interf
                star_interf = temp_interf

        
            # Weights definition if the phase has to be
            # defined for each star (no external phase
            # provided)
            
            n_phase = int(PHASE_LEN_COEFF * step_nb)

            weights = np.zeros(n_phase)
            
            weights += 1e-20
            weights_min_pix, weights_max_pix = (
                orb.utils.get_filter_edges_pix(
                    None,
                    (calibration_laser_map[int(star_x), int(star_y)]
                     / nm_laser),
                    step, order, n_phase, filter_min=filter_min,
                    filter_max=filter_max))
            weights[weights_min_pix:weights_max_pix] = 1.
       
            star_spectrum = orb.utils.transform_interferogram(
                star_interf, nm_laser,
                calibration_laser_map[int(star_x), int(star_y)],
                step, order, window_type, zpd_shift,
                bad_frames_vector=bad_frames_vector,
                n_phase=n_phase,
                ext_phase=None,
                balanced=True,
                weights=weights,
                smoothing_deg=smoothing_deg)

            # check polarity
            if np.mean(star_spectrum) < 0.:
                star_spectrum = -star_spectrum

            # rescale
            scale = (orb.utils.spectrum_mean_energy(star_spectrum)
                     / orb.utils.interf_mean_energy(star_interf))
            star_spectrum *= scale
            
            # filter correction
            if filter_correct:
                star_spectrum /= filter_function
                star_spectrum[:filter_min_pix] = np.nan
                star_spectrum[filter_max_pix:] = np.nan
               
            # flat correction
            if flat_cube is not None:
                # extracting flat spectrum in the region of the star
                (x_min, x_max,
                 y_min, y_max) = orb.utils.get_box_coords(star_x, star_y,
                                                astrom.box_size,
                                                0, self.dimx,
                                                0, self.dimy)
                x_min = int(x_min)
                x_max = int(x_max)
                y_min = int(y_min)
                y_max = int(y_max)
                star_fwhm = orb.utils.robust_mean(
                    orb.utils.sigmacut(astrom.fit_results[istar,:,'fwhm']))
                star_profile = astrom.profile(
                    astrom.fit_results[istar,0]).array2d(astrom.box_size,
                                                         astrom.box_size)
                flat_spectrum = list()
                for iframe in range(flat_cube.dimz):
                    star_box = flat_cube[x_min:x_max, y_min:y_max, iframe]
                    star_box *= star_profile
                    flat_spectrum.append(orb.astrometry.aperture_photometry(
                        star_box, star_fwhm, background_guess=0.)[0])
                flat_spectrum = np.squeeze(np.array(flat_spectrum))

                # flat spectrum is made 'flat' to remove its 'black
                # body' shape
                weights = np.zeros(flat_spectrum.shape[0])
                weights[np.nonzero(flat_spectrum)] = 1.
                
                flat_spectrum /= orb.utils.polyfit1d(flat_spectrum, 1,
                                           w=weights)

                star_spectrum[:filter_min_pix] = np.nan
                star_spectrum[filter_max_pix:] = np.nan
                flat_spectrum[:filter_min_pix] = np.nan
                flat_spectrum[filter_max_pix:] = np.nan
                star_spectrum /= flat_spectrum

            self._print_msg('Star %d mean flux: %f ADU'%(
                    istar, orb.utils.robust_mean(star_spectrum)))
            
            star_spectrum_list.append(star_spectrum)
        star_spectrum_list = np.array(star_spectrum_list)

        # write spectra
        self.write_fits(self._get_extracted_star_spectra_path(),
                        star_spectrum_list,
                        fits_header=self._get_extracted_star_spectra_header(),
                        overwrite=self.overwrite)
        if self.indexer is not None:
            self.indexer['extracted_star_spectra'] = (
                self._get_extracted_star_spectra_path())

        return star_spectrum_list
    
    
##################################################
#### CLASS InterferogramMerger ###################
##################################################

class InterferogramMerger(Tools):
    """ORBS interferogram merging class.

    The InterferogramMerger class is aimed to merge the interferogram
    cubes of the two cameras of SpIOMM/SITELLE.

    .. note:: In this class the letter 'A' refers to the camera 1 and the
       letter 'B' to the camera 2
    """
    
    cube_A = None
    cube_B = None
    dx = None
    dy = None
    dr = None
    da = None
    db = None
    xc = None
    yc = None
    rc = None
    zoom_factor = None
    alignment_coeffs = None
    
    pix_size_A = None
    pix_size_B = None
    bin_A = None
    bin_B = None
    
    overwrite = False
    
    _data_prefix = None
    config_file_name = None
    ncpus = None
    _msg_class_hdr = None
    _data_path_hdr = None
    _project_header = None
    _wcs_header = None
    
    def __init__(self, image_list_path_A=None, image_list_path_B=None,
                 bin_A=None, bin_B=None, pix_size_A=None, pix_size_B=None,
                 data_prefix="temp_data_",
                 alignment_coeffs=None, project_header=list(),
                 config_file_name="config.orb",
                 cube_A_project_header = list(),
                 cube_B_project_header = list(),
                 wcs_header=list(), overwrite=False,
                 tuning_parameters=dict(),
                 indexer=None, logfile_name=None):
        """
        Initialize InterferogramMerger class

        :param image_list_path_A: (Optional) Path to the image list of
          the camera 1

        :param image_list_path_B: (Optional) Path to the image list of
          the camera 2

        :param bin_A: (Optional) Binning factor of the camera A

        :param bin_B: (Optional) Binning factor of the camera B

        :param pix_size_A: (Optional) Pixel size of the camera A
        
        :param pix_size_A: (Optional) Pixel size of the camera B

        :param data_prefix: (Optional) Header and path of the files
          created by the class

        :param config_file_name: (Optional) name of the config file to
          use. Must be located in orbs/data/.

        :param project_header: (Optional) header section to be added
          to each output files based on merged data (an empty list by
          default).

        :param cube_A_project_header: (Optional) header section to be
          added to each output files based on pure cube A data (an
          empty list by default).

        :param cube_B_project_header: (Optional) header section to be
          added to each output files based on pure cube B data (an
          empty list by default).

        :param wcs_header: (Optional) header section describing WCS
          that can be added to each created image files (an empty list
          by default).

        :param alignment_coeffs: (Optional) Pre-calculated alignement
          coefficients. Setting alignment_coeffs to something else
          than 'None' will avoid alignment coeffs calculation in
          :meth:`process.InterferogramMerger.find_alignment`

        :param overwrite: (Optional) If True existing FITS files will
          be overwritten (default False).

        :param tuning_parameters: (Optional) Some parameters of the
          methods can be tuned externally using this dictionary. The
          dictionary must contains the full parameter name
          (class.method.parameter_name) and its value. For example :
          {'InterferogramMerger.find_alignment.BOX_SIZE': 7}. Note
          that only some parameters can be tuned. This possibility is
          implemented into the method itself with the method
          :py:meth:`orb.core.Tools._get_tuning_parameter`.

        :param indexer: (Optional) Must be a :py:class:`orb.core.Indexer`
          instance. If not None created files can be indexed by this
          instance.

        :param logfile_name: (Optional) Give a specific name to the
          logfile (default None).
        """
        self._init_logfile_name(logfile_name)
        self.overwrite = overwrite
        self.indexer = indexer
        self._data_prefix = data_prefix
        self.config_file_name = config_file_name
        self.ncpus = int(self._get_config_parameter("NCPUS"))
        self._project_header = project_header
        self._wcs_header = wcs_header
        self._msg_class_hdr = self._get_msg_class_hdr()
        self._data_path_hdr = self._get_data_path_hdr()
        self._tuning_parameters = tuning_parameters
        
        if alignment_coeffs is not None:
            [self.dx, self.dy, self.dr, self.da, self.db] = alignment_coeffs

        if image_list_path_A is not None:
            self.cube_A = Cube(image_list_path_A,
                               project_header=cube_A_project_header,
                               config_file_name=self.config_file_name)
        if image_list_path_B is not None:
            self.cube_B = Cube(image_list_path_B,
                               project_header=cube_B_project_header,
                               config_file_name=self.config_file_name)

        self.bin_A = bin_A
        self.bin_B = bin_B
        self.pix_size_A = pix_size_A
        self.pix_size_B = pix_size_B
        # defining zoom factor
        if (self.pix_size_A is not None and self.pix_size_B is not None
            and self.bin_A is not None and self.bin_B is not None):
            self.zoom_factor = ((float(self.pix_size_B) * float(self.bin_B)) / 
                                (float(self.pix_size_A) * float(self.bin_A)))
        
        # defining rotation center
        if self.cube_B is not None:
            self.rc = [(float(self.cube_B.dimx) / 2.), 
                       (float(self.cube_B.dimy) / 2.)]



    def _get_modulation_ratio_path(self):
        """Return the path to the modulation ratio."""
        return self._data_path_hdr + "modulation_ratio.fits"

    def _get_modulation_ratio_header(self):
        """Return the header of the modulation ratio."""
        return (self._get_basic_header('Modulation ratio')
                + self._project_header)
        
    def _get_energy_map_path(self):
        """Return the path to the energy map.

        The energy map is the mean frame from the merged cube. It is
        useful to check the alignement.
        """
        return self._data_path_hdr + "energy_map.fits"

    def _get_energy_map_header(self):
        """Return the header of the energy map."""
        return (self._get_basic_header('Energy map')
                + self._project_header
                + self._get_basic_frame_header(
                    self.cube_A.dimx, self.cube_A.dimy))

    def _get_stray_light_vector_path(self):
        """Return the path to the stray light vector.

        The external illuminaton vector records lights coming from
        reflections over clouds, the moon or the sun.
        """
        return self._data_path_hdr + "stray_light_vector.fits"

    def _get_stray_light_vector_header(self):
        """Return the header of the stray light vector."""
        return (self._get_basic_header('stray light vector')
                + self._project_header)
   
    def _get_ext_illumination_vector_path(self):
        """Return the path to the external illumination vector.

        The external illuminaton vector records the external
        illumination difference between both cameras (e.g. if one
        camera get some diffused light from the sky while the other is
        well isolated). This vector is used to correct
        interferograms.
        """
        return self._data_path_hdr + "ext_illumination_vector.fits"

    def _get_ext_illumination_vector_header(self):
        """Return the header of the external illumination vector."""
        return (self._get_basic_header('External illumination vector')
                + self._project_header)
    
    def _get_transmission_vector_path(self, err=False):
        """Return the path to the transmission vector.

        Transmission vector is the vector used to correct
        interferograms for the variations of the sky transmission.

        :param err: (Optional) True if error vector (default False).
        """
        if not err:
            return self._data_path_hdr + "transmission_vector.fits"
        else:
            return self._data_path_hdr + "transmission_vector_err.fits"

    def _get_transmission_vector_header(self, err=False):
        """Return the header of the transmission vector.

        :param err: (Optional) True if error vector (default False).
        """
        if not err:
            return (self._get_basic_header('Transmission vector')
                    + self._project_header)
        else:
            return (self._get_basic_header('Transmission vector error')
                    + self._project_header)


    def _get_calibration_stars_path(self):
        """Return the path to a data file containing the merged
        interferograms of the calibrated stars"""
        
        return self._data_path_hdr + "calibration_stars.fits"

    def _get_calibration_stars_header(self):
        """Return the header of the calibration stars data file."""
        return (self._get_basic_header('Calibration stars interferograms')
                + self._project_header)

    def _get_extracted_star_spectra_path(self):
        """Return the path to a data file containing the spectra of
        the extracted stars"""
        return self._data_path_hdr + "extracted_star_spectra.fits"

    def _get_extracted_star_spectra_header(self):
        """Return the header of a data file containing the spectra of
        the extracted stars"""
        return (self._get_basic_header('Extracted star spectra')
                + self._project_header)


    def _get_deep_frame_path(self):
        """Return the path to the deep frame.

        The energy map is the mean frame from the merged cube. It is
        useful to check the alignement.
        """
        return self._data_path_hdr + "deep_frame.fits"

    def _get_deep_frame_header(self):
        """Return the header of the deep frame."""
        return (self._get_basic_header('Deep Frame')
                + self._project_header
                + self._get_basic_frame_header(
                    self.cube_A.dimx, self.cube_A.dimy))

    def _get_merged_interfero_frame_list_path(self):
        """Return the path to the list of frames of the merged cube"""
        return self._data_path_hdr + "interf.list"

    def _get_merged_interfero_frame_path(self, index):
        """Return the default path to the merged interferogram frames.

        :param index: Index of the merged interferogram frame.
        """
        formatted_index = "%(#)04d" %{"#":index}
        interfero_dirname = os.path.dirname(self._data_path_hdr)
        interfero_basename = os.path.basename(self._data_path_hdr)
        return (interfero_dirname + "/INTERFEROGRAM/" + interfero_basename
                + "interferogram_" + str(formatted_index) + ".fits")

    def _get_merged_interfero_frame_header(self):
        """Return the header of the merged interferogram frames."""
        return (self._get_basic_header('Merged interferogram frame')
                + self._project_header
                + self._get_basic_frame_header(self.cube_A.dimx,
                                               self.cube_A.dimy))

    def _get_bad_frames_vector_path(self):
        """Return the path to the bad frames vector.

        This vector is created by
        :py:meth:`process.InterferogramMerger.merge` method.
        """
        return self._data_path_hdr + "bad_frames_vector.fits"

    def _get_bad_frames_vector_header(self):
        """Return the header of the bad frames vector."""
        return (self._get_basic_header('Bad frames vector')
                + self._project_header)

    def _get_transformed_interfero_frame_list_path(self):
        """Return the path to the list of frames of the transformed cube"""
        return self._data_path_hdr + "transf.list"

    def _get_transformed_interfero_frame_path(self, index):
        """Return the default path to the transformed interferogram frames.
        
        :param index: Index of the transformed interferogram frame.
        """
        formatted_index = "%(#)04d" %{"#":index}
        interfero_dirname = os.path.dirname(self._data_path_hdr)
        interfero_basename = os.path.basename(self._data_path_hdr)
        return (interfero_dirname + "/TRANSFORMED_CUBE_B/" + interfero_basename
                + "transformed_cube_B_" + str(formatted_index) + ".fits")

    def _get_transformed_interfero_frame_header(self):
        """Return the header of the transformed interferogram frames."""
        return (self._get_basic_header('Transformed interferogram frame')
                + self.cube_B._project_header
                + self._get_basic_frame_header(self.cube_A.dimx,
                                               self.cube_A.dimy))

    def _get_stars_interfero_frame_list_path(self):
        """Return the path to the list of frames of the stars cube"""
        return self._data_path_hdr + "stars.list"

    def _get_stars_interfero_frame_path(self, index):
        """Return the default path to the stars interferogram frames.

        :param index: Index of the merged interferogram frame.
        """
        formatted_index = "%(#)04d" %{"#":index}
        interfero_dirname = os.path.dirname(self._data_path_hdr)
        interfero_basename = os.path.basename(self._data_path_hdr)
        return interfero_dirname + "/STARS_INTERFEROGRAM/" + interfero_basename + "stars_interferogram_" + str(formatted_index) + ".fits"

    def _get_stars_interfero_frame_header(self):
        """Return the header of the merged interferogram frames
        containing only the photometrical data for the stars.
        """
        return (self._get_basic_header('Merged stars interferogram frame')
                + self._project_header
                + self._get_basic_frame_header(self.cube_A.dimx,
                                               self.cube_A.dimy))


    def add_missing_frames(self, step_number):
        """ Add non taken frames at the end of a cube in order to
        complete it and have a centered ZDP. Useful when a cube could
        not be completed during the night.
        
        :param step_number: Number of steps for a full cube.
        """
        if step_number > self.cube_A.dimz:
            zeros_frame = np.zeros((self.cube_A.dimx, self.cube_A.dimy), dtype=float)
            image_list_text = ""
            for iframe in range(step_number):
                image_list_text += self._get_merged_interfero_frame_path(iframe) + "\n"
                if iframe >= self.cube_A.dimz:
                    self.write_fits(
                        self._get_merged_interfero_frame_path(iframe),
                        zeros_frame,
                        fits_header=self._get_merged_interfero_frame_header(),
                        overwrite=self.overwrite,
                        mask=zeros_frame)
            f = open(self._get_merged_interfero_frame_list_path(), "w")
            f.write(image_list_text)
            f.close

    def find_alignment(self, star_list_path_A, init_angle, init_dx, init_dy,
                       fwhm_arc_A, fov_A):
        """
        Return the alignment coefficients to align the cube of the
        camera 2 on the cube of the camera 1

        :param star_list_path_A: Path to a list of star for the camera A
        
        :param init_angle: Initial rotation angle between images

        :param init_dx: Initial shift along x axis between images

        :param init_dy: Initial shift along y axis between images

        :param fwhm_arc_A: rough FWHM of the stars in arcsec in the
          camera A.
        
        :param fov_A: Field of view of the camera A in arcminutes (given
          along x axis.

        .. seealso:: py:meth:`orb.astrometry.Aligner.compute_alignment_parameters`
        """
        # High pass filtering of the frames
        HPFILTER = int(self._get_tuning_parameter('HPFILTER', 0))
        
        self._print_msg("Computing alignment parameters")

        # defining FOV of the camera B
        ccd_size_A = self.bin_A * self.cube_A.dimx * self.pix_size_A
        ccd_size_B = self.bin_B * self.cube_B.dimx * self.pix_size_B
        scale = fov_A / ccd_size_A # absolute scale [arcsec/um]
        fov_B = scale * ccd_size_B

        fwhm_arc_B = float(fwhm_arc_A)
        self._print_msg("Calculated FOV of the camera B: %f arcmin"%fov_B)

        # Printing some information
        self._print_msg("Rotation center: %s"%str(self.rc))
        self._print_msg("Zoom factor: %f"%self.zoom_factor)

        # creating deep frames for cube A and B
        frameA = self.cube_A.get_mean_image()
        frameB = self.cube_B.get_mean_image()

        if HPFILTER: # Filter alignment frames
            frameA = orb.utils.high_pass_diff_image_filter(frameA, deg=1)
            frameB = orb.utils.high_pass_diff_image_filter(frameB, deg=1)
        
        aligner = Aligner(
            frameA, frameB, fwhm_arc_A, fov_A, fov_B,
            self.bin_A, self.bin_B, self.pix_size_A, self.pix_size_B,
            init_angle, init_dx, init_dy, logfile_name=self._logfile_name,
            tuning_parameters=self._tuning_parameters,
            project_header=self._project_header, overwrite=self.overwrite,
            data_prefix=self._data_prefix,
            config_file_name=self.config_file_name)
        
        result = aligner.compute_alignment_parameters(
            star_list_path1=star_list_path_A,
            fwhm_arc=fwhm_arc_A,
            correct_distorsion=False)

        [self.dx, self.dy, self.dr, self.da, self.db] = result['coeffs']
        self.rc = result['rc']
        self.zoom_factor = result['zoom_factor']
        sip1 = result['sip1']
        sip2 = result['sip2']
        

        return [[self.dx, self.dy, self.dr, self.da, self.db], self.rc, 
                self.zoom_factor]


    def transform(self, interp_order=1):
        """Transform cube B given a set of alignment coefficients.

        :param interp_order: Order of interpolation. (1: linear by default)

        .. seealso:: :meth:`orb.utils.transform_frame`
        """
        # Init of the multiprocessing server
        job_server, ncpus = self._init_pp_server()
        ncpus_max = ncpus

        framesA = np.empty((self.cube_A.dimx, self.cube_A.dimy, ncpus), 
                           dtype=float)
        framesB = np.empty((self.cube_A.dimx, self.cube_A.dimy, ncpus), 
                           dtype=float)
        framesB_mask = np.empty((self.cube_A.dimx, self.cube_A.dimy, ncpus), 
                                dtype=float)
        framesB_init = np.empty((self.cube_B.dimx, self.cube_B.dimy, ncpus), 
                                dtype=float)
        framesB_init_mask = np.empty((self.cube_B.dimx, self.cube_B.dimy,
                                      ncpus), dtype=float)
        
        transf_list_file = self.open_file(
            self._get_transformed_interfero_frame_list_path())

        self._print_msg("Transforming cube B")
        self._print_msg("Alignment parameters : %s"%str([self.dx, self.dy,
                                                         self.dr, self.da,
                                                         self.db]))
        self._print_msg("Zoom factor : %s"%str(self.zoom_factor))
        progress = ProgressBar(int(self.cube_A.dimz/ncpus_max))
        for ik in range(0, self.cube_A.dimz, ncpus):
            # no more jobs than frames to compute
            if (ik + ncpus >= self.cube_A.dimz):
                ncpus = self.cube_A.dimz - ik
            
            for ijob in range(ncpus):
                framesA[:,:,ijob] = self.cube_A.get_data_frame(ik + ijob)
                framesB_init[:,:,ijob] = self.cube_B.get_data_frame(ik + ijob)
                if self.cube_B._mask_exists:
                    framesB_init_mask[:,:,ijob] = self.cube_B.get_data_frame(
                        ik + ijob, mask=True)
                else:
                    framesB_init_mask[:,:,ijob].fill(0.)

            # transform frames of camera B to align them with those of camera A
            jobs = [(ijob, job_server.submit(
                orb.utils.transform_frame, 
                args=(framesB_init[:,:,ijob],
                      0, self.cube_A.dimx, 
                      0, self.cube_A.dimy, 
                      [self.dx, self.dy, self.dr, self.da, self.db],
                      self.rc, self.zoom_factor,
                      interp_order,
                      framesB_init_mask[:,:,ijob]),
                modules=("numpy as np", 
                         "from scipy import ndimage",
                         "import orb.cutils as cutils"))) 
                    for ijob in range(ncpus)]

            for ijob, job in jobs:
                framesB[:,:,ijob], framesB_mask[:,:,ijob] = job()
            
            for ijob in range(ncpus):
                transfo_frame_path = self._get_transformed_interfero_frame_path(
                    ik + ijob)
                transf_list_file.write(transfo_frame_path + "\n")
                self.write_fits(
                    transfo_frame_path, framesB[:,:,ijob], 
                    silent=True, 
                    fits_header=self._get_transformed_interfero_frame_header(),
                    overwrite=self.overwrite,
                    mask=framesB_mask[:,:,ijob])

            progress.update(int(ik/ncpus_max), info="frame : " + str(ik))
        self._close_pp_server(job_server)
        progress.end()

        transf_list_file.close()
        
        if self.indexer is not None:
            self.indexer['transformed_interfero_frame_list'] = self._get_transformed_interfero_frame_list_path()


    def alternative_merge(self, add_frameB=True):
        """Alternative merging process.

        Star photometry is not used during the merging process. Might
        be more noisy but useful if for some reason the correction
        vectors cannot be well computed (e.g. not enough good stars,
        intense emission lines everywhere in the field)

        :param add_frameB: (Optional) Set it to False if B frame is
           too noisy to be added to the result. In this case frame B
           is used only to correct for variations of flux from the
           source (airmass, clouds ...) (Default False).
           
        .. note:: Cubes are merged using the formula (for the nth frame):
              
              .. math::

                 Frame_{n,M} = \\frac{Frame_{n,1} -
                 Frame_{n,2}}{Frame_{n,1} + Frame_{n,2}}

        """

        def _create_merged_frame(frameA, frameB, modulation_ratio,
                                 add_frameB, transmission_scale):
            """Create the merged frame given the frames of both cubes
            and the correction factor.

            :param frameA: Frame of the camera 1
            
            :param frameB: Frame of the camera 2
            
            :param modulation_ratio: The ratio of modulation between
              the two cameras. It depends on the gain and the quantum
              efficiency of the CCD.
               
            :param add_frameB: If False the frame B is not added but
            used to determine the transmission of the sky in each
            pixel.

            :param transmission_scale: Scaling factor for the
              transmission frame
            """
            
            if np.all(frameA == 0) and np.all(frameB == 0):
                return np.zeros_like(frameA)
            
            # Correcting for the variation of sky transmission
            frameB = frameB / modulation_ratio

            # Sky transmission frame
            transmission_frame = (frameB + frameA) / transmission_scale
            bad_pix = np.nonzero(transmission_frame==0.)
            transmission_frame[bad_pix] = 1.
            
            if add_frameB:
                result_frame = ((frameB - frameA) / transmission_frame)
            else:
                result_frame = ((frameA) / transmission_frame)

            result_frame[bad_pix] = np.nan
            result_frame[np.nonzero(frameA == 0.)] = np.nan
            result_frame[np.nonzero(frameB == 0.)] = np.nan
            
            return result_frame
        
        def get_nostar_modulation_ratio(frameA, frameB, saturation_level,
                                        pix_ratio=0.015):
            """The most intense non saturated pixels are taken to
            evaluate precisely the modulation ratio.
            
            :param frameA: Frame of the camera 1
            
            :param frameB: Frame of the camera 2

            :param saturation_level: Level above which values are
              considered as saturated and thus incorrect.

            :param pix_ratio: (Optional) Percentage of the most
              intense pixels used to compute the modulation ratio.          
            """
            
            # get intensity threshold
            intensity_list = np.sort(frameA.flatten())
            intensity_list = intensity_list[np.nonzero(
                intensity_list < saturation_level)]
            threshold_number = int(np.size(frameA)*pix_ratio)
            threshold_intensity = intensity_list[-threshold_number]
            # get good pixel indexes
            good_pix = np.nonzero(
                (frameA > threshold_intensity)
                * (frameA < SATURATION_LEVEL))
            # setting bad pixels in frame A to 1.
            frameA[np.nonzero(np.isnan(frameA))] = 1.
            frameA[np.nonzero(frameA == 0.)] = 1.
            
            frames_ratio = frameB/frameA
            return orb.utils.robust_mean((frames_ratio)[good_pix])

        SATURATION_LEVEL = 65000 # Level of image saturation
        
        self._print_warning('Alternative merging process: Merging cubes without using star photometry')

        ## MODULATION RATIO
        # creating deep frames for cube A and B
        deep_frameA = self.cube_A.get_mean_image()
        deep_frameB = self.cube_B.get_mean_image()
        energy_mapA = self.cube_A.get_interf_energy_map()
        energy_mapB = self.cube_B.get_interf_energy_map()

        modulation_ratio = get_nostar_modulation_ratio(
            np.copy(deep_frameA), np.copy(deep_frameB),
            SATURATION_LEVEL/2.)

        self._print_msg(
            "Modulation ratio: %f"%
            modulation_ratio)

        ## ENERGY MAP & DEEP FRAME
        energy_map = energy_mapA * modulation_ratio + energy_mapB
        deep_frame = deep_frameA * modulation_ratio + deep_frameB
        
        self.write_fits(self._get_energy_map_path(), energy_map, 
                        fits_header=
                        self._get_energy_map_header(),
                        overwrite=self.overwrite)

        if self.indexer is not None:
            self.indexer['energy_map'] = self._get_energy_map_path()

        self.write_fits(self._get_deep_frame_path(), deep_frame, 
                        fits_header=
                        self._get_deep_frame_header(),
                        overwrite=self.overwrite)

        if self.indexer is not None:
            self.indexer['deep_frame'] = self._get_deep_frame_path()

        ## TRANSMISSION SCALE
        # scaling factor for the transmission frame during merging
        transmission_scale = np.median(deep_frameA
                                       + deep_frameB / modulation_ratio)
        
        
        ## MERGE FRAMES
        self._print_msg("Merging cubes")
        
        # Init of the multiprocessing server
        job_server, ncpus = self._init_pp_server()
        framesA = np.empty((self.cube_A.dimx, self.cube_A.dimy, ncpus),
                           dtype=float)
        ncpus_max = ncpus
        
        image_list_file = self.open_file(
            self._get_merged_interfero_frame_list_path())
        
        result_frames = np.empty(
            (self.cube_A.dimx, self.cube_A.dimy, ncpus), dtype=float)
        
        progress = ProgressBar(int(self.cube_A.dimz/ncpus_max))
        for ik in range(0, self.cube_A.dimz, ncpus):
            # no more jobs than frames to compute
            if (ik + ncpus >= self.cube_A.dimz):
                ncpus = self.cube_A.dimz - ik

            for ijob in range(ncpus):
                framesA[:,:,ijob] = self.cube_A.get_data_frame(ik + ijob)
                # result_frames are used instead of a framesB variable
                # to reduce the amount of memory used
                result_frames[:,:,ijob] = self.cube_B.get_data_frame(ik + ijob)

            # compute merged frames
            jobs = [(ijob, job_server.submit(
                _create_merged_frame, 
                args=(framesA[:,:,ijob],
                      result_frames[:,:,ijob], 
                      modulation_ratio,
                      add_frameB,
                      transmission_scale),
                modules=("numpy as np",)))
                    for ijob in range(ncpus)]
                
            for ijob, job in jobs:
                result_frames[:,:,ijob] = job()
             
            for ijob in range(ncpus):
                
                merged_frame_path = self._get_merged_interfero_frame_path(
                    ik + ijob)
                fits_header = self._get_merged_interfero_frame_header()
                image_list_file.write(merged_frame_path + "\n")
                self.write_fits(merged_frame_path, result_frames[:,:,ijob], 
                                silent=True, 
                                fits_header=fits_header,
                                overwrite=self.overwrite)

            progress.update(int(ik/ncpus_max), info="frame : " + str(ik))
        self._close_pp_server(job_server)
        progress.end()

        if self.indexer is not None:
            self.indexer['merged_interfero_frame_list'] = (
                self._get_merged_interfero_frame_list_path())
        

    def merge(self, star_list_path, step_number, fwhm_arc, fov,
              add_frameB=True, smooth_vector=True,
              create_stars_cube=False, profile_name='gaussian',
              moffat_beta=3.5, bad_frames_vector=[],
              compute_ext_light=True, aperture_photometry=True,
              readout_noise_1=10., dark_current_level_1=0.,
              readout_noise_2=10., dark_current_level_2=0.):
        
        """
        Merge the cube of the camera 1 and the transformed cube of the
        camera 2.

        :param star_list_path: Path to a list of star positions.

        :param step_number: Number of steps for a full cube.
        
        :param add_frameB: (Optional) Set it to False if B frame is
           too noisy to be added to the result. In this case frame B
           is used only to correct for variations of flux from the
           source (airmass, clouds ...) (Default False).
           
        :param smooth_vector: (Optional) If True smooth the obtained
           correction vector with a gaussian weighted moving average.
           Reduce the possible high frequency noise of the correction
           function. (Default True).

        :param fwhm_arc: rough FWHM of the stars in arcsec
        
        :param fov: Field of view of the frame in arcminutes (given
          along x axis.

        :param create_stars_cube: (Optional) If True only the
          interferogram of the stars in the star list are computed
          using their photometric parameters returned by a 2D gaussian
          fit (default False).

        :param profile_name: (Optional) PSF profile to use to fit
          stars. Can be 'gaussian' or 'moffat' (default
          'gaussian'). See:
          :py:meth:`orb.astrometry.Astrometry.fit_stars_in_frame`.

        :param moffat_beta: (Optional) Beta parameter to use for
          moffat PSF (default 3.5).

        :param bad_frames_vector: (Optional) Contains the index of the
          frames considered as bad(default []).

        :param compute_ext_light: (Optional) If True compute the
          external light vector. Make sure that there's enough 'sky'
          pixels in the frame. The vector will be deeply affected if
          the object covers the whole area (default True).

        :param aperture_photometry: (Optional) If True, flux of stars
          is computed by aperture photometry. Else, The flux is
          evaluated given the fit parameters (default True).

        :param readout_noise_1: (Optional) Readout noise in ADU/pixel
          of camera 1 (can be computed from bias frames:
          std(master_bias_frame)) (default 10.)
    
        :param dark_current_level_1: (Optional) Dark current level of
          camera 1 in ADU/pixel (can be computed from dark frames:
          median(master_dark_frame)) (default 0.)

        :param readout_noise_2: (Optional) Readout noise in ADU/pixel
          of camera 2 (can be computed from bias frames:
          std(master_bias_frame)) (default 10.)
    
        :param dark_current_level_2: (Optional) Dark current level of
          camera 2 in ADU/pixel (can be computed from dark frames:
          median(master_dark_frame)) (default 0.)

        .. note:: The merging process goes throught 3 steps:

           1. Compute external illumination vector: This vector
              records the external illumination difference between
              both cameras (e.g. if one camera get some diffused light
              from the sky while the other is well isolated). This
              vector is used to correct interferograms.
        
           2. Compute transmission vector: the transmission vector is
              computed from star photometry (2D gaussian or moffat
              fitting. See
              :py:meth:`orb.astrometry.Astrometry.fit_stars_in_cube`) of
              both frames from camera 1 and camera 2 (frames must
              therefore be aligned).

           3. Cube merging using for each frame (nth) of the cube the
              formula:
              
              .. math::

                 Frame_{n,M} = \\frac{Frame_{n,1}
                 -Frame_{n,2}}{transmission vector[n]}
        """

        def _get_stray_light_coeff(frameA, frameB, transmission_factor,
                                   modulation_ratio, ext_level):
            """Return the stray light coefficient. This light comes
            from reflections over clouds, the sun or the moon.
            
            :param frameA: Frame of the camera 1
            
            :param frameB: Frame of the camera 2
            
            :param transmission_factor: Correction factor for the sky
              variation of transmission

            :param modulation_ratio: The ratio of modulation between
              the two cameras. It depends on the gain and the quantum
              efficiency of the CCD.

            :param ext_level: Level of stray light (external
              illumination) in the camera B (if level is negative,
              the stray light is thus in the camera A)
            """
            ## This must be done by adding frames instead of doing all this
            ## which has exactly the same effect
            if np.any(frameB) and np.any(frameA):
                result_frame = ((((frameB / modulation_ratio) + frameA)
                                 / transmission_factor) - ext_level)
                stray_light_coeff = orb.utils.robust_median(result_frame) / 2.
            
            else:
                stray_light_coeff = np.nan
                
            return stray_light_coeff
            
        def _create_merged_frame(frameA, frameB, transmission_factor,
                                 modulation_ratio, ext_level,
                                 add_frameB, frameA_mask,
                                 frameB_mask):
            """Create the merged frame given the frames of both cubes
            and the correction factor.

            :param frameA: Frame of the camera 1
            
            :param frameB: Frame of the camera 2
            
            :param transmission_factor: Correction factor for the sky
              variation of transmission

            :param modulation_ratio: The ratio of modulation between
              the two cameras. It depends on the gain and the quantum
              efficiency of the CCD.

            :param ext_level: Level of light coming from an external
              source in the camera B but not in the camera A (if level
              is negative, the stray light is thus in the camera A)
              
            :param add_frameB: If False the frame B is not added. The
              resulting frame is thus the frame A divided by the
              transmission factor (generally not recommanded)

            :param frameA_mask: Mask of the frame A.

            :param frameB_mask: Mask of the frame B.
            """
            
            # Correcting for the variation of sky transmission
            if add_frameB:
                result_frame = ((((frameB / modulation_ratio) - frameA)
                                 / transmission_factor) - ext_level)
                
                flux_frame = ((((frameB / modulation_ratio) + frameA)
                                 / transmission_factor) - ext_level)
            else: # frame B is not added
                if np.any(frameA):
                    cont_frame = ((frameB / modulation_ratio) + frameA
                                  - ext_level) / 2.
                    
                    result_frame = ((frameA - np.nanmean(cont_frame))
                                    / transmission_factor)
                else:
                    result_frame = frameA
                    cont_frame = frameA
                    
                flux_frame = cont_frame
                
                ## if np.any(frameA):
                ##     result_frame = ((frameA - stray_light_coeff)
                ##                     / transmission_factor) + ext_level
                ## else:
                ##     result_frame = frameA
                ## flux_frame = result_frame

            result_frame_mask = frameA_mask + frameB_mask
            result_frame[np.nonzero(frameA == 0.)] = 0.
            result_frame[np.nonzero(frameB == 0.)] = 0.
            flux_frame[np.nonzero(frameA == 0.)] = 0.
            flux_frame[np.nonzero(frameB == 0.)] = 0.
            flux_frame[np.nonzero(np.isnan(flux_frame))] = 0.
            flux_frame[np.nonzero(np.isinf(flux_frame))] = 0.
            
            return result_frame, result_frame_mask, flux_frame

        def _create_merged_stars_frame(dimx, dimy, photom_A, photom_B,
                                       star_list, transmission_factor,
                                       modulation_ratio, ext_level):
            """Create a star frame

            The star frame is a reconstructed interferogram frame with
            only one point for each star. Other pixels are set to zero.

            :param dimx: Dimension along x axis of the resulting frame
            
            :param dimy: Dimension along y axis of the resulting frame
            
            :param photom_A: Photometry of the stars in the cube A for
              the given frame.

            :param photom_B: Photometry of the stars in the cube B for
              the given frame.

            :param star_list: List of star positions
            
            :param transmission_factor: Correction factor for the sky
              variation of transmission

            :param modulation_ratio: The ratio of modulation between
              the two cameras. It depends on the gain and the quantum
              efficiency of the CCD.
              
            :param ext_level: Level of stray light (external
              illumination) in the camera B (if the level is negative,
              the stray light is thus in the camera A)
            """
            result_frame = np.zeros((dimx, dimy), dtype=float)
            
            for istar in range(star_list.shape[0]):
                if ((photom_B[istar] != 0.)
                    and (photom_A[istar] != 0)):
                    x_star, y_star = star_list[istar]
                    result_frame[int(x_star), int(y_star)] = (
                        (((photom_B[istar] / modulation_ratio)
                         - photom_A[istar])
                        / transmission_factor) - ext_level)
            
            return result_frame

        def get_sky_level_vector(cube):
            """Create a vector containing the sky level evaluated in
            each frame of a cube

            :param cube: Data cube
            """
            def get_sky_level(frame):
                if len(np.nonzero(frame)[0]) > 0:
                    return orb.astrometry.sky_background_level(
                        frame[np.nonzero(frame)])
                else:
                    return 0.
                
            BORDER_COEFF = 0.15
            
            xmin = int(cube.dimx * BORDER_COEFF)
            xmax = cube.dimx - xmin + 1
            ymin = int(cube.dimy * BORDER_COEFF)
            ymax = cube.dimy - ymin + 1
            
            median_vector = np.empty(cube.dimz, dtype=float)
            job_server, ncpus = cube._init_pp_server()
            
            progress = ProgressBar(cube.dimz)
            for ik in range(0, cube.dimz, ncpus):
                
                progress.update(ik, info="Creating sky level vector")
                if (ik + ncpus >= cube.dimz):
                    ncpus = cube.dimz - ik
                 
                jobs = [(ijob, job_server.submit(
                    get_sky_level, 
                    args=(cube.get_data_frame(ik+ijob)[xmin:xmax,ymin:ymax],),
                    modules=("import numpy as np",
                             'import orb.astrometry')))
                        for ijob in range(ncpus)]

                for ijob, job in jobs:
                    median_vector[ik+ijob] = job()
                
            progress.end()
            cube._close_pp_server(job_server)
            
            return median_vector

        SMOOTH_DEG = 0 # number of pixels used on each side to
                       # smooth the transmission vector

        SMOOTH_RATIO_EXT = 0.05 # Ratio of the number of pixels over
                                # the vector length used to smooth the
                                # external illumination vector

        EXT_ZPD_SIZE = 0.20 # Length ratio of the ZPD over the entire
                            # cube. This is used to correct the external
                            # illumination vector

        # Minimum number of stars to compute the transmission vector
        MIN_STAR_NUMBER = float(self._get_tuning_parameter(
            'MIN_STAR_NUMBER', 5))

        BAD_FRAME_COEFF = 0.5 # Minimum transmission coefficient for
                              # bad frames detection (taken relatively
                              # to the median transmission coefficient)

        SIGMA_CUT_COEFF = 2.0 # Number of sigmas of the sigmacut
                              # (better if < 3.)

        # Coefficient on the mean reduced chi square to reject bad
        # star fit
        RED_CHISQ_COEFF = float(self._get_tuning_parameter(
            'RED_CHISQ_COEFF', 1.5))

        # FIXED MODULATION RATIO
        FIXED_MODULATION_RATIO = self._get_tuning_parameter(
            'FIXED_MODULATION_RATIO', None)
        if FIXED_MODULATION_RATIO is not None:
            FIXED_MODULATION_RATIO = float(FIXED_MODULATION_RATIO)

        # Define fit parameters depending on the type of frame
        EXTENDED_EMISSION = bool(int(
            self._get_tuning_parameter('EXTENDED_EMISSION', 0)))

        # Avoid transmission correction (useful for testing purpose)
        NO_TRANSMISSION_CORRECTION = bool(int(
            self._get_tuning_parameter('NO_TRANSMISSION_CORRECTION', 0)))
        if NO_TRANSMISSION_CORRECTION:
            self._print_warning('No transmission correction')


        local_background = True
        
        if EXTENDED_EMISSION:
            fix_fwhm = True
            optimized_modulation_ratio = False
            # Length ratio of the ZPD over the entire cube to correct
            # the transmission vector
            TRANS_ZPD_SIZE = float(
                self._get_tuning_parameter('TRANS_ZPD_SIZE', 0.1))
            
            self._print_warning(
                'Region considered as an extended emission region')
        else:
            fix_fwhm = False
            optimized_modulation_ratio = True
            # Length ratio of the ZPD over the entire cube to correct
            # the transmission vector
            TRANS_ZPD_SIZE = float(
                self._get_tuning_parameter('TRANS_ZPD_SIZE', 0.01))
        
        if aperture_photometry:
            self._print_msg('Star flux evaluated by aperture photometry')
            photometry_type = 'aperture_flux'
        else:
            self._print_msg('Star flux evaluated from fit parameters')
            photometry_type = 'flux'

        # creating deep frames for cube A and B
        frameA = self.cube_A.get_mean_image()
        frameB = self.cube_B.get_mean_image()
        
        # fit stars on deep frames to get a better guess on position
        # and FWHM
        mean_params_A = Astrometry(
            frameA, fwhm_arc, fov, profile_name=profile_name,
            star_list_path=star_list_path, readout_noise=readout_noise_1,
            dark_current_level=dark_current_level_1,
            logfile_name=self._logfile_name,
            tuning_parameters=self._tuning_parameters,
            config_file_name=self.config_file_name).fit_stars_in_frame(
            0, precise_guess=True, local_background=local_background,
            fix_fwhm=fix_fwhm, fix_height=False)
        mean_params_B = Astrometry(
            frameB, fwhm_arc, fov, profile_name=profile_name,
            star_list_path=star_list_path, readout_noise=readout_noise_2,
            dark_current_level=dark_current_level_2,
            logfile_name=self._logfile_name,
            tuning_parameters=self._tuning_parameters,
            config_file_name=self.config_file_name).fit_stars_in_frame(
            0, precise_guess=True, local_background=local_background,
            fix_fwhm=fix_fwhm, fix_height=False)

        star_list_A = mean_params_A.get_star_list()
        star_list_B = mean_params_A.get_star_list()

        fwhm_arc_A = orb.utils.robust_mean(mean_params_A[:,'fwhm_arc'])
        fwhm_arc_B = orb.utils.robust_mean(mean_params_B[:,'fwhm_arc'])

        self._print_msg(
            'mean FWHM of the stars in camera 1: {} arc-seconds'.format(
                fwhm_arc_A))
        self._print_msg(
            'mean FWHM of the stars in camera 2: {} arc-seconds'.format(
                fwhm_arc_B))
        

        ## COMPUTING STARS PHOTOMETRY #############################
        self._print_msg("Computing stars photometry")
        astrom_A = Astrometry(self.cube_A, fwhm_arc_A, fov,
                              profile_name=profile_name,
                              moffat_beta=moffat_beta,
                              data_prefix=self._data_prefix + 'cam1.',
                              readout_noise=readout_noise_1,
                              dark_current_level=dark_current_level_1,
                              logfile_name=self._logfile_name,
                              tuning_parameters=self._tuning_parameters,
                              check_mask=True,
                              config_file_name=self.config_file_name)
        astrom_A.reset_star_list(star_list_A)

        astrom_B = Astrometry(self.cube_B, fwhm_arc_B, fov,
                              profile_name=profile_name,
                              moffat_beta=moffat_beta,
                              data_prefix=self._data_prefix + 'cam2.',
                              readout_noise=readout_noise_2,
                              dark_current_level=dark_current_level_2,
                              logfile_name=self._logfile_name,
                              tuning_parameters=self._tuning_parameters,
                              check_mask=True,
                              config_file_name=self.config_file_name)
        astrom_B.reset_star_list(star_list_B)

        # Fit stars and get stars photometry
        astrom_A.fit_stars_in_cube(local_background=local_background,
                                   fix_fwhm=fix_fwhm,
                                   fix_height=False,
                                   fix_aperture_size=True,
                                   multi_fit=True)
        astrom_B.fit_stars_in_cube(local_background=local_background,
                                   fix_fwhm=fix_fwhm,
                                   fix_height=False,
                                   fix_aperture_size=True,
                                   multi_fit=True)
        
        astrom_A.load_fit_results(astrom_A._get_fit_results_path())
        astrom_B.load_fit_results(astrom_B._get_fit_results_path())

        photom_A = astrom_A.fit_results[:,:,photometry_type]
        photom_B = astrom_B.fit_results[:,:,photometry_type]

        # Find ZPD ################################################
        bad_frames_vector = orb.utils.correct_bad_frames_vector(
            bad_frames_vector, self.cube_A.dimz)
        zmedian = self.cube_A.get_zmedian(nozero=True)
        zmedian[bad_frames_vector] = 0.
        zpd_index = orb.utils.find_zpd(zmedian,
                                       step_number=step_number)
        
        self._print_msg('ZPD index: %d'%zpd_index)


        ## MODULATION RATIO #######################################
        # Calculating the mean modulation ratio (to correct for
        # difference of camera gain and transmission of the optical
        # path)

        # Optimization routine
        def photom_diff(modulation_ratio, photom_A, photom_B, zpd_min, zpd_max):
            return orb.utils.robust_median((photom_A * modulation_ratio
                                            - photom_B)**2.)
        
        # use EXT_ZPD_SIZE to remove ZPD from MODULATION RATION calculation
        ext_zpd_min = zpd_index - int(EXT_ZPD_SIZE * step_number / 2.)
        if ext_zpd_min < 0: ext_zpd_min = 0
        ext_zpd_max = zpd_index + int(EXT_ZPD_SIZE * step_number / 2.) + 1
        if ext_zpd_max > self.cube_A.dimz:
            ext_zpd_max = self.cube_A.dimz - 1

        photom_A_nozpd = np.copy(photom_A)
        photom_A_nozpd[:,ext_zpd_min:ext_zpd_max] = np.nan
        photom_B_nozpd = np.copy(photom_B)
        photom_B_nozpd[:,ext_zpd_min:ext_zpd_max] = np.nan
        
        if optimized_modulation_ratio and FIXED_MODULATION_RATIO is None:
            modulation_ratio = optimize.fmin_powell(
                photom_diff, [1.0],
                args=(photom_A_nozpd, photom_B_nozpd, ext_zpd_min, ext_zpd_max),
                ftol=1e-3, xtol=1e-3, disp=False)


            flux_error = np.nanmean(
                photom_A * modulation_ratio - photom_B, axis=1)
            flux_sum = np.nanmean(
                photom_A * modulation_ratio + photom_B, axis=1)
         
            flux_error_ratio = orb.utils.robust_mean(
                np.abs(flux_error/flux_sum),
                weights=flux_sum/np.nansum(flux_sum))
  
            self._print_msg(
                "Optimized modulation ratio: %f (std: %f)"%(
                    modulation_ratio, modulation_ratio * flux_error_ratio))
        
        elif FIXED_MODULATION_RATIO is None:
            # If the optimization does not work we try a more robust
            # but sometimes less precise method
            modulation_ratios = list()
            for index in range(photom_A_nozpd.shape[1]):
                index_mod = list()
                for istar in range(photom_A_nozpd.shape[0]):
                    if (photom_A[istar,index] != 0.
                        and not np.isnan(photom_B_nozpd[istar,index])
                        and not np.isnan(photom_A_nozpd[istar,index])):
                        index_mod.append(photom_B_nozpd[istar,index]
                                         / photom_A_nozpd[istar,index])
                if len(index_mod) > 0:
                    modulation_ratios.append(orb.utils.robust_mean(
                        orb.utils.sigmacut(index_mod, sigma=SIGMA_CUT_COEFF)))

            modulation_ratio = orb.utils.robust_mean(
                orb.utils.sigmacut(modulation_ratios, sigma=SIGMA_CUT_COEFF))

            modulation_ratio_std = orb.utils.robust_std(
                orb.utils.sigmacut(modulation_ratios, sigma=SIGMA_CUT_COEFF))

            self._print_msg(
                "Modulation ratio: %f (std: %f)"%(
                    modulation_ratio, modulation_ratio_std))
        else:
            modulation_ratio = FIXED_MODULATION_RATIO
            self._print_msg(
                "Fixed modulation ratio: %f"%(
                    modulation_ratio))

        self.write_fits(
            self._get_modulation_ratio_path(), 
            np.array([modulation_ratio]),
            fits_header=self._get_modulation_ratio_header(),
            overwrite=self.overwrite)

        if self.indexer is not None:
            self.indexer['modulation_ratio'] = self._get_modulation_ratio_path()

        # PHOTOMETRY ON MERGED FRAMES #############################
        astrom_merged = Astrometry(self.cube_B, fwhm_arc_B, fov,
                                   profile_name=profile_name,
                                   moffat_beta=moffat_beta,
                                   data_prefix=self._data_prefix + 'merged.',
                                   readout_noise=readout_noise_2,
                                   dark_current_level=dark_current_level_2,
                                   logfile_name=self._logfile_name,
                                   tuning_parameters=self._tuning_parameters,
                                   check_mask=False,
                                   config_file_name=self.config_file_name)
        astrom_merged.reset_star_list(star_list_B)
        
        astrom_merged.fit_stars_in_cube(
            local_background=local_background,
            fix_aperture_size=True,
            add_cube=[self.cube_A, modulation_ratio],
            no_fit=True)
        astrom_merged.load_fit_results(astrom_merged._get_fit_results_path())
        photom_merged = astrom_merged.fit_results[:,:,photometry_type]
        photom_merged_err = astrom_merged.fit_results[
            :,:,photometry_type + '_err']

        ## TRANSMISSION VECTOR ####################################
        self._print_msg("Computing transmission vector")

        transmission_vector_list = list()
        red_chisq_list = list()
        trans_err_list = list()
        
        # normalization of the merged photometry vector
        for istar in range(astrom_A.star_list.shape[0]):
            if not np.all(np.isnan(photom_merged)):
                trans = np.copy(photom_merged[istar,:])
                trans_err = np.copy(photom_merged_err[istar,:])
                trans_mean = orb.utils.robust_mean(orb.utils.sigmacut(trans))
                trans /= trans_mean
                trans_err /= trans_mean
                transmission_vector_list.append(trans)
                red_chisq = orb.utils.robust_mean(
                    orb.utils.sigmacut(astrom_A.fit_results[
                        istar, :, 'reduced-chi-square']))
                
                trans_err_list.append(trans_err)
                red_chisq_list.append(red_chisq)

        # reject stars with a bad reduced-chi-square
        mean_red_chisq = orb.utils.robust_mean(
            orb.utils.sigmacut(red_chisq_list))
        temp_list_trans = list()
        temp_list_trans_err = list()
        for istar in range(len(transmission_vector_list)):
            if red_chisq_list[istar] < mean_red_chisq * RED_CHISQ_COEFF:
                temp_list_trans.append(transmission_vector_list[istar])
                temp_list_trans_err.append(trans_err_list[istar])
        transmission_vector_list = temp_list_trans
        transmission_vector_list_err = temp_list_trans_err

        if len(transmission_vector_list) <  MIN_STAR_NUMBER:
            self._print_error("Too much stars have been rejected. The transmission vector cannot be computed !")

        self._print_msg(
            "Transmission vector will be computed using %d stars"%len(
                transmission_vector_list))
        transmission_vector_list = np.array(transmission_vector_list)
        transmission_vector_list_err = np.array(transmission_vector_list_err)
        
        # Create transmission vector
        transmission_vector = np.empty((self.cube_A.dimz), dtype=float)
        transmission_vector_err = np.empty_like(transmission_vector)
        transmission_vector.fill(np.nan)
        transmission_vector_err.fill(np.nan)
        
        for ik in range(self.cube_A.dimz):
            trans_ik = transmission_vector_list[:,ik]
            trans_err_ik = transmission_vector_list_err[:,ik]
            
            if len(np.nonzero(trans_ik)[0]) > 0:
                if len(trans_ik) >= MIN_STAR_NUMBER:
                    trans_cut, trans_cut_index = orb.utils.sigmacut(
                        trans_ik, sigma=SIGMA_CUT_COEFF, return_index_list=True)
                    transmission_vector[ik] = orb.utils.robust_mean(
                        trans_cut)
                    trans_cut_err = trans_err_ik[trans_cut_index]
                    transmission_vector_err[ik] = np.sqrt(
                        orb.utils.robust_mean(trans_cut_err**2.))
        
        # Transmission is corrected for bad values
        transmission_vector = orb.utils.correct_vector(
            transmission_vector, bad_value=0., polyfit=True, deg=3)

        # correct vector for ZPD
        if TRANS_ZPD_SIZE > 0:
            trans_zpd_min = (zpd_index
                             - int((TRANS_ZPD_SIZE * step_number)/2.))
            trans_zpd_max = (zpd_index
                             + int((TRANS_ZPD_SIZE * step_number)/2.) + 1)

            if trans_zpd_min < 0: trans_zpd_min = 0
            if trans_zpd_max > self.cube_A.dimz:
                trans_zpd_max = self.cube_A.dimz - 1

            transmission_vector[trans_zpd_min:trans_zpd_max] = 0.
        
            transmission_vector = orb.utils.correct_vector(
                transmission_vector, bad_value=0., polyfit=True, deg=3)
            
        # Transmission vector smoothing
        if smooth_vector:
            if SMOOTH_DEG > 0:
                transmission_vector = orb.utils.smooth(transmission_vector,
                                                       deg=SMOOTH_DEG)

        # Normalization of the star transmission vector to 1.5% clip
        nz = np.nonzero(transmission_vector)
        max_trans = orb.cutils.part_value(transmission_vector[nz], 0.985)
        transmission_vector[nz] /= max_trans

        if NO_TRANSMISSION_CORRECTION:
            transmission_vector.fill(1.)
            transmission_vector_err.fill(0.)
        
        # Save transmission vector
        self.write_fits(
            self._get_transmission_vector_path(), 
            transmission_vector.reshape((transmission_vector.shape[0],1)),
            fits_header=self._get_transmission_vector_header(),
            overwrite=self.overwrite)
        if self.indexer is not None:
            self.indexer[
                'transmission_vector'] = self._get_transmission_vector_path()

        self.write_fits(
            self._get_transmission_vector_path(err=True), 
            transmission_vector_err.reshape(
                (transmission_vector_err.shape[0],1)),
            fits_header=self._get_transmission_vector_header(err=True),
            overwrite=self.overwrite)
        if self.indexer is not None:
            self.indexer['transmission_vector_err'] = (
                self._get_transmission_vector_path(err=True))
        
        # Create BAD FRAMES VECTOR from transmission vector
        bad_frames_vector = np.zeros((self.cube_A.dimz), dtype=int)
        bad_frames_vector[
            np.nonzero(transmission_vector <= BAD_FRAME_COEFF)] = 1
        if np.any(bad_frames_vector):
            self._print_msg("Detected bad frames : %s"%str(
                np.nonzero(bad_frames_vector)[0]))
        self.write_fits(
            self._get_bad_frames_vector_path(), 
            bad_frames_vector,
            fits_header=self._get_bad_frames_vector_header(),
            overwrite=self.overwrite)
        
        if self.indexer is not None:
            self.indexer[
                'bad_frames_vector'] = self._get_bad_frames_vector_path()

        ## EXTERNAL ILLUMINATION VECTOR ##########################
        # Computing the external illumination level (if some light
        # enters in one of the cameras).
        
        # WARNING : This vector will be correct if there's enough
        # 'sky' pixels.

        if compute_ext_light:
            self._print_msg("Computing external illumination vector")
            median_frame_vector_A = get_sky_level_vector(self.cube_A)
            median_frame_vector_B = get_sky_level_vector(self.cube_B)

            ext_level_vector = ((median_frame_vector_B / modulation_ratio)
                                - median_frame_vector_A)

            # correct vector for nan values and zeros
            ext_level_vector = orb.utils.correct_vector(
                ext_level_vector, bad_value=0., polyfit=True, deg=3)

            
            # correct vector for ZPD
            ext_level_vector[ext_zpd_min:ext_zpd_max] = 0.
            ext_level_vector = orb.utils.correct_vector(
                ext_level_vector, bad_value=0., polyfit=True, deg=3)
            
            # vector smoothing
            if SMOOTH_RATIO_EXT > 0.:
                ext_level_vector = orb.utils.smooth(
                    ext_level_vector, 
                    deg=int(ext_level_vector.shape[0] * SMOOTH_RATIO_EXT))

        else:
            self._print_warning(
                "External illumination vector computation skipped")
            ext_level_vector = np.zeros(self.cube_A.dimz, dtype=float)
     
        # Save external illumination vector
        self.write_fits(
            self._get_ext_illumination_vector_path(), 
            ext_level_vector.reshape((ext_level_vector.shape[0],1)),
            fits_header=self._get_ext_illumination_vector_header(),
            overwrite=self.overwrite)
        if self.indexer is not None:
            self.indexer['ext_illumination_vector'] = (
                self._get_ext_illumination_vector_path())

        ## STRAY LIGHT VECTOR #####################################
        # This vector is used to compute stray light in both
        # detectors.

        ## if not add_frameB:
        ##     self._print_msg("Computing stray light vector")
            
        ##     # Init of the multiprocessing server
        ##     job_server, ncpus = self._init_pp_server()
        ##     framesA = np.empty(
        ##         (self.cube_A.dimx, self.cube_A.dimy, ncpus), dtype=float)
        ##     framesB = np.empty(
        ##         (self.cube_A.dimx, self.cube_A.dimy, ncpus), dtype=float)
        ##     ncpus_max = ncpus

        ##     stray_light_vector = np.empty(self.cube_A.dimz, dtype=float)
        ##     progress = ProgressBar(self.cube_A.dimz)
        ##     for ik in range(0, self.cube_A.dimz, ncpus):
        ##         # no more jobs than frames to compute
        ##         if (ik + ncpus >= self.cube_A.dimz):
        ##             ncpus = self.cube_A.dimz - ik

        ##         for ijob in range(ncpus):
        ##             framesA[:,:,ijob] = self.cube_A.get_data_frame(ik + ijob)
        ##             framesB[:,:,ijob] = self.cube_B.get_data_frame(ik + ijob)

        ##         jobs = [(ijob, job_server.submit(
        ##             _get_stray_light_coeff, 
        ##             args=(framesA[:,:,ijob],
        ##                   framesB[:,:,ijob], 
        ##                   transmission_vector[ik + ijob],
        ##                   modulation_ratio,
        ##                   ext_level_vector[ik + ijob]),
        ##             modules=("numpy as np", 'import orb.utils')))    
        ##             for ijob in range(ncpus)]

        ##         for ijob, job in jobs:
        ##             stray_light_vector[ik+ijob] = job()

        ##         progress.update(ik, info="frame: %d"%ik)
        ##     self._close_pp_server(job_server)
        ##     progress.end()

        ##     # correct vector for nan values and zeros
        ##     stray_light_vector = orb.utils.correct_vector(
        ##         stray_light_vector, bad_value=0., polyfit=True, deg=3)

        ##     # remove pedestal
        ##     stray_light_vector -= orb.cutils.part_value(
        ##         stray_light_vector[np.nonzero(~np.isnan(
        ##             stray_light_vector))], 0.015)

        ##     # Save stray light vector
        ##     self.write_fits(
        ##         self._get_stray_light_vector_path(), 
        ##         np.reshape(stray_light_vector, (stray_light_vector.shape[0],1)),
        ##         fits_header=self._get_stray_light_vector_header(),
        ##         overwrite=self.overwrite)

        ##     if self.indexer is not None:
        ##         self.indexer['stray_light_vector'] = (
        ##             self._get_stray_light_vector_path())
        
        ## else:
        ##     # stray light vector will be computed from frame merging
        ##     stray_light_vector = np.empty_like(transmission_vector)
        ##     stray_light_vector.fill(np.nan)
        

        ## MERGE FRAMES ###########################################
        self._print_msg("Merging cubes")
        
        # Init of the multiprocessing server
        job_server, ncpus = self._init_pp_server()


        flux_frame = np.zeros((self.cube_A.dimx, self.cube_A.dimy),
                              dtype=float)
        flux_frame_nb = 0
        flux_vector = np.zeros(self.cube_A.dimz, dtype=float)
        result_frames = np.empty((self.cube_A.dimx, self.cube_A.dimy, ncpus),
                                 dtype=float)
        result_mask_frames = np.empty((self.cube_A.dimx, self.cube_A.dimy,
                                       ncpus), dtype=float)
        framesA_mask = np.empty((self.cube_A.dimx, self.cube_A.dimy,
                                 ncpus), dtype=float)
        framesB_mask = np.empty((self.cube_A.dimx, self.cube_A.dimy,
                                 ncpus), dtype=float)
        
        if create_stars_cube:
            image_list_file_path = (
                self._get_stars_interfero_frame_list_path())
        else:
            image_list_file_path = (
                self._get_merged_interfero_frame_list_path())
            
        image_list_file = self.open_file(image_list_file_path)
        
        ncpus_max = ncpus
        progress = ProgressBar(int(self.cube_A.dimz/ncpus_max))
        
        for ik in range(0, self.cube_A.dimz, ncpus):
            # no more jobs than frames to compute
            if (ik + ncpus >= self.cube_A.dimz):
                ncpus = self.cube_A.dimz - ik

            if (self.cube_A._mask_exists
                and self.cube_A._mask_exists):
                for ijob in range(ncpus):
                    framesA_mask[:,:,ijob] = self.cube_A.get_data_frame(
                        ik + ijob, mask=True)
                    framesB_mask[:,:,ijob] = self.cube_B.get_data_frame(
                        ik + ijob, mask=True)
            else:
                framesA_mask.fill(0.)
                framesB_mask.fill(0.)
            
            # compute merged frames
            if create_stars_cube:
                jobs = [(ijob, job_server.submit(
                    _create_merged_stars_frame, 
                    args=(self.cube_A.dimx, self.cube_A.dimy,
                          photom_A[:, ik + ijob],
                          photom_B[:, ik + ijob],
                          astrom_A.star_list, 
                          transmission_vector[ik + ijob],
                          modulation_ratio,
                          ext_level_vector[ik + ijob]),
                    modules=("numpy as np",)))
                        for ijob in range(ncpus)]
            else:
                jobs = [(ijob, job_server.submit(
                    _create_merged_frame, 
                    args=(self.cube_A.get_data_frame(ik + ijob),
                          self.cube_B.get_data_frame(ik + ijob), 
                          transmission_vector[ik + ijob],
                          modulation_ratio,
                          ext_level_vector[ik + ijob],
                          add_frameB,
                          framesA_mask[:,:,ijob],
                          framesB_mask[:,:,ijob]),
                    modules=("numpy as np",)))
                        for ijob in range(ncpus)]
                
            for ijob, job in jobs:
                if create_stars_cube:
                    result_frames[:,:,ijob] = job()
                else:
                    (result_frames[:,:,ijob],
                     result_mask_frames[:,:,ijob],
                     flux_frame_temp) = job()
                    
                    if np.any(flux_frame_temp != 0.):
                        flux_frame += flux_frame_temp
                        flux_frame_nb += 1
                        flux_vector[ik + ijob] = orb.utils.robust_median(
                            flux_frame_temp)
                    else:
                        flux_vector[ik + ijob] = np.nan
             
            for ijob in range(ncpus):
                if create_stars_cube:
                    merged_frame_path = self._get_stars_interfero_frame_path(
                        ik + ijob)
                    fits_header = self._get_stars_interfero_frame_header()
                    self.write_fits(merged_frame_path, result_frames[:,:,ijob], 
                                    silent=True, 
                                    fits_header=fits_header,
                                    overwrite=self.overwrite)
                else:
                    merged_frame_path = self._get_merged_interfero_frame_path(
                        ik + ijob)
                    fits_header = self._get_merged_interfero_frame_header()
                    self.write_fits(merged_frame_path, result_frames[:,:,ijob], 
                                    silent=True, 
                                    fits_header=fits_header,
                                    overwrite=self.overwrite,
                                    mask=result_mask_frames[:,:,ijob],
                                    record_stats=True)
                image_list_file.write(merged_frame_path + "\n")
                image_list_file.flush()
                

            progress.update(int(ik/ncpus_max), info="frame : " + str(ik))
        self._close_pp_server(job_server)
        progress.end()
        image_list_file.close
        flux_frame /= flux_frame_nb

        if self.indexer is not None:
            if create_stars_cube:
                self.indexer['stars_interfero_frame_list'] = (
                    image_list_file_path)
            else:
                self.indexer['merged_interfero_frame_list'] = (
                    image_list_file_path)
        

        # ENERGY MAP & DEEP FRAME
        # Before being added deep frames of cam1 and cam2 must be
        # scaled to keep the same amount of photons/ADU from one
        # reduction to another. It is here scaled relatively to frameB
        # because on SpIOMM cam2 has kept the same gain and cam1 has
        # not.

        if add_frameB:
            # remove pedestal of flux vector, 1.5% clip
            stray_light_vector = flux_vector - orb.cutils.part_value(
                flux_vector[np.nonzero(~np.isnan(flux_vector))], 0.015)
       
            # Save stray light vector
            self.write_fits(
                self._get_stray_light_vector_path(), 
                stray_light_vector,
                fits_header=self._get_stray_light_vector_header(),
                overwrite=self.overwrite)
        
            if self.indexer is not None:
                self.indexer['stray_light_vector'] = (
                    self._get_stray_light_vector_path())
                
            self._print_msg('Mean flux of stray light: {} ADU'.format(
                np.nanmean(stray_light_vector)))
        else:
            stray_light_vector = np.zeros_like(flux_vector)
       
        merged_cube = Cube(image_list_file_path,
                           config_file_name=self.config_file_name)
        energy_map = merged_cube.get_interf_energy_map()
        deep_frame = (flux_frame - np.nanmean(stray_light_vector))
    
        self.write_fits(self._get_energy_map_path(), energy_map, 
                        fits_header=
                        self._get_energy_map_header(),
                        overwrite=self.overwrite)

        if self.indexer is not None:
            self.indexer['energy_map'] = self._get_energy_map_path()

        
        self.write_fits(self._get_deep_frame_path(), deep_frame, 
                        fits_header=self._get_deep_frame_header(),
                        overwrite=self.overwrite)

        if self.indexer is not None:
            self.indexer['deep_frame'] = self._get_deep_frame_path()


        # SAVE CALIBRATION STARS INTERFEROGRAMS
        self._print_msg("Saving corrected calibration stars interferograms")
        calib_stars_interf_list = list()
        for istar in range(astrom_A.star_list.shape[0]):
            calib_stars_interf_list.append(
                (((photom_B[istar,:]/modulation_ratio) - photom_A[istar,:])
                 / transmission_vector) - ext_level_vector)
        calibration_stars_path = self._get_calibration_stars_path()
        self.write_fits(calibration_stars_path,
                        np.array(calib_stars_interf_list),
                        fits_header=self._get_calibration_stars_header(),
                        overwrite=self.overwrite)

        if self.indexer is not None:
            self.indexer['calibration_stars'] = calibration_stars_path
            
        self._print_msg("Cubes merged")


    def extract_stars_spectrum(self, star_list_path, fwhm_arc, fov,
                               modulation_ratio_path,
                               transmission_vector_path,
                               ext_illumination_vector_path,
                               calibration_laser_map_path, step,
                               order, nm_laser, filter_file_path,
                               step_nb, window_type=None,
                               bad_frames_vector=None,
                               phase_map_0_path=None,
                               phase_coeffs=None, smoothing_deg=2,
                               aperture=True, profile_name='gaussian',
                               moffat_beta=3.5, n_phase=None,
                               auto_phase=False, filter_correct=True,
                               flat_spectrum_path=None, aper_coeff=3.,
                               saturation=None):
        
        """
        Extract the spectrum of the stars in a list of stars location
        list by photometry.

        This method may be used after
        :py:meth:`process.InterferogramMerger.merge` has created the
        nescessary data: modulation ratio, transmission vector and
        external illumination vector.
        
        :param star_list_path: Path to a list of star positions. A
          list of star positions can also be given as a list of tuples
          [(x0, y0), (x1, y1), ...].
        
        :param fwhm_arc: rough FWHM of the stars in arcsec
        
        :param fov: Field of view of the frame in arcminutes (given
          along x axis.

        :param modulation_ratio_path: Modulation ratio path.

        :param transmission_vector_path: Variation of the sky
          transmission. Must have the same size as the interferograms
          of the cube.

        :param ext_illumination_vector_path: Level of external
          illumination.  This is a small correction for the difference
          of incoming light between both cameras. Must have the same
          size as the interferograms of the cube.
    
        :param calibration_laser_map_path: Path to the calibration
          laser map.
          
        :param order: Folding order
          
        :param step: Step size in nm

        :param filter_file_path: Path to the filter file. If given the
          filter edges can be used to give a weight to the phase
          points. See :meth:`process.Spectrum.correct_filter` for more
          information about the filter file.

        :param step_nb: Full number of steps in the interferogram. Can
          be greater than the real number of steps if the cube has
          been stopped before the end. Missing steps will be replaced
          by zeros.
          
        :param window_type: (Optional) Apodization window to be used
          (Default None, no apodization)

        :param bad_frames_vector: (Optional) Mask-like vector
          containing ones for bad frames. Bad frames are replaced by
          zeros using a special function that smoothes transition
          between good parts and zeros (default None).

        :param phase_map_0_path: (Optional) This map contains the 0th
          order coefficient of the phase. It must have the same
          dimensions as the frames of the interferogram cube (default
          None).

        :param phase_coeffs: (Optional) Phase coefficiens other than
          the 0th order coefficient which is given by the phase
          map_0. The phase coefficients are defined for a fixed number
          of phase points and a given zpd shift. To avoid errors use
          the same number of phase points for the spectrum computation
          and for the phase computation. Try also to keep track of the
          shift use to compute the phase cube (default None).
          
        :param aperture: (Optional) If True, flux of stars is computed
          by aperture photometry. Else, The flux is evaluated given
          the fit parameters (default True).

        :param profile_name: (Optional) PSF profile to use to fit
          stars. Can be 'gaussian' or 'moffat' (default
          'gaussian'). See:
          :py:meth:`orb.astrometry.Astrometry.fit_stars_in_frame`.
          
        :param moffat_beta: (Optional) Beta parameter to use for
          moffat PSF (default 3.5).

        :param n_phase: (Optional) Number of points around ZPD to use
          for phase correction. If 0, no phase correction will be done
          and the resulting spectrum will be the absolute value of the
          complex spectrum. If None, the number of points is set to 50
          percent of the interferogram length (default None).

        :param auto_phase: (Optional) If True, phase is computed for
          each star independantly. Useful for high SNR stars when no
          reliable external phase can be provided (e.g. Standard
          stars). Note that if auto_phase is set to True, phase will
          be corrected even if n_phase is set to 0. (default False).

        :param filter_correct: (Optional) If True returned spectra
          are corrected for filter. Points out of the filter band
          are set to NaN (default True).

        :param flat_spectrum_path: (Optional) Path to a list of flat
          spectrum frames. This is used to further correct the
          resulting stars spectrum for fringing effects (default None).

        :param aper_coeff: (Optional) Aperture coefficient. The
          aperture radius is Rap = aper_coeff * FWHM. Better when
          between 1.5 to reduce the variation of the collected photons
          with varying FWHM and 3. to account for the flux in the
          wings (default 3., better for star with a high SNR).

        :param saturation: (Optional) If not None, allpixels above the
          saturation level are removed from the fit (default None).
        """
        PHASE_LEN_COEFF = 0.5 # Ratio of the number of points used to
                              # define phase over the total number of
                              # points of the interferograms

        RECOMPUTE_TRANSMISSION_VECTOR = bool(int(
            self._get_tuning_parameter('RECOMPUTE_TRANSMISSION_VECTOR', 0)))
        SMOOTH_DEG = int(
            self._get_tuning_parameter('SMOOTH_DEG', 0))
        POLYFIT_DEG = int(
            self._get_tuning_parameter('POLYFIT_DEG', 0))
        

        # Loading flat spectrum cube
        if flat_spectrum_path is not None:
            flat_cube = Cube(flat_spectrum_path,
                             config_file_name=self.config_file_name)
        else:
            flat_cube = None

        if isinstance(star_list_path, str):
            star_list = orb.astrometry.load_star_list(star_list_path)
        else:
            star_list = star_list_path
            
        # creating deep frames for cube A and B
        frameA = self.cube_A.get_mean_image()
        frameB = self.cube_B.get_mean_image()
        
        # fit stars on deep frames to get a better guess on position
        # and FWHM
        mean_astrom_A = Astrometry(
            frameA, fwhm_arc, fov, profile_name=profile_name,
            logfile_name=self._logfile_name,
            tuning_parameters=self._tuning_parameters,
            config_file_name=self.config_file_name)
        mean_astrom_A.reset_star_list(star_list)
        mean_params_A = mean_astrom_A.fit_stars_in_frame(
            0, precise_guess=True, local_background=True,
            fix_fwhm=False, fix_height=False, multi_fit=True)
        
        mean_astrom_B = Astrometry(
            frameB, fwhm_arc, fov, profile_name=profile_name,
            logfile_name=self._logfile_name,
            tuning_parameters=self._tuning_parameters,
            config_file_name=self.config_file_name)
        mean_astrom_B.reset_star_list(star_list)
        mean_params_B = mean_astrom_B.fit_stars_in_frame(
            0, precise_guess=True, local_background=True,
            fix_fwhm=False, fix_height=False, multi_fit=True)

        star_list_A = mean_params_A.get_star_list()
        star_list_B = mean_params_A.get_star_list()

        fwhm_arc_A = orb.utils.robust_mean(mean_params_A[:,'fwhm_arc'])
        fwhm_arc_B = orb.utils.robust_mean(mean_params_B[:,'fwhm_arc'])

        ## COMPUTING STARS INTERFEROGRAM
        self._print_msg("Computing stars photometry")
        
        if aperture:
            self._print_msg('Star flux evaluated by aperture photometry')
            photometry_type = 'aperture_flux'
        else:
            self._print_msg('Star flux evaluated by profile fitting')
            photometry_type = 'flux'
        
        astrom_A = Astrometry(self.cube_A, fwhm_arc_A, fov,
                              profile_name=profile_name,
                              moffat_beta=moffat_beta,
                              data_prefix=self._data_prefix + 'cam1.',
                              logfile_name=self._logfile_name,
                              tuning_parameters=self._tuning_parameters,
                              config_file_name=self.config_file_name)
        astrom_A.reset_star_list(star_list)

        astrom_B = Astrometry(self.cube_B, fwhm_arc_B, fov,
                              profile_name=profile_name,
                              moffat_beta=moffat_beta,
                              data_prefix=self._data_prefix + 'cam2.',
                              logfile_name=self._logfile_name,
                              tuning_parameters=self._tuning_parameters,
                              config_file_name=self.config_file_name)
        astrom_B.reset_star_list(star_list)

        # Fit stars and get stars photometry
        astrom_A.fit_stars_in_cube(local_background=True,
                                   fix_aperture_size=True,
                                   precise_guess=True,
                                   aper_coeff=aper_coeff,
                                   multi_fit=True,
                                   saturation=saturation)
        astrom_B.fit_stars_in_cube(local_background=True,
                                   fix_aperture_size=True,
                                   precise_guess=True,
                                   aper_coeff=aper_coeff,
                                   multi_fit=True,
                                   saturation=saturation)
        
        astrom_A.load_fit_results(astrom_A._get_fit_results_path())
        astrom_B.load_fit_results(astrom_B._get_fit_results_path())

        photom_A = astrom_A.fit_results[:,:,photometry_type]
        photom_B = astrom_B.fit_results[:,:,photometry_type]

        if astrom_A.star_nb == 1:
            photom_A = photom_A[np.newaxis, :]
            photom_B = photom_B[np.newaxis, :]
        
        modulation_ratio = np.squeeze(
            self.read_fits(modulation_ratio_path))
        transmission_vector = np.squeeze(
            self.read_fits(transmission_vector_path))
        ext_illumination_vector = np.squeeze(
            self.read_fits(ext_illumination_vector_path))

        star_interf_list = list()
        star_flux_list = list()


        # compute modulation ratio
        modulation_ratio_list = list()
        for istar in range(astrom_A.star_list.shape[0]):
            modulation_ratio = (orb.utils.robust_median(photom_B[istar,:]
                                                        / photom_A[istar,:]))
            modulation_ratio_list.append(modulation_ratio)
            
        
            self._print_msg('[Star %d] recomputed modulation ratio: %f'%(
                istar, modulation_ratio))
            
            if RECOMPUTE_TRANSMISSION_VECTOR:
                transmission_vector = ((photom_B[istar,:]/modulation_ratio)
                                       + photom_A[istar,:])
                if SMOOTH_DEG > 0:
                    transmission_vector = orb.utils.smooth(transmission_vector,
                                                           deg=SMOOTH_DEG)
                
                if POLYFIT_DEG > 0:
                    transmission_vector = orb.utils.polyfit1d(
                        transmission_vector, POLYFIT_DEG)
                
                    
                transmission_vector /= orb.cutils.part_value(
                    transmission_vector.flatten(), 0.99)



            # compute equivalent surface to substract ext_illumination
            # and stray light correctly from the integrated flux
            surf_eq = (4. * math.pi *  orb.utils.robust_median(
                (astrom_A.fit_results[:,:,'fwhm']
                 / orb.constants.FWHM_COEFF)**2.))
            
            star_flux_list.append(
                (((photom_B[istar,:]/modulation_ratio) + photom_A[istar,:])
                 / transmission_vector)
                - ext_illumination_vector * surf_eq)
                #- stray_light_vector  * surf_eq)

        # PHOTOMETRY ON MERGED FRAMES #############################
        astrom_merged = Astrometry(self.cube_B, fwhm_arc_B, fov,
                                   profile_name=profile_name,
                                   moffat_beta=moffat_beta,
                                   data_prefix=self._data_prefix + 'merged.',
                                   logfile_name=self._logfile_name,
                                   tuning_parameters=self._tuning_parameters,
                                   check_mask=False,
                                   config_file_name=self.config_file_name)
        astrom_merged.reset_star_list(star_list_B)

        modulation_ratio = orb.utils.robust_mean(
            orb.utils.sigmacut(modulation_ratio_list))
        
        astrom_merged.fit_stars_in_cube(
            local_background=True,
            fix_aperture_size=True,
            add_cube=[self.cube_A, -modulation_ratio],
            no_fit=True,
            aper_coeff=aper_coeff)
        
        astrom_merged.load_fit_results(astrom_merged._get_fit_results_path())
        photom_merged = astrom_merged.fit_results[:,:,'aperture_flux']
        photom_merged_err = astrom_merged.fit_results[
            :, :, 'aperture_flux_err']

        star_interf_list = list()
        for istar in range(len(star_list)):
            
            # compute equivalent surface to substract ext_illumination
            # and stray light correctly from the integrated flux
            surf_eq = (4. * math.pi *  orb.utils.robust_median(
                (astrom_A.fit_results[:,:,'fwhm']
                 / orb.constants.FWHM_COEFF)**2.))

            # compute interferograms
            if len(star_list) > 1:
                iphotom_merged = photom_merged[istar,:]
            else:
                iphotom_merged = np.squeeze(photom_merged)
                
            star_interf_list.append([
                (iphotom_merged
                 / transmission_vector) - ext_illumination_vector * surf_eq,
                star_list[istar]])

        ## COMPUTING STARS SPECTRUM
        
        # Loading calibration laser map
        self._print_msg("loading calibration laser map")
        calibration_laser_map = self.read_fits(calibration_laser_map_path)
        if (calibration_laser_map.shape[0] != self.cube_A.dimx):
            calibration_laser_map = orb.utils.interpolate_map(
                calibration_laser_map, self.cube_A.dimx, self.cube_A.dimy)
            
        ## Searching ZPD shift 
        zpd_shift = orb.utils.find_zpd(self.cube_A.get_zmedian(nozero=True),
                                       return_zpd_shift=True,
                                       step_number=step_nb)
        
        ## Loading phase map and phase coefficients
        if (phase_map_0_path is not None and phase_coeffs is not None
            and n_phase != 0):
            phase_map_0 = self.read_fits(phase_map_0_path)
        else:
            phase_map_0 = np.zeros((self.cube_A.dimx,
                                    self.cube_A.dimy), dtype=float)
            phase_coeffs = None

        if auto_phase:
            self._print_warning('Auto-phase: phase will be computed for each star independantly (No use of external phase)')
            
        ## Spectrum computation

        # Print some information about the spectrum transformation
        
        self._print_msg("Apodization function: %s"%window_type)
        self._print_msg("Zeros smoothing degree: %d"%smoothing_deg)
        self._print_msg("Folding order: %f"%order)
        self._print_msg("Step size: %f"%step)
        self._print_msg("Bad frames: %s"%str(np.nonzero(bad_frames_vector)[0]))

        # get filter min and filter max edges for weights definition
        # in case no external phase is provided
       
        (filter_nm, filter_trans,
         filter_min, filter_max) = orb.utils.read_filter_file(filter_file_path)

        # load filter function for filter correction
        if filter_correct:
            (filter_function,
             filter_min_pix, filter_max_pix) = orb.utils.get_filter_function(
                filter_file_path, step, order, step_nb)

        star_spectrum_list = list()
        for istar in range(len(star_interf_list)):
            star_interf = star_interf_list[istar][0]
            star_x, star_y = star_interf_list[istar][1]

            # Add missing steps
            if np.size(star_interf) < step_nb:
                temp_interf = np.zeros(step_nb)
                temp_interf[:np.size(star_interf)] = star_interf
                star_interf = temp_interf

            # define external phase
            if (phase_map_0 is not None and phase_coeffs is not None
                and not auto_phase):
                coeffs_list = list()
                coeffs_list.append(phase_map_0[int(star_x), int(star_y)])
                coeffs_list += phase_coeffs
                ext_phase = np.polynomial.polynomial.polyval(
                    np.arange(step_nb), coeffs_list)
                weights = None
    
            elif (n_phase != 0) or auto_phase:
                ext_phase = None
                # Weights definition if the phase has to be
                # defined for each star (no external phase
                # provided)
                if n_phase is None or n_phase == 0:
                    n_phase = int(PHASE_LEN_COEFF * step_nb)

                weights = np.zeros(n_phase)
                if ext_phase is None and n_phase != 0:
                    weights += 1e-20
                    weights_min_pix, weights_max_pix = (
                        orb.utils.get_filter_edges_pix(
                            None,
                            (calibration_laser_map[int(star_x), int(star_y)]
                             / nm_laser),
                            step, order, n_phase, filter_min=filter_min,
                            filter_max=filter_max))
                weights[weights_min_pix:weights_max_pix] = 1.
            elif n_phase == 0:
                ext_phase = None
                weights = None
            
            star_spectrum = orb.utils.transform_interferogram(
                star_interf, nm_laser,
                calibration_laser_map[int(star_x), int(star_y)],
                step, order, window_type, zpd_shift,
                bad_frames_vector=bad_frames_vector,
                n_phase=0,
                ext_phase=ext_phase,
                balanced=True,
                weights=weights,
                smoothing_deg=smoothing_deg)

            # check polarity
            if np.mean(star_spectrum) < 0.:
                star_spectrum = -star_spectrum

            # rescale to make sure that the same quantity of energy
            # correponds to a given number of counts
            scale_factor = (orb.utils.robust_mean(star_flux_list[istar])/
                            orb.utils.robust_mean(star_spectrum))
            
            star_spectrum *= scale_factor
            
            # filter correction
            if filter_correct:
                star_spectrum /= filter_function
                star_spectrum[:filter_min_pix] = np.nan
                star_spectrum[filter_max_pix:] = np.nan
               
            # flat correction
            if flat_cube is not None:
                # extracting flat spectrum in the region of the star
                (x_min, x_max,
                 y_min, y_max) = orb.utils.get_box_coords(star_x, star_y,
                                                          astrom_A.box_size,
                                                          0, astrom_A.dimx,
                                                          0, astrom_A.dimy)
                x_min = int(x_min)
                x_max = int(x_max)
                y_min = int(y_min)
                y_max = int(y_max)
                star_fwhm = orb.utils.robust_mean(
                    orb.utils.sigmacut(astrom_A.fit_results[istar,:,'fwhm']))
                star_profile = astrom_A.profile(
                    astrom_A.fit_results[istar,0]).array2d(astrom_A.box_size,
                                                           astrom_A.box_size)
                flat_spectrum = list()
                for iframe in range(flat_cube.dimz):
                    star_box = flat_cube[x_min:x_max, y_min:y_max, iframe]
                    star_box *= star_profile
                    flat_spectrum.append(orb.astrometry.aperture_photometry(
                        star_box, star_fwhm, background_guess=0.)[0])
                flat_spectrum = np.squeeze(np.array(flat_spectrum))

                # flat spectrum is made 'flat' to remove its 'black
                # body' shape
                weights = np.zeros(flat_spectrum.shape[0])
                weights[np.nonzero(flat_spectrum)] = 1.
                
                flat_spectrum /= orb.utils.polyfit1d(flat_spectrum, 1,
                                           w=weights)

                star_spectrum[:filter_min_pix] = np.nan
                star_spectrum[filter_max_pix:] = np.nan
                flat_spectrum[:filter_min_pix] = np.nan
                flat_spectrum[filter_max_pix:] = np.nan
                star_spectrum /= flat_spectrum

            self._print_msg('Star %d mean flux: %f ADU'%(
                    istar, orb.utils.robust_mean(star_spectrum)))
            self._print_msg('Star %d mean modulation efficiency: %f %%'%(
                    istar, 1./scale_factor*100.))
            
            star_spectrum_list.append(star_spectrum)
        star_spectrum_list = np.array(star_spectrum_list)
                
        # write spectra
        self.write_fits(self._get_extracted_star_spectra_path(),
                        star_spectrum_list,
                        fits_header=self._get_extracted_star_spectra_header(),
                        overwrite=self.overwrite)
        if self.indexer is not None:
            self.indexer['extracted_star_spectra'] = (
                self._get_extracted_star_spectra_path())
   
        return star_spectrum_list
        
##################################################
#### CLASS Spectrum ##############################
##################################################
class Spectrum(Cube):
    """
    ORBS spectrum processing class.

    This class is used to correct the spectrum computed by the
    Interferogram class. 
    
    :param spectrum_cube_path: Path to the spectrum cube
    """

    def _get_stars_coords_path(self):
        """Return path to the list of stars coordinates used to correct WCS"""
        return self._data_path_hdr + "stars_coords"

        
    def _get_calibrated_spectrum_list_path(self, stars_cube=False):
        """Return the default path to the calibrated spectrum list.

        :param stars_cube: (Optional) The spectrum computed
          contains only the spectrum of some stars. The default path
          name is changed (default False).
        """ 
        if stars_cube:
            return self._data_path_hdr + "calibrated_stars_spectrum.list"
        else:
            return self._data_path_hdr + "calibrated_spectrum.list"

    def _get_modulation_efficiency_map_path(self):
        """Return path to the modulation efficiency map."""
        return self._data_path_hdr + "modulation_efficiency_map.fits"

    def _get_modulation_efficiency_map_header(self):
        """Return the header of the modulation efficiency map."""
        
        header = self._get_basic_header('Modulation efficiency map')
       
        return (header
                + self._project_header
                + self._calibration_laser_header
                + self._get_basic_frame_header(self.dimx, self.dimy))

    def _get_calibrated_spectrum_frame_path(self, frame_index,
                                            stars_cube=False):
        """Return the default path to a calibrated spectral frame given its
        index.

        :param frame_index: Index of the frame
        :param stars_cube: (Optional) The spectrum computed
          contains only the spectrum of some stars. The default path
          name is changed (default False).
        """
        cube_type = "calibrated_spectrum"
        if stars_cube:
            dir_header = "STARS_"
            stars_header = "stars_"
        else:
            dir_header = ""
            stars_header = ""

        spectrum_dirname = os.path.dirname(self._data_path_hdr)
        spectrum_basename = os.path.basename(self._data_path_hdr)
        
        return (spectrum_dirname + os.sep + dir_header
                + "%s"%cube_type.upper() + os.sep
                + spectrum_basename + stars_header 
                + "%s%04d.fits"%(cube_type, frame_index))


    def _get_calibrated_spectrum_frame_header(self, frame_index, axis,
                                              apodization_function,
                                              stars_cube=False,
                                              wavenumber=False):
        
        """Return the header of the calibrated spectral frames.
        
        :param frame_index: Index of the frame.  
    
        :param axis: Spectrum axis (must be in wavelength or in
          wavenumber).
        
        :param stars_cube: (Optional) The spectrum computed contains
          only the spectrum of some stars. The default path name is
          changed (default False).

        :param wavenumber: (Optional) If True the axis is considered
          to be in wavenumber. If False the axis is considered to be
          in wavelength (default False).
        """
        if stars_cube: file_type = "Calibrated stars spectrum frame"
        else: file_type = "Calibrated spectrum frame"
            
        return (self._get_basic_header(file_type)
                + self._project_header
                + self._calibration_laser_header
                + self._get_basic_frame_header(self.dimx, self.dimy)
                + self._get_basic_spectrum_frame_header(frame_index, axis,
                                                        wavenumber=wavenumber)
                + self._get_fft_params_header(apodization_function))
    
    def _get_calibrated_spectrum_path(self, stars_cube=False):
        """Return the default path to the calibrated spectral cube.
        
        :param stars_cube: (Optional) The spectrum computed
          contains only the spectrum of some stars. The default path
          name is changed (default False).
        """
        if stars_cube:
            stars_header = "stars_"
        else:
            stars_header = ""
      
        return (self._data_path_hdr + stars_header
                + "calibrated_spectrum.fits")
    
    def _get_calibrated_spectrum_header(self, axis, apodization_function,
                                        stars_cube=False,
                                        wavenumber=False):
        """Return the header of the calibrated spectral cube.
        
        :param axis: Spectrum axis (must be in wavelength or in
          wavenumber).
        
        :param stars_cube: (Optional) The spectrum computed
          contains only the spectrum of some stars. The default path
          name is changed (default False).
          
        :param wavenumber: (Optional) If True the axis is considered
          to be in wavenumber. If False the axis is considered to be
          in wavelength (default False).
        """
        if stars_cube:
            header = self._get_basic_header('Calibrated stars spectrum cube')
        else:
            header = self._get_basic_header('Calibrated spectrum cube')
        return (header
                + self._project_header
                + self._calibration_laser_header
                + self._get_basic_frame_header(self.dimx, self.dimy)
                + self._get_basic_spectrum_cube_header(axis,
                                                       wavenumber=wavenumber)
                + self._get_fft_params_header(apodization_function))


    def _update_hdr_wcs(self, hdr, wcs_hdr):
        """Update a header with WCS parameters

        :param hdr: A pyfits.Header() instance

        :param wcs_header: A pyfits.Header() instance containing the
          new WCS parameters.
        """
        hdr.extend(wcs_hdr, strip=True,
                   update=True, end=True)

        # delete unused keywords created by pywcs
        if 'RESTFRQ' in hdr:
            del hdr['RESTFRQ']
        if 'RESTWAV' in hdr:
            del hdr['RESTWAV']
        if 'LONPOLE' in hdr:
            del hdr['LONPOLE']
        if 'LATPOLE' in hdr:
            del hdr['LATPOLE']
        return hdr
        

    def calibrate(self, filter_file_path, step, order,
                  calibration_laser_map_path, nm_laser,
                  stars_cube=False, correct_wcs=None,
                  flux_calibration_vector=None,
                  deep_frame_path=None, mean_flux=True, wavenumber=False,
                  standard_header=None, spectral_calibration=True):
        
        """Calibrate spectrum cube: correct for filter transmission
        function, correct WCS parameters and flux calibration.

        :param filter_file_path: The path to the file containing the
           filter transmission function.

        :param step: Step size of the interferogram in nm.
        
        :param order: Folding order of the interferogram.

        :param calibration_laser_map_path: Path to the calibration
          laser map.

        :param nm_laser: Calibration laser wavelength.

        :param spectral_calibration (Optional): If True, the ouput
          spectral cube will be calibrated in
          wavelength/wavenumber. Note that in this case the spectrum
          must be interpolated. Else no spectral calibration is done:
          the channel position of a given wavelength/wavenumber
          changes with its position in the field (default True).
          
        :param stars_cube: (Optional) True if the spectral cube is a
          star cube (default False).
          
        :param correct_wcs: (Optional) Must be a pywcs.WCS
          instance. If not None header of the corrected spectrum
          cube is updated with the new WCS.

        :param flux_calibration_vector: (Optional) Must be a vector
          calibrated in erg/cm^2/s/A as the one given by
          :py:meth:`process.Spectrum.get_flux_calibration_vector`. Each
          spectrum will be multiplied by this vector to be flux
          calibrated.
       
        :param deep_frame_path: (Optional) Path to the deep frame of
          the interferogram cube. Useful to get the mean modulation
          efficiency and rescale flux.
    
        :param mean_flux: (Optional) If True, the flux calibration
          vector gives only a mean flux for all the wavelength and
          does not correct for the filter. In this case the filter
          correction is done but the filter function is normalized
          beacuse the flux calibration already takes into account the
          mean flux loss due to the filter. If False, the flux
          calibration vector is considered to correct for everything
          included the filter and no filter correction is done
          (default True).

        :param wavenumber: (Optional) If True, the spectrum is
          considered to be in wavenumber. If False it is considered to
          be in wavelength (default False).    

        :param standard_header: (Optional) Header for the standard
          star used for flux calibration. This header part will be
          appended to the FITS header.

        .. note:: The filter file used must have two colums separated
          by a space character. The first column contains the
          wavelength axis in nm. The second column contains the
          transmission coefficients. Comments are preceded with a #.
          Filter edges can be specified using the keywords :
          FILTER_MIN and FILTER_MAX::

            ## ORBS filter file 
            # Author: Thomas Martin <thomas.martin.1@ulaval.ca>
            # Filter name : SpIOMM_R
            # Wavelength in nm | Transmission percentage
            # FILTER_MIN 648
            # FILTER_MAX 678
            1000 0.001201585284
            999.7999878 0.009733387269
            999.5999756 -0.0004460749624
            999.4000244 0.01378122438
            999.2000122 0.002538740868

        """
        
        def _correct_spectrum_column(spectrum_col, filter_function,
                                     min_index, max_index,
                                     flux_calibration_vector,
                                     scale_factor,
                                     calibration_laser_col, nm_laser,
                                     step, order, wavenumber,
                                     spectral_calibration):
            """
            
            """
            # rescaling:
            if scale_factor is not None:
                spectrum_col *= scale_factor

            
            if wavenumber:
                cm1_axis = orb.utils.create_cm1_axis(spectrum_col.shape[1],
                                                     step, order, corr=1.)
                filter_min_nm = cm1_axis[min_index]
                filter_max_nm = cm1_axis[max_index]
            else:
                nm_axis = orb.utils.create_nm_axis(spectrum_col.shape[1],
                                                   step, order)
                filter_min_nm = nm_axis[min_index]
                filter_max_nm = nm_axis[max_index]

            for icol in range(spectrum_col.shape[0]):

                corr = calibration_laser_col[icol]/nm_laser

                if wavenumber:
                    cm1_axis_corr = orb.utils.create_cm1_axis(
                        spectrum_col.shape[1], step, order, corr=corr)

                    # filter function and spectrum are projected
                    if spectral_calibration: # spectrum proj
                        [imin_index, imax_index] = [min_index, max_index]
                        ifilter = filter_function
                        spectrum_col[icol,:] = orb.utils.interpolate_axis(
                            spectrum_col[icol,:], cm1_axis, 1,
                            old_axis=cm1_axis_corr) 
                    else: # filter proj
                        [imin_index, imax_index] = orb.utils.cm12pix(
                            cm1_axis_corr, [filter_min_nm, filter_max_nm])
                        ifilter = orb.utils.interpolate_axis(
                            filter_function, cm1_axis_corr, 1,
                            old_axis=cm1_axis) 

                    imin_index = int(imin_index)
                    imax_index = int(imax_index)
                    spectrum_col[icol, imin_index:imax_index] /= (
                        ifilter[imin_index:imax_index])
                    spectrum_col[icol,:imin_index] = np.nan
                    spectrum_col[icol,imax_index:] = np.nan

                else:
                    nm_axis_corr = orb.utils.create_nm_axis(
                        spectrum_col.shape[1], step, order, corr=corr)
                    # filter function and spectrum are projected
                    if spectral_calibration: # spectrum proj
                        [imin_index, imax_index] = [min_index, max_index]
                        ifilter = filter_function
                        spectrum_col[icol,:] = orb.utils.interpolate_axis(
                            spectrum_col[icol,:], nm_axis, 1,
                            old_axis=nm_axis_corr) 
                    else: # filter proj
                        [imin_index, imax_index] = orb.utils.nm2pix(
                            nm_axis_corr, [filter_min_nm, filter_max_nm])
                        ifilter = orb.utils.interpolate_axis(
                            filter_function, nm_axis_corr, 1,
                            old_axis=nm_axis)

                    imin_index = int(imin_index)
                    imax_index = int(imax_index)
                    spectrum_col[icol, imin_index:imax_index] /= (
                        ifilter[imin_index:imax_index])
                    spectrum_col[icol,:imin_index] = np.nan
                    spectrum_col[icol,imax_index:] = np.nan

                    #####################################
                    ## ifilter = orb.utils.interpolate_axis(
                    ##     filter_function, nm_axis_ireg_corr, 1,
                    ##     old_axis=nm_axis)
                    ## spectrum_col[icol, :] = orb.utils.interpolate_axis(
                    ##     spectrum_col[icol, :], nm_axis_ireg, 5,
                    ##     old_axis=nm_axis)

                    ## [imin_index, imax_index] = orb.utils.nm2pix(
                    ##     nm_axis_ireg_corr, [filter_min_nm, filter_max_nm])

                    ## imin_index = int(imin_index)
                    ## imax_index = int(imax_index)
                    ## spectrum_col[icol, imin_index:imax_index] /= (
                    ##     ifilter[imin_index:imax_index])
                    ## spectrum_col[icol,:imin_index] = np.nan
                    ## spectrum_col[icol,imax_index:] = np.nan

                    ## # once the spectrum has been divided by the
                    ## # filter it is interpolated back to its
                    ## # original axis
                    ## spectrum_col[icol, :] = orb.utils.interpolate_axis(
                    ##     spectrum_col[icol, :], nm_axis, 5,
                    ##     old_axis=nm_axis_ireg)
                        

            # flux calibration
            if flux_calibration_vector is not None:
                spectrum_col *= flux_calibration_vector
            
            return spectrum_col

        
        def get_mean_scale_map(ref_scale_map, spectrum_scale_map):
            
            MEAN_SCALING_BORDER = 0.3
            
            x_min = int(self.dimx * MEAN_SCALING_BORDER)
            x_max = int(self.dimx * (1. - MEAN_SCALING_BORDER))
            y_min = int(self.dimy * MEAN_SCALING_BORDER)
            y_max = int(self.dimy * (1. - MEAN_SCALING_BORDER))
            spectrum_scale_map_box = spectrum_scale_map[x_min:x_max,
                                                        y_min:y_max]
            ref_scale_map_box = ref_scale_map[x_min:x_max, y_min:y_max]
            return (orb.utils.robust_mean(orb.utils.sigmacut(ref_scale_map_box
                                         / spectrum_scale_map_box)),
                    orb.utils.robust_std(orb.utils.sigmacut(ref_scale_map_box
                                        / spectrum_scale_map_box)))
        
                
        # Get FFT parameters
        hdu = self.read_fits(self.image_list[0],
                             return_hdu_only=True)
        if 'APODIZ' in hdu[0].header:
            apodization_function = hdu[0].header['APODIZ']
        else:
            apodization_function = 'None'

        # get calibration laser map
        calibration_laser_map = self.read_fits(calibration_laser_map_path)
        if (calibration_laser_map.shape[0] != self.dimx):
            calibration_laser_map = orb.utils.interpolate_map(
                calibration_laser_map,
                self.dimx, self.dimy)
            
        # Get filter parameters
        filter_function, filter_min, filter_max = orb.utils.get_filter_function(
            filter_file_path, step, order, self.dimz, wavenumber=wavenumber)

        if filter_min < 0: filter_min = 0
        if filter_max > self.dimz: filter_max = self.dimz
    
        if flux_calibration_vector is not None:
            if mean_flux:
                filter_function[filter_min:filter_max] /= orb.utils.robust_mean(
                    filter_function[filter_min:filter_max])
            else:
                filter_function.fill(1.)     
        
        self._print_msg("Calibrating spectra", color=True)
        self._print_msg("Filter correction")

        if spectral_calibration:
            self._print_msg("Spectral calibration")
        else:
            self._print_warning("No spectral calibration")
        
        if flux_calibration_vector is not None:
            self._print_msg("Flux calibration")
        else:
            self._print_warning("No flux calibration")
            
        if correct_wcs is not None:
            self._print_msg("WCS correction")
        else:
            self._print_warning("No WCS correction")

        if deep_frame_path is not None:
            
            deep_frame_interf = self.read_fits(deep_frame_path)
            deep_frame_spectrum = self.get_mean_image()
        
            self.write_fits(
                self._get_modulation_efficiency_map_path(),
                deep_frame_spectrum/deep_frame_interf,
                fits_header=self._get_modulation_efficiency_map_header(),
                overwrite=self.overwrite)
                            
            if self.indexer is not None:
                self.indexer['modulation_efficiency_map'] = (
                    self._get_modulation_efficiency_map_path())
            
            scale_factor, scale_factor_std = get_mean_scale_map(
                deep_frame_interf, deep_frame_spectrum)
            self._print_msg("Mean scale factor: %f, std: %f"%(
                scale_factor, scale_factor_std))
            self._print_msg("Mean modulation efficiency: %f %%"%(
                1./scale_factor * 100))
   
        else:
            self._print_warning(
                "No rescaling done: flux calibration might be bad")
            scale_factor = None

        # Init of the multiprocessing server    
        for iquad in range(0, self.QUAD_NB):
            (x_min, x_max, 
             y_min, y_max) = self.get_quadrant_dims(iquad)
            iquad_data = self.get_data(x_min, x_max, 
                                       y_min, y_max, 
                                       0, self.dimz)
            iquad_calibration_laser_map = calibration_laser_map[
                x_min:x_max, y_min:y_max]
            job_server, ncpus = self._init_pp_server()
            ncpus_max = int(ncpus)
            progress = ProgressBar(int((x_max-x_min)/ncpus_max))

            for ii in range(0, x_max-x_min, ncpus):
                progress.update(int(ii/ncpus_max), 
                                info="quad : %d, column : %d"%(iquad + 1, ii))
                
                # no more jobs than frames to compute
                if (ii + ncpus >= x_max-x_min):
                    ncpus = x_max - x_min - ii

                # correct spectrum columns
                jobs = [(ijob, job_server.submit(
                    _correct_spectrum_column, 
                    args=(
                        iquad_data[ii+ijob,:,:], 
                        filter_function,
                        filter_min, filter_max,
                        flux_calibration_vector,
                        scale_factor, 
                        iquad_calibration_laser_map[ii+ijob,:],
                        nm_laser, step, order, wavenumber,
                        spectral_calibration),
                    modules=("numpy as np", "import orb.utils"))) 
                        for ijob in range(ncpus)]

                for ijob, job in jobs:
                    # corrected data comes in place of original data
                    iquad_data[ii+ijob,:,:] = job()

            self._close_pp_server(job_server)
            progress.end()
            
            progress = ProgressBar(self.dimz)
            ## SAVE returned data by quadrants
            for iframe in range(self.dimz):
                progress.update(iframe, info='Saving data')
                frame_path = self._get_calibrated_spectrum_frame_path(
                    iframe, stars_cube=stars_cube)

                # save data in a *.IQUAD file
                self.write_fits(
                    frame_path+'.%d'%(iquad), iquad_data[:,:,iframe],
                    silent=True, overwrite=True)
            progress.end()

        # merge *.IQUAD files
        if wavenumber:
            axis = orb.utils.create_nm_axis(self.dimz, step, order)
        else:
            axis = orb.utils.create_cm1_axis(self.dimz, step, order)

        # update standard header
        if standard_header is not None:
            standard_header.append((
                'FLAMBDA',
                np.nanmean(flux_calibration_vector),
                'Mean flux/ADU [erg/cm^2/s/A/ADU]'))
                
        progress = ProgressBar(self.dimz)
        for iframe in range(self.dimz):
            progress.update(iframe, info='Merging quads')
            frame = np.empty((self.dimx, self.dimy), dtype=float)
            frame_path = self._get_calibrated_spectrum_frame_path(
                iframe, stars_cube=stars_cube)
            for iquad in range(0, self.QUAD_NB):
                x_min, x_max, y_min, y_max = self.get_quadrant_dims(iquad)
                frame[x_min:x_max, y_min:y_max] = self.read_fits(
                    frame_path+'.%d'%(iquad), delete_after=True)
                
            # Create header
            hdr = self._get_calibrated_spectrum_frame_header(
                iframe, axis,
                apodization_function, stars_cube=stars_cube,
                wavenumber=wavenumber)

            # Create WCS header
            new_hdr = pyfits.PrimaryHDU(frame.transpose()).header
            new_hdr.extend(hdr, strip=True, update=True, end=True)
            if correct_wcs is not None:
                hdr = self._update_hdr_wcs(new_hdr, correct_wcs.to_header())
            else:
                hdr = new_hdr

            hdr.set('PC1_1', after='CROTA2')
            hdr.set('PC1_2', after='PC1_1')
            hdr.set('PC2_1', after='PC1_2')
            hdr.set('PC2_2', after='PC2_1')
            hdr.set('WCSAXES', before='CTYPE1')
            
            # Create Standard header
            if standard_header is not None:
                hdr.extend(standard_header, strip=False, update=False, end=True)
                    
            # Create flux header
            flux_hdr = list()
            flux_hdr.append(('COMMENT','',''))
            flux_hdr.append(('COMMENT','Flux',''))
            flux_hdr.append(('COMMENT','----',''))
            flux_hdr.append(('COMMENT','',''))
            if flux_calibration_vector is not None:
                flux_hdr.append(('BUNIT','FLUX','Flux unit [erg/cm^2/s/A]'))
            else:
                flux_hdr.append(('BUNIT','UNCALIB','Uncalibrated Flux'))
                    
            hdr.extend(flux_hdr, strip=False, update=False, end=True)
                
            self.write_fits(
                frame_path, frame, silent=True,
                fits_header=hdr,
                overwrite=True)
        progress.end()

        # write list of calibrated frames
        file_list_path = self._get_calibrated_spectrum_list_path()
        file_list = self.open_file(file_list_path )
        for iframe in range(self.dimz):
            frame_path = self._get_calibrated_spectrum_frame_path(
                iframe, stars_cube=stars_cube)
            file_list.write("%s\n"%frame_path)
        file_list.close()
        if self.indexer is not None:
            self.indexer['calibrated_spectrum_list'] = file_list_path

    def get_flux_calibration_vector(self, std_spectrum_path, std_name,
                                    step, order, exp_time, filter_file_path,
                                    mean_vector=True):
        """
        Return a flux calibration vector in [erg/cm^2/s/A]/ADU on the range
        corresponding to the observation parameters of the spectrum to
        be calibrated.

        The spectrum to be calibrated can then be simply multiplied by
        the returned vector to be converted in [erg/cm^2/s/A]

        :param std_spectrum_path: Path to the standard spectrum

        :param std_name: Name of the standard

        :param step: Step size of the spectrum to calibrate

        :param order: Order of the spectrum to calibrate

        :param exp_time: Exposition time of the spectrum to calibrate

        :param filter_file_path: Path to the filter file. If given the
          filter edges can be used to give a weight to the phase
          points. See :meth:`process.Spectrum.correct_filter` for more
          information about the filter file.
          
        :paran mean_vector: (Optional) If True, returned vector is a
          'flat' vector of the same value corresponding to the mean of
          the obtained calibration vector. Useful for bad quality
          standard data.
        """
        self._print_msg('Computing flux calibration vector', color=True)
        self._print_msg('Standard Name: %s'%std_name)
        self._print_msg('Standard spectrum path: %s'%std_spectrum_path)

        nm_axis = orb.utils.create_nm_axis(self.dimz, step, order)
        
        # Get real spectrum
        re_spectrum, hdr = self.read_fits(std_spectrum_path, return_header=True)
        if len(re_spectrum.shape) > 1:
            self._print_error(
                'Bad standard shape. Standard spectrum must be a 1D vector !')

        # Standard observation parameters
        std_step = hdr['STEP']
        std_order = hdr['ORDER']
        std_exp_time = hdr['EXPTIME']
        std_step_nb = re_spectrum.shape[0]
        std_nm_axis = orb.utils.create_nm_axis(std_step_nb, std_step, std_order)

        # Real spectrum is converted to ADU/s
        # We must divide by the exposition time
        re_spectrum /= std_exp_time # ADU -> ADU/s

        # Remove portions outside the filter
        (filter_function,
         filter_min_pix, filter_max_pix) = orb.utils.get_filter_function(
            filter_file_path, step, order, re_spectrum.shape[0])
        re_spectrum[:filter_min_pix] = np.nan
        re_spectrum[filter_max_pix:] = np.nan
        
        # Get standard spectrum in erg/cm^2/s/A
        std = Standard(std_name, logfile_name=self._logfile_name,
                       config_file_name=self.config_file_name)
        th_spectrum = std.get_spectrum(std_step, std_order,
                                       re_spectrum.shape[0])

        th_spectrum[np.nonzero(np.isnan(re_spectrum))] = np.nan

        ## Plot Real spectrum vs Theoretical spectrum
        ## import pylab as pl
        ## fig = pl.figure(figsize=(14,5))
        ## ax_re = fig.add_subplot(1,1,1)
        ## plot_axis = std_nm_axis[np.nonzero(~np.isnan(re_spectrum))]
        ## ax_re.plot(std_nm_axis, re_spectrum,
        ##            linewidth=2., linestyle='-', color='0.',
        ##            label='Observed spectrum')
        ## ax_th = ax_re.twinx()
        ## ax_th.plot(std_nm_axis, th_spectrum,
        ##            linewidth=2., linestyle='--', color='0.5',
        ##            label='Standard spectrum')
        ## ax_re.set_xlim([np.nanmin(plot_axis), np.nanmax(plot_axis)])
        ## ax_re.set_ylim([0,np.nanmean(re_spectrum) * 1.3])
        ## ax_th.set_ylim([0,np.nanmean(th_spectrum) * 1.3])
        ## ax_re.set_ylabel('Flux [ADU s$^{-1}$]')
        ## ax_th.set_ylabel('Flux [erg s$^{-1}$ cm$^{-2}$ $\AA^{-1}$]')
        ## handles_re, labels_re = ax_re.get_legend_handles_labels()
        ## handles_th, labels_th = ax_th.get_legend_handles_labels()
        ## ax_re.legend(handles_re+handles_th, labels_re+labels_th,
        ##              loc='lower right')
        ## pl.title('{}'.format(std_name))
        ## pl.show()
        ## quit()
        
        if mean_vector:
            self._print_msg('Mean flux calibration')
            calib = np.empty(self.dimz)
            self._print_msg('Mean theoretical flux of the star: %e erg/cm^2/s/A'%orb.utils.robust_mean(th_spectrum))
            self._print_msg('Mean flux of the star in the cube: %e ADU/s'%orb.utils.robust_mean(re_spectrum))
            calib.fill(orb.utils.robust_mean(th_spectrum) / orb.utils.robust_mean(re_spectrum))
        else:
            self._print_error('Not tested yet')
            # absorption lines are removed from fit
            mean = orb.utils.robust_mean(orb.utils.sigmacut(re_spectrum))
            std = orb.utils.robust_std(orb.utils.sigmacut(re_spectrum))
            weights = np.ones_like(re_spectrum)
            weights[np.nonzero(re_spectrum < mean - 2.*std)] = 0.

            # remove NaN before fitting
            std_nm_axis = std_nm_axis[np.nonzero(~np.isnan(re_spectrum))]
            th_spectrum = th_spectrum[np.nonzero(~np.isnan(re_spectrum))]
            weights = weights[np.nonzero(~np.isnan(re_spectrum))]
            re_spectrum = re_spectrum[np.nonzero(~np.isnan(re_spectrum))]

            # spectra are fitted before being divided
            re_spectrum = orb.utils.polyfit1d(re_spectrum, 1, w=weights) # ADU/s
            th_spectrum = orb.utils.polyfit1d(th_spectrum, 1) # erg/cm^2/s/A

            calib = th_spectrum / re_spectrum # [erg/cm^2/s/A/[ADU/s]]

            # calibration vector is then extrapolated to fit to the range
            # of the spectrum
            calib_fit_coeffs = np.polynomial.polynomial.polyfit(
                std_nm_axis, calib, 1, full=True)
            
            calib = np.polynomial.polynomial.polyval(
                nm_axis, calib_fit_coeffs[0])
            
        self._print_msg(
            'Mean Flambda calibration: %e erg/cm^2/s/A/[ADU/s]'%np.mean(calib))
        
        # calibration vector is converted from erg/cm^2/s/A/[ADU/s] to
        # erg/cm^2/s/A/[ADU]
        calib /= exp_time

        self._print_msg(
            'Mean flux/ADU [flux is in erg/cm^2/s/A] in the cube: %e'%np.mean(
                calib))

        return calib
        
        
        

##################################################
#### CLASS Phase #################################
##################################################

class Phase(Cube):
    """ORBS phase processing class.

    Used to create the phase maps used to correct phase in spectra.
    
    .. note:: Phase data can be obtained by transforming interferogram
      cubes into a phase cube using :class:`process.Interferogram`.
    """


    def _get_phase_map_path(self, order, phase_map_type=None):
        """Return the default path to the phase map.

        :param order: Order of the parameter of the polynomial fitted
          to the phase.

        :param phase_map_type: (Optional) Type of phase map. Must be
          None, 'smoothed', 'fitted', 'error' or 'residual'
        """
        if phase_map_type is not None:
            if phase_map_type == 'smoothed':
                pm_type = "_smoothed"
            elif phase_map_type == 'fitted':
                pm_type = "_fitted"
            elif phase_map_type == 'error':
                pm_type = "_fitted_error"
            elif phase_map_type != 'residual':
                self._print_error("Phase_map_type must be set to 'smoothed', 'fitted', 'error', 'residual' or None")
        else:
            pm_type = ""
            
      
        if phase_map_type != 'residual':
            return self._data_path_hdr + "phase_map%s_order_%d.fits"%(
                pm_type, order)
        else:
            return self._data_path_hdr + "phase_map_residual.fits"
      

    
    def _get_phase_map_header(self, order, phase_map_type=None):
        """Return the header of the phase map.

        :param order: Order of the parameter of the polynomial fitted
          to the phase.

        :param phase_map_type: (Optional) Type of phase map. Must be
          None, 'smoothed', 'fitted', 'error' or 'residual'

        .. note:: smoothed, fitted and error are incompatible. If more
          than one of those options are set to True the priority order
          is smoothed, then fitted, then error.
        """
        if phase_map_type is not None:
            if phase_map_type == 'smoothed':
                header = self._get_basic_header(
                    'Smoothed phase map order %d'%order)
            elif phase_map_type == 'fitted':
                header = self._get_basic_header(
                    'Fitted phase map order %d'%order)
            elif phase_map_type == 'error':
                header = self._get_basic_header(
                    'Fitted phase error map order %d'%order)
            elif phase_map_type == 'residual':
                header = self._get_basic_header(
                    'Residual map on phase fit')
            else:
                self._print_error("Phase_map_type must be set to 'smoothed', 'fitted', 'error', 'residual' or None")
        else:
            header = self._get_basic_header('Phase map order %d'%order)
       
        if self.dimx is not None and self.dimy is not None:
            return (header
                    + self._project_header
                    + self._calibration_laser_header
                    + self._get_basic_frame_header(self.dimx, self.dimy))
        else:
            self._print_warning("Basic header could not be created (frame dimensions are not available)")
            return (header + self._project_header + self._calibration_header)

    def create_phase_maps(self, calibration_laser_map_path, filter_file_path,
                          nm_laser, step, order, interferogram_length=None,
                          fit_order=2, flat_cube=False):
        """Create phase maps. One phase map is created for each order
        of the polynomial fit (e.g. 3 maps are created when fit_order
        = 2)

        :param calibration_laser_map_path: Path to the
          calibration laser map.

        :param filter_file_path: Path to the filter file. see
          :meth:`process.Spectrum.correct_filter` for more information
          about the filter file.

        :param nm_laser: Wavelength [in nm] of the laser used to
          create the calibration laser map.

        :param step: Step size of the moving mirror in nm.

        :param order: Folding order.

        :param interferogram_length: Length of the interferogram from
          which the phase has been computed. Useful if the phase
          vectors have a lower number of points than the
          interferogram: this parameter is used to correct the fit
          coefficients. If None given the phase vectors are assumed to
          have the same number of points as the interferogram (default
          None).

        :param fit_order: (Optional) Order of the polynomial used to
          fit the phase (default 2).

        :param flat_cube: (Optional) If True, data is considered to be
          a flat cube so that the source delivers a high SNR at all
          wavelengths. In this case no filtering is done.

        .. note:: A phase map is a map of the coefficients of the
          polynomial fit to the phase for a given order of the
          fit. The dimensions of the phase map are the same as the
          dimensions of the frames of the phase cube. Values of the
          zeroth order phase map are defined modulo PI. Fit_order + 1
          different phase maps will be created by this method.
        """
        def _compute_filter_maps_in_column(filter_min, filter_max,
                                           correction_map_column,
                                           step, order, dimz):
            filter_min_map_column = np.empty_like(correction_map_column)
            filter_max_map_column = np.empty_like(correction_map_column)
            for ij in range(correction_map_column.shape[0]):                
                filter_min_pix, filter_max_pix = orb.utils.get_filter_edges_pix(
                    None, correction_map_column[ij],
                    step, order, dimz,
                    filter_min=filter_min, filter_max=filter_max)
                # edges are inversed if order is even because the
                # phase vector is not returned (and must not be).
                if int(order) & 1:
                    filter_min_map_column[ij] = filter_min_pix
                    filter_max_map_column[ij] = filter_max_pix
                else: 
                    filter_min_map_column[ij] = dimz - filter_max_pix
                    filter_max_map_column[ij] = dimz - filter_min_pix
                
            return (filter_min_map_column, filter_max_map_column)

        def _fit_phase_in_column(phase_column, filter_min_column,
                                 filter_max_column, fit_order,
                                 interferogram_length):
            EDGE_COEFF = 0.05
            phase_coeff_column = np.zeros((phase_column.shape[0],
                                           fit_order + 1),
                                          dtype=float)
            res_column = np.zeros((phase_column.shape[0]), dtype=float)
            for icol in range(phase_column.shape[0]):
                iphase = phase_column[icol,:]
                # If the interferogram length is different from the
                # phase vector length, the phase vector is resized to
                # get good fit coefficients for a full length vector
                # and not a low resolution vector
                if interferogram_length != iphase.shape[0]:
                    iphase = orb.utils.interpolate_size(
                        iphase, interferogram_length, 1)
                if (np.sum(iphase) != 0.):
                    # weights definition using filter edges. The part
                    # between the edges is reduced to make sure to
                    # get only the points with a high enough SNR
                    weights = np.ones_like(iphase)
                    filter_size = (filter_max_column[icol]
                                   - filter_min_column[icol])
                    if (not np.isnan(filter_min_column[icol])
                        and not np.isnan(filter_max_column[icol])):
                        filter_min = int(filter_min_column[icol]
                                         + EDGE_COEFF * filter_size)
                        filter_max = int(filter_max_column[icol]
                                         - EDGE_COEFF * filter_size)
                        weights[:filter_min] = 1e-20
                        weights[filter_max:] = 1e-20
                        coeffs = np.polynomial.polynomial.polyfit(
                            np.arange(iphase.shape[0]),
                            iphase, fit_order, w=weights,
                            full=True)
                        if len(coeffs[1][0]) == 1:
                            phase_coeff_column[icol,:] = np.array(coeffs[0])
                            res_column[icol] = coeffs[1][0]
                        
            return phase_coeff_column, res_column

        def correct_phase_values(pmap, use_mean=False):
            progress = ProgressBar(pmap.shape[0])
            mean_map = np.mean(pmap[np.nonzero(pmap)])
            for ii in range(pmap.shape[0]):
                for ij in range(pmap.shape[1]):
                    if pmap[ii,ij] != 0.:
                        if not use_mean:
                            test_value = pmap[ii,ij]
                        else:
                            test_value = pmap[ii,ij] - mean_map
                        while (abs(test_value) >= math.pi / 2.):
                            if test_value > 0.:
                                pmap[ii,ij] -= math.pi
                                test_value -= math.pi
                            else:
                                pmap[ii,ij] += math.pi
                                test_value += math.pi
                progress.update(ii, info="Correcting phase values")
            progress.end()
            return pmap

        THRESHOLD_COEFF = 2. # Define the threshold for well enough
                             # fitted phase vectors

        MAX_RES_THRESHOLD = 50. # Define the maximum threshold above
                                # which THRESHOLD_COEFF is
                                # automatically set to 1.
                                
        FILTER_BORDER_COEFF = 0.2 # If no filter file given, the good
                                  # part of the folter is assumed to
                                  # be between 20% and 80% of the
                                  # total band

        # Degree of a median filter applied to the phase map. 0 by default.
        MEDIAN_FILTER_DEG = int(self._get_tuning_parameter(
            'MEDIAN_FILTER_DEG', 0))

        # defining interferogram length
        if interferogram_length is None:
            interferogram_length = self.dimz

        # Calibration laser map load and interpolation
        calibration_laser_map = self.read_fits(calibration_laser_map_path)
        if (calibration_laser_map.shape[0] != self.dimx):
            calibration_laser_map = orb.utils.interpolate_map(
                calibration_laser_map,
                self.dimx, self.dimy)
        ## Create filter min and max map
        if filter_file_path is not None:
            (filter_nm, filter_trans,
             filter_min, filter_max) = orb.utils.read_filter_file(
                filter_file_path)
        else:
            nm_axis = orb.utils.create_nm_axis(self.dimz, step, order)
            nm_range = nm_axis[-1] - nm_axis[0]
            filter_min = int(FILTER_BORDER_COEFF * nm_range + nm_axis[0])
            filter_max = int((1. - FILTER_BORDER_COEFF) * nm_range + nm_axis[0])
            
        correction_map = calibration_laser_map / nm_laser

        filter_min_map = np.empty((self.dimx, self.dimy), dtype=float)
        filter_max_map = np.empty((self.dimx, self.dimy), dtype=float)

        job_server, ncpus = self._init_pp_server()
        progress = ProgressBar(self.dimx)
        for ii in range(0, self.dimx, ncpus):
            # no more jobs than frames to compute
            if (ii + ncpus >= self.dimx):
                ncpus = self.dimx - ii

            jobs = [(ijob, job_server.submit(
                _compute_filter_maps_in_column, 
                args=(filter_min, filter_max,
                      correction_map[ii+ijob,:],
                      step, order, interferogram_length),
                modules=("numpy as np", "import orb.utils"))) 
                    for ijob in range(ncpus)]

            for ijob, job in jobs:
                (filter_min_map[ii+ijob,:],
                 filter_max_map[ii+ijob,:]) = job()

            progress.update(ii, info='Computing filter maps')
        progress.end()
        
        ## Create phase maps
        phase_maps = np.empty((self.dimx, self.dimy, fit_order + 1),
                              dtype=float)
        res_map = np.empty((self.dimx, self.dimy), dtype=float)
            
        for iquad in range(0, self.QUAD_NB):
            (x_min, x_max, 
             y_min, y_max) = self.get_quadrant_dims(iquad)
            iquad_data = self.get_data(x_min, x_max, 
                                       y_min, y_max, 
                                       0, self.dimz)
            job_server, ncpus = self._init_pp_server()
            progress = ProgressBar(int(x_max-x_min))

            for ii in range(0, x_max-x_min, ncpus):
                # no more jobs than frames to compute
                if (ii + ncpus >= x_max-x_min):
                    ncpus = x_max - x_min - ii

                # correct spectrum columns
                jobs = [(ijob, job_server.submit(
                    _fit_phase_in_column, 
                    args=(iquad_data[ii+ijob,:,:],
                          filter_min_map[x_min+ii+ijob, y_min:y_max],
                          filter_max_map[x_min+ii+ijob, y_min:y_max],
                          fit_order, interferogram_length),
                    modules=("numpy as np", "import orb.utils"))) 
                        for ijob in range(ncpus)]

                for ijob, job in jobs:
                    (phase_maps[x_min+ii+ijob,y_min:y_max,:],
                     res_map[x_min+ii+ijob,y_min:y_max]) = job()
                
                progress.update(ii, 
                                info="quad : %d, column : %d"%(iquad + 1, ii))

            self._close_pp_server(job_server)
            progress.end()

        # save residual map
        res_map_path = self._get_phase_map_path(0, phase_map_type='residual')
        self.write_fits(
            res_map_path, res_map, 
            fits_header = self._get_phase_map_header(
                0, phase_map_type='residual'),
            overwrite=self.overwrite)
        
        if self.indexer is not None:
            self.indexer['phase_map_residual'] = res_map_path

        if not flat_cube:
            # remove bad fitted phase values
            flat_res_map = res_map[np.nonzero(res_map)].flatten()
            res_map_med = np.median(flat_res_map)
            res_map_std = orb.utils.robust_std(flat_res_map)
            flat_res_map = flat_res_map[np.nonzero(
                flat_res_map < res_map_med + 0.5 * res_map_std)]
            res_threshold = (THRESHOLD_COEFF
                             * np.median(flat_res_map))

            if res_threshold > MAX_RES_THRESHOLD:
                self._print_warning("Residual threshold is too high (%f > %f) : phase correction might be bad !"%(res_threshold, MAX_RES_THRESHOLD))
                res_threshold = np.median(flat_res_map)

            self._print_msg("Residual threshold on phase fit: %f"%res_threshold)
            mask_map = np.ones_like(res_map)
            mask_map[np.nonzero(res_map > res_threshold)] = 0.

            for iorder in range(fit_order + 1):
                phase_maps[:,:,iorder] *= mask_map
        else:
            self._print_warning('No bad fit filter. Cube is considered to be a flat cube with a high SNR everywhere.')

        ## Correct 0th order phase map
            
        # As the phase is defined modulo PI, values of the phase map
        # at the zeroth order are corrected to minimize their
        # difference.
        phase_map_0 = np.copy(phase_maps[:,:,0])
        mask = np.nonzero(phase_map_0 == 0)
        phase_map_0 = correct_phase_values(phase_map_0)
        phase_map_0[mask] = 0.
        phase_map_0 = correct_phase_values(phase_map_0, use_mean=True)
        phase_map_0[mask] = 0.
        phase_maps[:,:,0] = phase_map_0

        # Median filtering of the 0th order phase map
        if MEDIAN_FILTER_DEG > 0:
            self._print_warning('Median filtering of the phase map (degree: {})'.format(MEDIAN_FILTER_DEG))
            import scipy.ndimage.filters
            phase_maps[:,:,0] = scipy.ndimage.filters.median_filter(
                phase_maps[:,:,0], size=(MEDIAN_FILTER_DEG*2+1,
                                         MEDIAN_FILTER_DEG*2+1))
        
        # SAVE MAPS
        for iorder in range(fit_order + 1):
            phase_map_path = self._get_phase_map_path(iorder)

            self.write_fits(phase_map_path, phase_maps[:,:,iorder], 
                            fits_header=
                            self._get_phase_map_header(iorder),
                            overwrite=self.overwrite)

            if self.indexer is not None:
                self.indexer['phase_map_%d'%iorder] = phase_map_path
            


    def smooth_phase_map(self, phase_map_path):
        """Smooth values of a phase map.

        This method smooth a phase map by trying to clear most of the
        difference between adjacent pixels (remember that the phase is
        defined modulo PI).

        :param phase_map_path: Path to the phase map
        """
                
        def smooth_columns(pmap):
            progress = ProgressBar(pmap.shape[0])
            for ii in range(1, pmap.shape[0]):
                coli = np.mean((pmap[ii,:])[np.nonzero(pmap[ii,:])])
                coli_1 = np.mean((pmap[ii-1,:])[np.nonzero(pmap[ii-1,:])])
                column_diff = coli - coli_1
                while abs(column_diff) >= math.pi / 2.:
                    if column_diff >= 0.:
                        pmap[ii,:] -= math.pi
                        column_diff -= math.pi
                    else:
                        pmap[ii,:] += math.pi
                        column_diff += math.pi
                        
                progress.update(ii, info="Smoothing columns values")
            progress.end()
            return pmap

        def smooth_phase(pmap, deg=10):
            def smooth_box(ii, ij, pmap, deg):
                if ii > 0: xmin = ii - deg
                else: xmin = 0
                if ii < pmap.shape[0] - deg: xmax = ii + deg
                else: xmax = pmap.shape[0] - deg
                if ij > 0: ymin = ij - deg
                else: ymin = 0
                if ij < pmap.shape[1] - deg: ymax = ij + deg
                else: ymax = pmap.shape[1] - deg

                box = np.copy(pmap[xmin:xmax+1, ymin:ymax+1])
                box_mask = np.nonzero(box)
                box_mask_inv = np.nonzero(box == 0)
                if np.any(box):
                    box -= float(np.mean(box[box_mask]))
                    box[box_mask_inv] = 0.
                    bad_values = np.nonzero(abs(box) >= math.pi / 2. )
                    for ibad in range(len(bad_values[0])):
                        badx = bad_values[0][ibad]
                        bady = bad_values[1][ibad]
                        while abs(box[badx, bady]) >= math.pi / 2.:
                            if box[badx, bady] >= 0.:
                                box[badx, bady] -= math.pi
                                pmap[xmin + badx,
                                     ymin + bady] -= math.pi
                            else:
                                box[badx, bady] += math.pi
                                pmap[xmin + badx,
                                     ymin + bady] += math.pi


            progress = ProgressBar(pmap.shape[0] - 2*deg)
            for ii in range(deg, pmap.shape[1] - deg):
                for ij in range(deg, pmap.shape[0] - deg):
                    smooth_box(ii, ij, pmap, deg)
                                        
                progress.update(ii - deg, info="Smoothing phase values")
            progress.end()

            return pmap


        SMOOTH_DEG_COEFF = 0.025 # ratio of the smoothing degree to
                                 # the phase map shape

        # Load map
        phase_map = self.read_fits(phase_map_path)

        # Smooth map
        mask = np.nonzero(phase_map == 0)
        phase_map = smooth_phase(phase_map, deg=int(SMOOTH_DEG_COEFF * (phase_map.shape[0] + phase_map.shape[1])/2.))
        phase_map[mask] = 0.
        phase_map = smooth_columns(phase_map)
        phase_map[mask] = 0.    

        # Save smoothed map
        phase_map_path = self._get_phase_map_path(0, phase_map_type='smoothed')

        self.write_fits(phase_map_path, phase_map, 
                        fits_header=self._get_phase_map_header(
                            0, phase_map_type='smoothed'),
                        overwrite=self.overwrite)
        if self.indexer is not None:
            self.indexer['phase_map_smoothed_0'] = phase_map_path
    
    def fit_phase_map(self, phase_map_path, residual_map_path):
        """Fit the phase map.

        Help remove most of the noise. This process is useful if the phase
        map has been computed from astronomical data without a high SNR.

        :param phase_map_path: Path to the phase map

        :param residual_map_path: Path to the residual on phase fit
        """

        FIT_DEG = 1 # Degree of the polynomial used fo the fit
        
        MAX_FIT_ERROR = 0.1 # Maximum fit error over which a warning
                            # is raised
                       
        BORDER = 0.1 # percentage of the image length removed on the
                     # border to fit the phase map (cannot be more
                     # than 0.5)

        phase_map = self.read_fits(phase_map_path)
        # border points are removed
        mask = np.ones_like(phase_map, dtype=bool)
        border = (self.dimx + self.dimy)/2. * BORDER 
        mask[border:-border,border:-border:] = False
        mask[np.nonzero(phase_map == 0.)] = True
        phase_map[np.nonzero(mask)] = np.nan
        # error map
        err_map = self.read_fits(residual_map_path)
        err_map[np.nonzero(mask)] = np.nan
        err_map = np.sqrt(err_map)

        fitted_phase_map, error_map, fit_error = orb.utils.fit_map(
            phase_map, err_map, FIT_DEG)
        
        self._print_msg(
            "Normalized root-mean-square deviation on the fit: %f%%"%(
                fit_error*100.))

        if fit_error > MAX_FIT_ERROR:
            self._print_warning("Normalized root-mean-square deviation on the fit is too high (%f > %f): phase correction will certainly be uncorrect !"%(fit_error, MAX_FIT_ERROR))
        
        ## save fitted phase map and error map
        error_map_path = self._get_phase_map_path(0, phase_map_type='error')
        fitted_map_path = self._get_phase_map_path(0, phase_map_type='fitted')
        self.write_fits(
            error_map_path, error_map, 
            fits_header= self._get_phase_map_header(0, phase_map_type='error'),
            overwrite=self.overwrite)
        if self.indexer is not None:
            self.indexer['phase_map_fitted_error_0'] = error_map_path
        self.write_fits(
            fitted_map_path, fitted_phase_map, 
            fits_header= self._get_phase_map_header(0, phase_map_type='fitted'),
            overwrite=self.overwrite)
        if self.indexer is not None:
            self.indexer['phase_map_fitted_0'] = fitted_map_path


#################################################
#### CLASS Standard #############################
#################################################
class Standard(Tools):

    def __init__(self, std_name, logfile_name=None, **kwargs):
        """Initialize Standard class.

        :param std_name: Name of the standard.

        :param logfile_name: (Optional) Give a specific name to the
          logfile (default None).

        :param kwargs: Kwargs are :meth:`core.Tools` properties.
        """
        Tools.__init__(self, **kwargs)
        
        if logfile_name is not None:
            self._logfile_name = logfile_name
            
        std_file_path, std_type = self._get_standard_file_path(std_name)

        if std_type == 'MASSEY' or std_type == 'MISC':
            self.ang, self.flux = self.read_massey_dat(std_file_path)
        elif std_type == 'CALSPEC':
            self.ang, self.flux = self.read_calspec_fits(std_file_path)
        else:
            self._print_error(
                "Bad type of standard file. Must be 'MASSEY', 'CALSPEC' or 'MISC'")
       

    def _get_data_prefix(self):
        return (os.curdir + os.sep + 'STANDARD' + os.sep
                + 'STD' + '.')

    def get_spectrum(self, step, order, n):
        """Return part of the standard spectrum corresponding to the
        observation parameters.

        Returned spectrum is calibrated in erg/cm^2/s/A

        :param order: Folding order
        :param step: Step size in um
        :param n: Number of steps
        """
        nm_axis = orb.utils.create_nm_axis(n, step, order)
        ang_axis = nm_axis * 10.
        return orb.utils.interpolate_axis(
            self.flux, ang_axis, 1, old_axis=self.ang)

    def read_massey_dat(self, file_path):
        """Read a data file from Massey et al., Spectrophotometric
        Standards (1988) and return a tuple of arrays (wavelength,
        flux).
        
        Returned wavelength axis is in A. Returned flux is converted
        in erg/cm^2/s/A.

        :param file_path: Path to the Massey dat file (generally
          'spXX.dat').
        """
        std_file = self.open_file(file_path, 'r')
        
        spec_ang = list()
        spec_mag = list()
        for line in std_file:
             line = line.split()
             spec_ang.append(line[0])
             spec_mag.append(line[1])

        spec_ang = np.array(spec_ang, dtype=float)
        spec_mag = np.array(spec_mag, dtype=float)
        
        # convert mag to flux in erg/cm^2/s/A
        spec_flux = orb.utils.ABmag2flambda(spec_mag, spec_ang)

        return spec_ang, spec_flux

    def read_calspec_fits(self, file_path):
        """Read a CALSPEC fits file containing a standard spectrum and
          return a tuple of arrays (wavelength, flux).

        Returned wavelength axis is in A. Returned flux is in
        erg/cm^2/s/A.
        
        :param file_path: Path to the Massey dat file (generally
          'spXX.dat').
        """
        hdu = self.read_fits(file_path, return_hdu_only=True)
        hdr = hdu[1].header
        data = hdu[1].data

        self._print_msg('Calspec file flux unit: %s'%hdr['TUNIT2'])
        
        # wavelength is in A
        spec_ang = np.array([data[ik][0] for ik in range(len(data))])

        # flux is in erg/cm2/s/A
        spec_flux = np.array([data[ik][1] for ik in range(len(data))])

        return spec_ang, spec_flux

    
    def compute_image_calibration(self, images_list_path, filter_name,
                                  exp_time, std_coords, init_fwhm_arc,
                                  fov, profile_name='gaussian',
                                  moffat_beta=3.5, prim_surf=17554,
                                  verbose=False):

        """
        Compute 'flambda' calibration coefficient for a spectrum cube
        from a set of images of a standard star.

        :param image_list_path: Path to a list of images of a standard
          star.

        :param filter_name: Name of the filter

        :param exp_time: Exposition time of one frame.

        :param std_coords: Pixel coordinates of the standard as a
          tuple [x,y]

        :param init_fwhm_arc: Rough FWHM of the stars in the frame in
          arcseconds

        :param fov: Field of View of the frame

        :param order: Folding order
        
        :param step: Step size in um

        :param step_nb: Number of steps

        :param profile_name: (Optional) Name of the PSF profile used
          for photometry. Can be 'gaussian' or 'moffat' (default
          'moffat').

        :param moffat_beta: (Optional) Initial value of the moffat
          beta parameter (default 3.5).
        
        :param prim_surf: (Optional) Surface of the primary mirror in
          cm^2. Used to print the rough flux of photons. Do not change
          anything to the flambda coefficient.

        :param verbose: (Optional) If True print more information to
          check results.
        """
        # read filter file
        filter_file_path = self._get_filter_file_path(filter_name)
        (filter_nm, filter_trans,
         filter_min, filter_max) = orb.utils.read_filter_file(filter_file_path)

        # convert filter scale to A
        filter_ang = filter_nm * 10.
        # convert percentage of transmission
        filter_trans /= 100.

        # filter band pass is cut in case the standard spectrum axis is smaller
        filter_trans = filter_trans[filter_ang < self.ang[-1]]
        filter_ang = filter_ang[filter_ang < self.ang[-1]]
        filter_trans = filter_trans[filter_ang > self.ang[0]]
        filter_ang = filter_ang[filter_ang > self.ang[0]]
        
        # interpolate standard spectrum 
        interp_spec = interpolate.InterpolatedUnivariateSpline(self.ang,
                                                               self.flux, k=1)
        interp_spec = interp_spec(filter_ang)
        
        # compute mean flux of the star in the filter band
        std_flux = (np.sum(interp_spec * filter_trans)
                    / np.sum(filter_trans))
        

        self._print_msg('Mean flux of the star in the filter band: %e [erg/s/cm^2/A]'%std_flux)

        if verbose:
            # compute mean energy of 1 photon in ergs
            h = 6.62653319e-27 # [erg.s]
            c = 299792458 # [m/s]
            lambda_mean = ((filter_max + filter_min)/2.) * 1e-9 # [m]
            mean_ph_energy = h * c / lambda_mean # [ergs]
            self._print_msg('Mean energy of 1 photon: %e [erg]'%mean_ph_energy)
            # compute flux of photons
            ph_flux = std_flux / mean_ph_energy # [ph/cm^2/s/A]
            self._print_msg('Flux of photons: %e [ph/cm^2/s/A]'%ph_flux)
        
        ## Photometry
        std = Cube(images_list_path,
                   config_file_name=self.config_file_name)
        if std.dimz == 1:
            std_master_frame = std.get_data_frame(0)
        elif std.dimz <= 3:
            std_master_frame = np.median(std[:,:,:], axis=2)
        elif std.dimz <= 15:
            std_master_frame = orb.utils.create_master_frame(
                std[:,:,:], silent=True)
        else: # large number of frames to combine
            std_master_frame = orb.utils.create_master_frame(
                std[:,:,:], silent=True, reject='minmax')

        astrom = Astrometry(std_master_frame, init_fwhm_arc,
                            fov, profile_name=profile_name,
                            moffat_beta=moffat_beta,
                            data_prefix=self._data_prefix,
                            logfile_name=self._logfile_name,
                            tuning_parameters=self._tuning_parameters,
                            silent=True,
                            config_file_name=self.config_file_name)

        astrom.reset_star_list(np.array([std_coords]))
        fit_results = astrom.fit_stars_in_frame(0, local_background=False,
                                                multi_fit=True,
                                                precise_guess=True)
        
        star_counts = fit_results[0, 'aperture_flux']
        #if verbose:
        self._print_msg('Raw Star photometry: %e ADU'%star_counts)

        star_flux = star_counts / exp_time # [ADU/s]
        if verbose:
            self._print_msg('Star flux: %e ADU/s'%star_flux)
        
        ## Compute calibration coeff
        if verbose:
            ph_calib = ph_flux / star_flux
            self._print_msg('Photons calibration: %e ph/cm^2/s/A/[ADU/s]'%
                            ph_calib)
            self._print_msg(
                'Estimated number of photons per ADU: %e ph/ADU'%
                (ph_calib * prim_surf * (filter_max - filter_min) * 10.))
            
        f_lambda_calib = std_flux / star_flux # erg/cm2/s/A / [ADU/s]
        self._print_msg(
            'Flambda calibration of the image: %e erg/cm^2/s/A/[ADU/s]'%
                        f_lambda_calib)
        
        return f_lambda_calib
