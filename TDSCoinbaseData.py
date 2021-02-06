from datetime import datetime, timedelta, timezone
import requests
import time
import pandas as pd
import logging
import os

try:
    from ipywidgets import IntProgress
    from IPython.display import display
except:
    logging.info("running in non-notebook environment")

####################################################################################
class TDSCoinbaseData:
####################################################################################
    
    API_URL = "https://api.pro.coinbase.com/"
    
    
    ################################################################################
    def __init__(self, cache_path='data', notebook_logging=False):
        """
        
        Interface to retrieve crypto market data

        Parameters: 
        cache_path        (str)  : path to store cached data in
        notebook_logging  (bool) : enable logging in a notebook environment    

        """ 
        
        self.cache_path = cache_path
        self.notebook_logging = notebook_logging
        if not os.path.isdir(self.cache_path):
            os.mkdir(self.cache_path) 
            
    
    ################################################################################
    def save_data(self, df, product, date, interval):
        """
        
        Construct an output path and save to parquet
        
        Parameters: 
        df        (DataFrame)  : df to save
        product   (str)        : product of data
        date      (str)        : date of data
        interval  (int)        : interval of data
    
        Returns: 
        None
        
        """ 
        
        dir_path = os.path.join(self.cache_path, str(interval), date)
        os.makedirs(dir_path, exist_ok=True)
        path = os.path.join(dir_path, f'{product}.parquet')
        df.to_parquet(path)

    
    ################################################################################
    def get_cache_path(self, product, date, interval):
        """
        
        Construct an output path

        Parameters: 
        product   (str)        : product of data
        date      (str)        : date of data
        interval  (int)        : interval of data
    
        Returns: 
        str : output path
        
        """ 
        return os.path.join(self.cache_path, str(interval), date, f'{product}.parquet')
    
    
    ################################################################################
    def get_last_row(self, product, date, interval):
        """
        
        Get the last row of data in a given dataset -- data generation helper function

        Parameters: 
        product   (str)        : product of data
        date      (str)        : date of data
        interval  (int)        : interval of data
    
        Returns: 
        dict : a dict of values in the last row of data
       
        """ 
       
        prev_date = (datetime.strptime(date, "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d")
        df = self.get_single_day_market_data(product, prev_date, interval)
        df_dict = df.set_index('timestamp').to_dict('index')
        max_key = max(list(df_dict.keys()))
        return df_dict[max_key]
    
    
    ################################################################################
    def fill_gaps(self, df, product, date, interval):
        """
        
        Gap fill any missing data -- data generation helper function

        Parameters: 
        df        (DataFrame)  : df to save
        product   (str)        : product of data
        date      (str)        : date of data
        interval  (int)        : interval of data
    
        Returns: 
        DataFrame : a gap filled df
        
        """ 
        
        new_df = df.set_index('timestamp')
        start_dt = datetime(int(date[:4]), int(date[4:6]), int(date[6:8]), tzinfo=timezone.utc)
    
        new_dict = new_df.to_dict('index')
        
        # Fill forward
        prev = None
        for i in range(int((1440 * 60) / interval)):
            curr_dt = start_dt + timedelta(seconds = interval * i)
            curr_timestamp = (int(curr_dt.timestamp()))
            if curr_timestamp not in new_dict:
                if prev is not None:
                    data = {
                        'low' : prev['close'],
                        'high' : prev['close'],
                        'open' : prev['close'],
                        'close' : prev['close'],
                        'volume' : 0,
                        'datetime' : curr_dt,
                        'product' : prev['product'],
                        'date' : prev['date']
                    }
                    new_dict[curr_timestamp] = data
            else:
                prev = new_dict[curr_timestamp]

        # Fill backward
        prev = None
        for j in range(int((1440 * 60) / interval)):
            i = int((1440 * 60) / interval) - 1 - j
            curr_dt = start_dt + timedelta(seconds = interval * i)
            curr_timestamp = (int(curr_dt.timestamp()))
            if curr_timestamp not in new_dict:
                if prev is None:
                    prev = self.get_last_row(product, date, interval)
                if prev is not None:
                    data = {
                        'low' : prev['close'],
                        'high' : prev['close'],
                        'open' : prev['close'],
                        'close' : prev['close'],
                        'volume' : 0,
                        'datetime' : curr_dt,
                        'product' : prev['product'],
                        'date' : date
                    }
                    new_dict[curr_timestamp] = data
            
        adj_df = pd.DataFrame.from_dict(new_dict, orient="index").reset_index().rename(columns={'index' : 'timestamp'}).sort_values('timestamp')
        return adj_df

    
    ################################################################################
    def get_single_day_from_api(self, product, date, interval=60, max_retries=7):
        """
        
        Get single day of market data from coinbase pro api

        Parameters: 
        product      (str)        : product of data
        date         (str)        : date of data
        interval     (int)        : interval of data
        max_retries  (int)        : max number of retries before an error (primarily used when rate limits are hit)
    
        Returns: 
        DataFrame : df of market data
        
        """ 

        start_dt = datetime(int(date[:4]), int(date[4:6]), int(date[6:8]), tzinfo=timezone.utc)
        end_dt = start_dt + timedelta(days=1)
        curr_dt = start_dt - timedelta(seconds=interval)
        dfs = [] 

        # read data in chunks -- coinbase pro returns at most 300 records per request
        while curr_dt < end_dt:
            start_iso = curr_dt.isoformat()
            end_iso = (curr_dt + timedelta(seconds=interval * 300)).isoformat()
            # 5 message overlap for safety
            curr_dt += timedelta(seconds=interval * 295)
            
            params = {
                'start' : start_iso,
                'end'   : end_iso,
                'granularity' : interval,
            }


            data = requests.get(self.API_URL + f"products/{product}/candles", params=params)

            # retur get up to 7 times
            retry_count = 0
            while data.status_code != 200:
                if retry_count >= max_retries:
                    raise Exception('MAX RETRIES EXCEEDED')
                retry_count += 1
                logging.warning(f'Rate limit exceeded -- retrying query ({start_iso}-{end_iso}, {product} {interval}) retry number {retry_count}/{max_retries}')
                time.sleep(0.15)
                data = requests.get(self.API_URL + f"products/{product}/candles", params=params)

            # convert to dateftame
            df = (pd.DataFrame.from_records(data.json(), columns=['timestamp', 'low', 'high', 'open', 'close', 'volume']))
            dfs.append(df)

        # get unique records
        big_df = pd.concat(dfs, ignore_index=True).groupby('timestamp').first().reset_index()
        # create datetime field
        big_df['datetime'] = pd.to_datetime(big_df['timestamp'], unit='s', utc=True)
        # trim boundaries
        big_df = big_df[big_df['datetime'] < end_dt].sort_values('datetime')
        big_df = big_df[big_df['datetime'] >= start_dt].sort_values('datetime')
        # add additional fields
        big_df['product'] = product
        big_df['date'] = date
        
        # fill gaps
        big_df = self.fill_gaps(big_df, product, date, interval)

        # save data
        self.save_data(big_df, product, date, interval)

        return big_df


    ################################################################################
    def get_single_day_market_data(self, product, date, interval):
        """
        
        Get single day of market data from cache if exists, otherwise, pull form coinbase pro

        Parameters: 
        product      (str)        : product of data
        date         (str)        : date of data
        interval     (int)        : interval of data
    
        Returns: 
        DataFrame : df of market data
        
        """ 


        cache_path = self.get_cache_path(product, date, interval)
        df = None
        # if cached data exists, return cached data
        if os.path.isfile(cache_path):
            df = pd.read_parquet(cache_path)
        # otherwise fetch data from the coinbase pro api
        else:
            df = self.get_single_day_from_api(product, date, interval)
        
        df['datetime'] = pd.to_datetime(df['datetime'], utc=True)
        return df


    ################################################################################
    def get_market_data(self, product, start_date, end_date, interval=60, overwrite=False):
        """
        
        Get market data over a range of dates

        Parameters: 
        product      (str)        : product of data
        start_date         (str)        : date of data
        end_date         (str)        : date of data
        interval     (int)        : interval of data
        overwrite     (bool)        : overwrite cached data
    
        Returns: 
        DataFrame : df of market data across the given time period
        
        """ 
        
        start_dt = datetime(int(start_date[:4]), int(start_date[4:6]), int(start_date[6:8]))
        end_dt = datetime(int(end_date[:4]), int(end_date[4:6]), int(end_date[6:8]))

        if self.notebook_logging:
            start_time = time.time()
            delta = end_dt - start_dt
            total_days = delta.days + 1
            print(f'Getting {product} data from {start_date} to {end_date} at {interval}s granularity')
            f = IntProgress(min=0, max=total_days, description = 'Progress', bar_style='info')
            display(f)
        
        dfs = []

        # iterate and get daily data
        while start_dt <= end_dt:
            date_str = start_dt.strftime('%Y%m%d')
            if overwrite:
                dfs.append(self.get_single_day_from_api(product, date_str, interval))  
            else:
                dfs.append(self.get_single_day_market_data(product, date_str, interval))  
            start_dt += timedelta(days=1)
            if self.notebook_logging:
                f.value += 1
            
        if self.notebook_logging:
            f.bar_style = 'success'
            print(f'Completed in {round(time.time() - start_time, 2)} seconds')
       
        return pd.concat(dfs, ignore_index=True)
       
