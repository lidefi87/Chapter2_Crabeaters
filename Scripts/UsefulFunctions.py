#Calling libraries
import argparse
import cosima_cookbook as cc
import netCDF4 as nc
import xarray as xr
import numpy as np
import pandas as pd
import copy
import os
import re
import rasterio
import geopandas
import rasterio.plot
import rioxarray
from shapely.geometry import mapping, Polygon
import calendar
import statsmodels.api as sm
import datetime as dt
import scipy.stats as ss
from glob import glob
import xesmf as xe
from pyproj import Transformer, CRS, transform, Proj
from sklearn.neighbors import BallTree


########
#Defining functions

########
#Loads ACCESS-OM2-01 sea ice and ocean data for the Southern Ocean. If ice data is accessed, it corrects the time and coordinate grid to match ocean outputs.
def getACCESSdata_SO(var, start, end, freq, ses, minlat = -90, maxlat = -45, 
                  exp = '01deg_jra55v140_iaf_cycle4', ice_data = False):
    '''
    Defining function that loads data automatically using `cc.querying.getvar()` in a loop. The inputs needed are similar to those for the `cc.querying.getvar()` function, with the addition of inputs to define an area of interest.  
The `getACCESSdata` will achieve the following:  
- Access data for the experiment and variable of interest at the frequency requested and within the time frame specified  
- Apply **time corrections** as midnight (00:00:00) is interpreted differently by the CICE model and the xarray package.
    - CICE reads *2010-01-01 00:00:00* as the start of 2010-01-01, while xarray interprets it as the start of the following day (2010-01-02). To fix this problem, 12 hours are subtracted from the time dimension (also known as *time coordinate*).  
- Latitude and longitude will be corrected in the dataset using the `geolon_t` dataset. The coordinate names are replaced by names that are more intuitive.  
- Minimum and maximum latitudes and longitudes can be specified in the function to access specific areas of the dataset if required.  The **Southern Ocean** is defined as ocean waters south of 45S.

    Inputs:
    var - Short name for the variable of interest
    start - Time from when data has to be returned
    end - Time until when data has to be returned
    freq - Time frequency of the data
    ses - Cookbook session
    minlat - minimum latitude from which to return data. If not set, defaults to -90 to cover the Southern Ocean.
    maxlat - maximum latitude from which to return data. If not set, defaults to -45 to cover the Southern Ocean.
    exp - Experiment name. Default is 01deg_jra55v140_iaf_cycle4.
    ice_data - Boolean, when True the variable being called is related to sea ice, when False is not. Default is set to False (i.e., it assumes variable is related to the ocean).
        
    Output:
    Data array with corrected time and coordinates within the specified time period and spatial bounding box.
    '''
    
    #If data being accessed is an ice related variable, then apply the following steps
    if ice_data == True:
        #Accessing data
        vararray = cc.querying.getvar(exp, var, ses, frequency = freq, start_time = start, end_time = end, decode_coords = False)
        #Accessing corrected coordinate data to update geographical coordinates in the array of interest
        area_t = cc.querying.getvar(exp, 'area_t', ses, n = 1)
        #Apply time correction so data appears in the middle (12:00) of the day rather than at the beginning of the day (00:00)
        vararray['time'] = vararray.time.to_pandas() - dt.timedelta(hours = 12)
        #Change coordinates so they match ocean dimensions 
        vararray.coords['ni'] = area_t['xt_ocean'].values
        vararray.coords['nj'] = area_t['yt_ocean'].values
        #Rename coordinate variables so they match ocean data
        vararray = vararray.rename(({'ni':'xt_ocean', 'nj':'yt_ocean'}))
        #Drop coordinates that are no longer needed
        if len(vararray.coords) > 3:
            vararray = vararray.drop([i for i in vararray.coords if i not in ['time', 'xt_ocean', 'yt_ocean']])
    else:
        #Accessing data
        vararray = cc.querying.getvar(exp, var, ses, frequency = freq, start_time = start, end_time = end)
    #Subsetting data to area of interest
    if vararray.name in ['u', 'v']:
        vararray = vararray.sel(yu_ocean = slice(minlat, maxlat))
    else:
        vararray = vararray.sel(yt_ocean = slice(minlat, maxlat))
    return vararray

########
#Correcting longitude values in a data array so they are between -180 and +180 degrees
def corrlong(array):
    '''
    Inputs:
    array - Data array on which longitude corrections will be applied.
    
    Output:
    Data array with corrected longitude values.
    '''
    
    if array.name in ['u', 'v']:
        long_name = 'xu_ocean'
    else:
        long_name = 'xt_ocean'
    
    #Apply longitude correction
    array[long_name] = ((array[long_name] + 180)%360)-180
    array = array.sortby(array[long_name])
    
    return array


########
#Correcting longitude values in a data array so they are between -180 and +180 degrees
def extract_bottom_layer(da):
    '''
    Inputs:
    da - Data array from which bottom layer needs to be extracted.
    
    Output:
    Data array with a single depth layer.
    '''

    #Give a value of 1 to all cells containing environmental data in a single time step
    mask_2d = xr.where(~np.isnan(da.isel(time = 0)), 1, np.nan)
    #Perform a cumulative sum along depth axis to identify deepest grid cell with environmental data
    mask_2d = mask_2d.cumsum('st_ocean').where(~np.isnan(da.isel(time = 0)))
    #Create a mask identifying deepest cells with a value of 1
    mask_2d = xr.where(mask_2d == mask_2d.max('st_ocean'), 1, np.nan)
    #Apply mask to original data array
    da = (mask_2d*da).sum('st_ocean')
    #Rearrange dimensions to match original dataset
    da = da.transpose('time', 'yt_ocean', 'xt_ocean')
    #Returning bottom layer
    return da


########
#This function calculates distance from each grid cell to its nearest neighbour in a reference data array. Nearest neighbour refers to the search of the point within a predetermined set of points that is located closest (spatially) to a given point.
def nn_dist(target_da, grid_coords_numpy, **kwargs):
    '''
    Inputs:
    target_da (data array) - Reference points to which nearest neighbour distances will be calculated. Maximum values along y axis will be used as reference points.
    grid_coords_numpy (np data array) - Coordinate pairs for each grid cell from which nearest neighbour distance will be calculated
    Optional:
    folder_out (string) - Path to folder where output will be saved
    file_base (string) - Base name to be used to save outputs
    
    Output:
    Data array with distance to nearest neighbour
    '''
    #Getting coordinate pairs for sea ice edge
    ice_coords = np.vstack([target_da.yt_ocean[target_da.argmax(dim = 'yt_ocean')],
                            target_da.xt_ocean]).T
    
    #Set up Ball Tree (nearest neighbour algorithm).
    ball_tree = BallTree(np.deg2rad(ice_coords), metric = 'haversine')
    #The nearest neighbour calculation will give two outputs: distances in radians and indices
    dist_rad, ind = ball_tree.query(grid_coords_numpy, return_distance = True)
    #Transform distances from radians to km and changing data to data array
    earth_radius_km = 6371
    dist_km = xr.DataArray(data = [(dist_rad*earth_radius_km).reshape(target_da.shape)],
                           dims = ['time', 'yt_ocean', 'xt_ocean'],
                           coords = {'time': [target_da.time.values],
                                     'yt_ocean': target_da.yt_ocean.values,
                                     'xt_ocean': target_da.xt_ocean.values},
                           name = 'dist_km')
    dist_km = dist_km.assign_attrs({'units': 'km',
                          'long_name': 'distance to nearest neighbour'})
    
    #If path to folder provided, then save output
    if 'folder_out' in kwargs.keys():
        #Make sure output folder exists
        os.makedirs(kwargs.get('folder_out'), exist_ok = True)
        if 'file_base' in kwargs.keys():
            #Extract year and month to use in filename
            month = str(dist_km.time.dt.month.values[0]).zfill(2)
            year = dist_km.time.dt.year.values[0]
            file_base = kwargs.get('file_base')
            file_out = os.path.join(kwargs.get('folder_out'), 
                                f'{file_base}_{year}-{month}.nc')
            dist_km.to_netcdf(file_out)
        else:
            'File name base is needed to save output. Month and year will be added to this string'
        
    return dist_km


########
#This function creates a colour palette using Crameri's palettes (Crameri, F. (2018), Scientific colour-maps, Zenodo, doi:10.5281/zenodo.1243862)
def colourMaps(colourLibraryPath, palette, rev = True):
    '''
    Inputs:
    colourLibraryPath - the file path where the palettes are currently saved.
    palette - name of the palette to be created.
    rev - Boolean. If True, it will create a normal and reversed version of the palette. If False, it will only return one palette
    
    Outputs:
    One or two palettes based on Crameri (2018) that can be used to colour matplotlib figures
    '''
    #Load relevant libraries to set Scientific Colour Map library
    from matplotlib.colors import LinearSegmentedColormap
    from matplotlib.colors import ListedColormap

    #Set path where the scientific library is found
    cm_data = np.loadtxt(os.path.join(colourLibraryPath, palette, (palette + '.txt')))
    #Create a colour map based on 'palette' argument
    pal_map_adv = LinearSegmentedColormap.from_list(palette, cm_data)
        
    if rev == True:
        pal_map_ret = ListedColormap(cm_data[::-1])
        return pal_map_adv,pal_map_ret
    else:
        return pal_map_adv


########
#This function creates a single data frame with SDM outputs that can be used to create a data array for plotting
def df_ready(file_path, model, df_coords):
    '''
    Inputs:
    file_path - file path to data location
    model - name of the SDM algorithm used to create outputs
    df_coords - target grid to be used to create data frame
    
    Outputs:
    Data frame containing SDM predictions
    '''
    #Load csv file
    df = pd.read_csv(file_path)
    #Add SDM algorithm to data frame
    df['model'] = model
    #Keep relevant columns 
    df = df[['yt_ocean', 'xt_ocean', 'pred', 'month', 'model']]
    #Add coordinates from target grid
    df = df_coords.merge(df, on = ['xt_ocean', 'yt_ocean', 'month'], how = 'left')
    #Return data frame
    return df


#This function creates a single dataset with SDM outputs from a list of data frames
def ds_sdm(list_df, grid_sample):
    '''
    Inputs:
    list_df - a list of data frames to be used in dataset creation
    grid_sample - sample target grid. It must be two dimensional
    df_coords - target grid to be used to create data frame
    
    Outputs:
    Data frame containing SDM predictions
    '''
    #Create a single data frame with all predictions
    df = pd.concat(list_df)

    #Initialising empty dictionary to create dataset
    ds = {}

    #Looping through each month
    for m in df.month.unique():
        mth = df[df.month == m]
        mth_mean = mth.groupby(['yt_ocean', 'xt_ocean']).mean('pred').reset_index()
        mth_mean['model'] = 'Ensemble'
        mth = pd.concat([mth, mth_mean])
        mods = mth.model.dropna().unique()
        mth_da = xr.DataArray(data = mth.pred.values.reshape((len(mods),*grid_sample.shape)),
                              dims = ['model', 'yt_ocean', 'xt_ocean'],
                              coords = {'model': mods,
                                        'xt_ocean': grid_sample.xt_ocean.values,
                                        'yt_ocean': grid_sample.yt_ocean.values})
        mth_name = calendar.month_name[m]
        ds[mth_name] = mth_da

    #Creating datasets
    ds = xr.Dataset(ds)
    
    #Return dataset
    return ds


########
def main(inargs):
    '''Run the program.'''

if __name__ == '__main__':
    description = 'This script contains functions used to perform timeseries within different sectors of the Southern Ocean.'
    parser = argparse.ArgumentParser(description = description)

    args = parser.parse_args()
    main(args)