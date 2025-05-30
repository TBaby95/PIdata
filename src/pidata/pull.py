import sys
import clr

sys.path.append(r'C:\Program Files (x86)\PIPC\AF\PublicAssemblies\4.0')
clr.AddReference('OSIsoft.AFSDK')

from OSIsoft.AF import *
from OSIsoft.AF.PI import *
from OSIsoft.AF.Asset import *
from OSIsoft.AF.Data import *
from OSIsoft.AF.Time import *
from OSIsoft.AF.UnitsOfMeasure import *

piServers = PIServers()

import datetime
import time
import pandas as pd
import numpy as np
import json
from typing import List, Dict, Any, Optional, Union

from dateutil.relativedelta import relativedelta, MO
from dateutil import parser

from .utils import strip_timestamp


def aggregated_vals(tags: List[str], 
                   start_time: str = "-30d", 
                   end_time: str = "", 
                   interval: str = '12h', 
                   method: str = 'Average', 
                   server: str = 'default') -> pd.DataFrame:
    """
    Optimized version using bulk retrieval via PIPointList.
    
    Will return a pandas dataframe of aggregated values (averaged values by default) 
    between `start_time` and `end_time`, within the given interval
    
    Arguments: 
    tags         :  list or list like
    start_time   :  Time of the first data point. Default: '-30d' (thirty days ago)
    end_time     :  Time of the last data point. Default: '' (empty/current time)
    interval     :  Time between data points. Default: '12h'
    method       :  Aggregation method (Total, Average, Minimum, Maximum, etc.)
    server       :  Name of the PI server to use. Uses the default if none is provided
    """
    
    # Handle empty tag list
    if not tags:
        return pd.DataFrame()
    
    # Get PI Server
    if server != 'default':
        piServer = PIServer.FindPIServer(server)
    else:
        piServer = piServers.DefaultPIServer
        
    if piServer is None:
        piServer = piServers.DefaultPIServer
    
    # Find all PI Points
    points = []
    tag_to_point = {}
    for tag in tags:
        try:
            pt = PIPoint.FindPIPoint(piServer, tag)
            points.append(pt)
            tag_to_point[pt.Name] = tag  # Map PI point name back to original tag
        except Exception as e:
            print(f"Warning: Could not find tag {tag}: {e}")
    
    if not points:
        return pd.DataFrame(columns=tags)
    
    # Create PIPointList for bulk operations
    point_list = PIPointList(points)
    
    # Set up time range and summary parameters
    time_range = AFTimeRange(start_time, end_time)
    span = AFTimeSpan.Parse(interval)
    summary_type = eval(f'AFSummaryTypes.{method}')
    
    # Configure paging for large data sets
    paging_config = PIPagingConfiguration(PIPageType.TagCount, 100)
    
    # Perform bulk retrieval
    try:
        summaries = point_list.Summaries(
            time_range,
            span,
            summary_type,
            AFCalculationBasis.TimeWeighted,
            AFTimestampCalculation.Auto,
            paging_config
        )
        
        # Pre-allocate data structures for efficiency
        data_dict = {}
        
        # Process results
        for summary in summaries:
            point_name = summary.PIPoint.Name
            original_tag = tag_to_point.get(point_name, point_name)
            
            # Extract timestamps and values
            timestamps = []
            values = []
            
            for event in summary.Value:
                timestamps.append(strip_timestamp(event.Timestamp))
                try:
                    values.append(np.float32(event.Value))
                except (TypeError, ValueError):
                    values.append(None)
            
            # Create series for this tag
            if timestamps:
                data_dict[original_tag] = pd.Series(values, index=timestamps)
        
        # Create DataFrame from all series
        if data_dict:
            df = pd.DataFrame(data_dict)
            # Ensure all requested tags are present
            for tag in tags:
                if tag not in df.columns:
                    df[tag] = np.nan
            return df[tags]  # Return columns in requested order
        else:
            return pd.DataFrame(columns=tags)
            
    except Exception as e:
        print(f"Error in bulk retrieval, falling back to sequential: {e}")
        # Fall back to original implementation
        return _aggregated_vals_sequential(tags, start_time, end_time, interval, method, server)


def _aggregated_vals_sequential(tags, start_time="-30d", end_time="", interval='12h', 
                                method='Average', server='default'):
    """Original sequential implementation as fallback"""
    
    if server != 'default':
        piServer = PIServer.FindPIServer(server)
    else:
        piServer = piServers.DefaultPIServer
        
    if piServer is None:
        piServer = piServers.DefaultPIServer
        
    time_range = AFTimeRange(start_time, end_time)
    span = AFTimeSpan.Parse(interval)
    
    data = pd.DataFrame(columns=tags)
    
    for tag in tags: 
        pt = PIPoint.FindPIPoint(piServer, tag)
        name = pt.Name.lower()
        
        summary_type_object = eval('AFSummaryTypes.' + method)
        averages = pt.Summaries(time_range, span, summary_type_object, 
                               AFCalculationBasis.TimeWeighted, AFTimestampCalculation.Auto)
        
        for average in averages:
            for event in average.Value:                        
                 try:
                     data.at[strip_timestamp(event.Timestamp), tag] = np.float32(event.Value)
                 except TypeError:
                     data.at[strip_timestamp(event.Timestamp), tag] = None
                   
    return data


def recorded_vals(tags: List[str], 
                 start_time: str = "-30d", 
                 end_time: str = "", 
                 server: str = 'default') -> pd.DataFrame:
    """
    Optimized version using bulk retrieval via PIPointList.
    
    Will return a pandas df of recorded vals between start and end time
    
    Arguments: 
    tags         :  list or list like
    start_time   :  Time of the first data point. Default: '-30d' (thirty days ago)
    end_time     :  Time of the last data point. Default: '' (empty/current time)
    server       :  Name of the PI server to use. Uses the default if none is provided
    """
    
    # Handle empty tag list
    if not tags:
        return pd.DataFrame()
    
    # Get PI Server
    if server != 'default':
        piServer = PIServer.FindPIServer(server)
    else:
        piServer = piServers.DefaultPIServer
        
    if piServer is None:
        piServer = piServers.DefaultPIServer
    
    # Find all PI Points
    points = []
    tag_to_point = {}
    for tag in tags:
        try:
            pt = PIPoint.FindPIPoint(piServer, tag)
            points.append(pt)
            tag_to_point[pt.Name] = tag
        except Exception as e:
            print(f"Warning: Could not find tag {tag}: {e}")
    
    if not points:
        return pd.DataFrame(columns=tags)
    
    # Create PIPointList for bulk operations
    point_list = PIPointList(points)
    
    # Set up time range
    time_range = AFTimeRange(start_time, end_time)
    
    # Configure paging
    paging_config = PIPagingConfiguration(PIPageType.TagCount, 100)
    
    try:
        # Perform bulk retrieval
        recorded_values = point_list.RecordedValues(
            time_range,
            AFBoundaryType.Inside,
            "",
            False,
            paging_config
        )
        
        # Process results into a dictionary of lists first (more efficient)
        data_dict = {tag: [] for tag in tags}
        timestamps_dict = {tag: [] for tag in tags}
        
        for values in recorded_values:
            point_name = values.PIPoint.Name
            original_tag = tag_to_point.get(point_name, point_name)
            
            for event in values:
                timestamps_dict[original_tag].append(strip_timestamp(event.Timestamp))
                try:
                    data_dict[original_tag].append(np.float32(event.Value))
                except (TypeError, ValueError):
                    data_dict[original_tag].append(None)
        
        # Create DataFrame from collected data
        # First, get all unique timestamps
        all_timestamps = set()
        for ts_list in timestamps_dict.values():
            all_timestamps.update(ts_list)
        
        if all_timestamps:
            # Sort timestamps
            sorted_timestamps = sorted(all_timestamps)
            
            # Create DataFrame with all timestamps as index
            df = pd.DataFrame(index=sorted_timestamps, columns=tags)
            
            # Fill in the data
            for tag in tags:
                if timestamps_dict[tag]:
                    tag_series = pd.Series(
                        data_dict[tag], 
                        index=timestamps_dict[tag]
                    )
                    df[tag] = tag_series
            
            return df
        else:
            return pd.DataFrame(columns=tags)
            
    except Exception as e:
        print(f"Error in bulk retrieval, falling back to sequential: {e}")
        # Fall back to original implementation
        return _recorded_vals_sequential(tags, start_time, end_time, server)


def _recorded_vals_sequential(tags, start_time="-30d", end_time="", server='default'):
    """Original sequential implementation as fallback"""
    
    if server != 'default':
        piServer = PIServer.FindPIServer(server)
    else:
        piServer = piServers.DefaultPIServer
        
    if piServer is None:
        piServer = piServers.DefaultPIServer
        
    time_range = AFTimeRange(start_time, end_time)
    
    data = pd.DataFrame(columns=tags)
    
    for tag in tags: 
        pt = PIPoint.FindPIPoint(piServer, tag)
        name = pt.Name.lower()
        
        recorded = pt.RecordedValues(time_range, AFBoundaryType.Inside, "", False)
        
        for event in recorded:
            try:
                data.at[strip_timestamp(event.Timestamp), tag] = np.float32(event.Value)
            except TypeError:
                data.at[strip_timestamp(event.Timestamp), tag] = None
    
    return data


def interp_vals(tags: List[str], 
                start_time: str = "-30d", 
                end_time: str = "", 
                interval: str = '12h', 
                server: str = 'default') -> pd.DataFrame:
    """
    Optimized version using bulk retrieval via PIPointList.
    
    Will return a pandas df of interpolated vals between start and end time, 
    with the given interval
    
    Arguments:  
    tags         :  list or list like
    start_time   :  Time of the first data point. Default: '-30d' (thirty days ago)
    end_time     :  Time of the last data point. Default: '' (empty/current time)
    interval     :  Time between data points. Default: '12h'
    server       :  Name of the PI server to use. Uses the default if none is provided
    """
    
    # Handle empty tag list
    if not tags:
        return pd.DataFrame()
    
    # Get PI Server
    if server != 'default':
        piServer = PIServer.FindPIServer(server)
    else:
        piServer = piServers.DefaultPIServer
        
    if piServer is None:
        piServer = piServers.DefaultPIServer
    
    # Find all PI Points
    points = []
    tag_to_point = {}
    for tag in tags:
        try:
            pt = PIPoint.FindPIPoint(piServer, tag)
            points.append(pt)
            tag_to_point[pt.Name] = tag
        except Exception as e:
            print(f"Warning: Could not find tag {tag}: {e}")
    
    if not points:
        return pd.DataFrame(columns=tags)
    
    # Create PIPointList for bulk operations
    point_list = PIPointList(points)
    
    # Set up time range and span
    time_range = AFTimeRange(start_time, end_time)
    span = AFTimeSpan.Parse(interval)
    
    # Configure paging
    paging_config = PIPagingConfiguration(PIPageType.TagCount, 100)
    
    try:
        # Perform bulk retrieval
        interpolated_values = point_list.InterpolatedValues(
            time_range,
            span,
            "",
            False,
            paging_config
        )
        
        # Process results
        data_dict = {}
        
        for values in interpolated_values:
            point_name = values.PIPoint.Name
            original_tag = tag_to_point.get(point_name, point_name)
            
            timestamps = []
            vals = []
            
            for event in values:
                if str(event.Value) != 'Bad Input':
                    timestamps.append(strip_timestamp(event.Timestamp))
                    vals.append(event.Value)
            
            if timestamps:
                data_dict[original_tag] = pd.Series(vals, index=timestamps)
        
        # Create DataFrame
        if data_dict:
            df = pd.DataFrame(data_dict)
            # Ensure all requested tags are present
            for tag in tags:
                if tag not in df.columns:
                    df[tag] = np.nan
            return df[tags]
        else:
            return pd.DataFrame(columns=tags)
            
    except Exception as e:
        print(f"Error in bulk retrieval, falling back to sequential: {e}")
        # Fall back to original implementation
        return _interp_vals_sequential(tags, start_time, end_time, interval, server)


def _interp_vals_sequential(tags, start_time="-30d", end_time="", interval='12h', server='default'):
    """Original sequential implementation as fallback"""
    
    if server != 'default':
        piServer = PIServer.FindPIServer(server)
    else:
        piServer = piServers.DefaultPIServer
        
    if piServer is None:
        piServer = piServers.DefaultPIServer
    
    time_range = AFTimeRange(start_time, end_time)
    span = AFTimeSpan.Parse(interval)
    
    data = pd.DataFrame(columns=tags)
    
    for tag in tags: 
        pt = PIPoint.FindPIPoint(piServer, tag)
        name = pt.Name.lower()
        
        interpolated = pt.InterpolatedValues(time_range, span, "", False)
        
        for event in interpolated: 
            if str(event.Value) == 'Bad Input':
                None
            else:
                data.at[strip_timestamp(event.Timestamp), tag] = event.Value
    
    return data


def current_vals(tags: List[str], server: str = 'default') -> List[Any]:
    """
    Optimized version using bulk retrieval via PIPointList.
    
    Returns the last recorded values at the time of running the function

    Arguments: 
    tags         :  list or list like
    server       :  Name of the PI server to use. Uses the default if none is provided
    """
    
    # Handle empty tag list
    if not tags:
        return []
    
    # Get PI Server
    if server != 'default':
        piServer = PIServer.FindPIServer(server)
    else:
        piServer = piServers.DefaultPIServer
        
    if piServer is None:
        piServer = piServers.DefaultPIServer
    
    # Find all PI Points
    points = []
    tag_to_point = {}
    valid_tags = []
    
    for tag in tags:
        try:
            pt = PIPoint.FindPIPoint(piServer, tag)
            points.append(pt)
            tag_to_point[pt.Name] = tag
            valid_tags.append(tag)
        except Exception as e:
            print(f"Warning: Could not find tag {tag}: {e}")
    
    if not points:
        return [None] * len(tags)
    
    # Create PIPointList for bulk operations
    point_list = PIPointList(points)
    
    try:
        # Perform bulk retrieval
        current_values = point_list.CurrentValue()
        
        # Create result list maintaining original tag order
        result = []
        value_dict = {}
        
        # Build value dictionary
        for value in current_values:
            point_name = value.PIPoint.Name
            original_tag = tag_to_point.get(point_name, point_name)
            value_dict[original_tag] = value.Value
        
        # Build result list in original order
        for tag in tags:
            result.append(value_dict.get(tag, None))
        
        return result
        
    except Exception as e:
        print(f"Error in bulk retrieval, falling back to sequential: {e}")
        # Fall back to original implementation
        return [PIPoint.FindPIPoint(piServer, tag).CurrentValue().Value for tag in tags]


def batch_aggregated_vals(tags, start_time, end_time, interval, period, increment, 
                         method='Average', verbose=False, save_csv=False, 
                         filename="", return_df=True, server='default'):
    """ 
    Optimized batch retrieval using bulk operations.
    
    Purpose: fetch large averaged data in batches to ease load on server
    function parameter description:
    tags        : list of tags to download
    start_time  : start date time in string format where batch fetch begin
    end_time    : end data time in string format where batch ends
    interval    : period over which to average data e.g. '4H', '2D'
    method      : aggregation method that will be given to aggregated_vals
    period      : time period to define batch size e.g. 'days','months'
    increment   : number of time periods in a batch
    verbose     : verbose output of progress (default = False)
    save_csv    : save progress files. Default is False.
    filename    : name of file without the extension.  Function will add suffix
    return_df   : whether or not to return the data as a pandas dataframe (default=True)
    """
    
    if server != 'default':
        piServer = PIServer.FindPIServer(server)
    else:
        piServer = piServers.DefaultPIServer
        
    if piServer is None:
        piServer = piServers.DefaultPIServer
    
    # Use list to accumulate data instead of DataFrame.append()
    all_data = []
    
    if save_csv:
        filename_suffix = filename + '.csv'
        # Create empty file
        pd.DataFrame().to_csv(filename_suffix, index=False)
    
    start_dt = parser.parse(start_time)
    end_dt = parser.parse(end_time)
    
    if verbose:
        print(f'Collecting data from {start_time} to {end_time} as {interval} averages in batches of {increment} {period}:')
    
    kwargs = {period: increment}
    block_end = start_dt + relativedelta(**kwargs)
    batch_num = 1
    
    while block_end < end_dt:
        if verbose:
            print(f'Collecting batch {batch_num}: {str(start_dt)} to {str(block_end)}')
        
        # Use bulk retrieval
        data = aggregated_vals(tags, str(start_dt), str(block_end), interval, method=method, server=server)
        data.index.names = ['DateTime']
        
        if verbose:
            print(f'  Retrieved {len(data)} records')
        
        if save_csv:
            # Append to CSV file
            data.to_csv(filename_suffix, mode='a', header=(batch_num == 1))
            if verbose:
                print(f'  Progress saved to {filename_suffix}')
        else:
            # Accumulate in memory
            all_data.append(data)
        
        start_dt = block_end
        block_end = start_dt + relativedelta(**kwargs)
        batch_num += 1
    
    # Handle final batch
    if verbose:
        print(f'Collecting final batch: {str(start_dt)} to {str(end_dt)}')
    
    data = aggregated_vals(tags, str(start_dt), str(end_dt), interval, method=method, server=server)
    data.index.names = ['DateTime']
    
    if verbose:
        print(f'  Retrieved {len(data)} records')
        print('Batch fetch completed.')
    
    if save_csv:
        data.to_csv(filename_suffix, mode='a', header=False)
        if verbose:
            print(f'Data saved to {filename_suffix}')
        
        if return_df:
            return pd.read_csv(filename_suffix, index_col=0)
    else:
        all_data.append(data)
        if return_df:
            # Concatenate all data at once
            return pd.concat(all_data, sort=True).astype(float)
    
    return None


def batch_recorded_vals(tags, start_time, end_time, period, increment, 
                       verbose=False, save_csv=False, filename="", 
                       return_df=True, server='default'):
    """ 
    Optimized batch retrieval using bulk operations.
    
    Purpose: fetch large recorded data in batches to ease load on server
    """
    
    if server != 'default':
        piServer = PIServer.FindPIServer(server)
    else:
        piServer = piServers.DefaultPIServer
        
    if piServer is None:
        piServer = piServers.DefaultPIServer
    
    # Use list to accumulate data instead of DataFrame.append()
    all_data = []
    
    if save_csv:
        filename_suffix = filename + '.csv'
        # Create empty file
        pd.DataFrame().to_csv(filename_suffix, index=False)
    
    start_dt = parser.parse(start_time)
    end_dt = parser.parse(end_time)
    
    if verbose:
        print(f'Collecting data from {start_time} to {end_time} in batches of {increment} {period}:')
    
    kwargs = {period: increment}
    block_end = start_dt + relativedelta(**kwargs)
    batch_num = 1
    
    while block_end < end_dt:
        if verbose:
            print(f'Collecting batch {batch_num}: {str(start_dt)} to {str(block_end)}')
        
        # Use bulk retrieval
        data = recorded_vals(tags, str(start_dt), str(block_end), server=server)
        data.index.names = ['DateTime']
        
        if verbose:
            print(f'  Retrieved {len(data)} records')
        
        if save_csv:
            # Append to CSV file
            data.to_csv(filename_suffix, mode='a', header=(batch_num == 1))
            if verbose:
                print(f'  Progress saved to {filename_suffix}')
        else:
            # Accumulate in memory
            all_data.append(data)
        
        start_dt = block_end
        block_end = start_dt + relativedelta(**kwargs)
        batch_num += 1
    
    # Handle final batch
    if verbose:
        print(f'Collecting final batch: {str(start_dt)} to {str(end_dt)}')
    
    data = recorded_vals(tags, str(start_dt), str(end_dt), server=server)
    data.index.names = ['DateTime']
    
    if verbose:
        print(f'  Retrieved {len(data)} records')
        print('Batch fetch completed.')
    
    if save_csv:
        data.to_csv(filename_suffix, mode='a', header=False)
        if verbose:
            print(f'Data saved to {filename_suffix}')
        
        if return_df:
            return pd.read_csv(filename_suffix, index_col=0)
    else:
        all_data.append(data)
        if return_df:
            # Concatenate all data at once
            return pd.concat(all_data, sort=True).astype(float)
    
    return None


def recorded_vals_dict(tags, start_time="-30d", end_time="", server='default'):
    """
    Optimized dictionary version using bulk retrieval.
    
    A dictionary version of the recorded vals function for better efficiency for large amounts of data
    Will return a dictionary of recorded vals between start and end time
    Arguments: 
    tags: list or list like
    """

    if server != 'default':
        piServer = PIServer.FindPIServer(server)
    else:
        piServer = piServers.DefaultPIServer
        
    if piServer is None:
        piServer = piServers.DefaultPIServer
    
    # Find all PI Points
    points = []
    tag_to_point = {}
    for tag in tags:
        try:
            pt = PIPoint.FindPIPoint(piServer, tag)
            points.append(pt)
            tag_to_point[pt.Name] = tag
        except Exception as e:
            print(f"Warning: Could not find tag {tag}: {e}")
    
    if not points:
        return {tag: {} for tag in tags}
    
    # Create PIPointList for bulk operations
    point_list = PIPointList(points)
    
    time_range = AFTimeRange(start_time, end_time)
    
    # Initialize result dictionary
    data = {tag: {} for tag in tags}
    
    # Configure paging
    paging_config = PIPagingConfiguration(PIPageType.TagCount, 100)
    
    try:
        # Perform bulk retrieval
        recorded_values = point_list.RecordedValues(
            time_range,
            AFBoundaryType.Inside,
            "",
            False,
            paging_config
        )
        
        for values in recorded_values:
            point_name = values.PIPoint.Name
            original_tag = tag_to_point.get(point_name, point_name)
            
            for event in values:
                timestamp_str = event.Timestamp.ToString(AFLocaleIndependentFormatProvider())
                data[original_tag][timestamp_str] = str(event.Value)
        
        return data
        
    except Exception as e:
        print(f"Error in bulk retrieval, falling back to sequential: {e}")
        # Fall back to original implementation
        return _recorded_vals_dict_sequential(tags, start_time, end_time, server)


def _recorded_vals_dict_sequential(tags, start_time="-30d", end_time="", server='default'):
    """Original sequential implementation as fallback"""
    
    if server != 'default':
        piServer = PIServer.FindPIServer(server)
    else:
        piServer = piServers.DefaultPIServer
        
    if piServer is None:
        piServer = piServers.DefaultPIServer
        
    time_range = AFTimeRange(start_time, end_time)

    data = {tag : {} for tag in tags}

    for tag in tags: 
        pt = PIPoint.FindPIPoint(piServer, tag)
        name = pt.Name.lower()

        recorded = pt.RecordedValues(time_range, AFBoundaryType.Inside, "", False)

        for event in recorded:
            data[tag][event.Timestamp.ToString(AFLocaleIndependentFormatProvider())] = str(event.Value)

    return data


def batch_recorded_vals_dict(tags, start_time, end_time, period, increment, 
                           verbose=False, save_csv=False, filename="", 
                           return_df=True, server='default'):
    """ 
    Optimized batch dictionary retrieval using bulk operations.
    
    A dictionary version of the batch recorded vals function for better efficiency
    """
     
    if server != 'default':
        piServer = PIServer.FindPIServer(server)
    else:
        piServer = piServers.DefaultPIServer
        
    if piServer is None:
        piServer = piServers.DefaultPIServer
        
    bigdata = {tag : {} for tag in tags}
    start_dt = parser.parse(start_time)
    end_dt = parser.parse(end_time)
    
    if verbose:
        print(f'Collecting data from {start_time} to {end_time} in batches of {increment} {period}:')
    
    kwargs = {period: increment}
    block_end = start_dt + relativedelta(**kwargs)
    batch_num = 1
    
    while block_end < end_dt:
        if verbose:
            print(f'Collecting batch {batch_num}: {str(start_dt)} to {str(block_end)}')
        
        data = recorded_vals_dict(tags, str(start_dt), str(block_end), server=server)
        
        for tag in tags:
            bigdata[tag].update(data[tag])

        if verbose:
            print(f'  Done')
                
        start_dt = block_end
        block_end = start_dt + relativedelta(**kwargs)
        batch_num += 1
    
    # Handle final batch
    if verbose:
        print(f'Collecting final batch: {str(start_dt)} to {str(end_dt)}')
    
    data = recorded_vals_dict(tags, str(start_dt), str(end_dt), server=server)
    
    for tag in tags:
        bigdata[tag].update(data[tag])
    
    if verbose:
        print('Batch fetch completed.')
    
    if save_csv:
        filename_suffix = filename + '.json'
        j = json.dumps(bigdata)
        with open(filename_suffix, 'w') as f:
            f.write(j)
            f.close()

        if verbose:
            print(f'Data saved to {filename_suffix}')
            
    if return_df:
        return bigdata
        
    else: 
        return None
