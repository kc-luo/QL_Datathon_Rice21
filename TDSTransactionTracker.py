from datetime import datetime, timedelta, timezone
import requests
import time
import pandas as pd
import logging
import os
import json
import plotly.express as px
from TDSCoinbaseData import TDSCoinbaseData
from TDSTickGenerator import TDSTickGenerator

try:
    from ipywidgets import IntProgress
    from IPython.display import display
except:
    logging.info("running in non-notebook environment")

####################################################################################
class TDSTransactionTracker:
####################################################################################
    
    BLOCKFI_LENDING_RATE = 0.06
    
    ################################################################################
    def __init__(self, start_date, end_date, holdings, max_taken_vol=0.5, fee_rate=0.0018):
        """

        Interface to make and track trades

        Parameters: 
        start_date     (str)    : YYYYMMDD start date 
        end_date       (str)    : YYYYMMDD end date
        holdings       (dict)   : initial holdings dict
        max_taken_vol  (float)  : Max pct of volume that can be taken in a given tick
        fee_rate       (float)  : Fee rate per transaction
    
        """ 
        self.start_date = start_date
        self.end_date = end_date
        self.trades = []
        self.holdings = holdings
        self.max_taken_vol = max_taken_vol
        self.fee_rate = fee_rate
        self.initial_holdings = self.holdings.copy()

    ################################################################################
    def get_holdings(self):
        """ 

        Retrieve the current holding dictionary. 
    
        Returns: 
        dict: current holdings 
    
        """ 
        return self.holdings
        
    ################################################################################
    def get_trades(self):
        """

        Retrieve the current trade history 
    
        Returns: 
        list: list of current trade history 
    
        """ 
        return self.trades
    
    ################################################################################
    def get_max_taken_volume(self):
        """

        Retrieve the max taken volume (max pct of volume that can be taken in a single tick)
    
        Returns: 
        float: max take volume 
    
        """ 
        return self.max_taken_vol
    
    ################################################################################
    def make_trade(self, tick, product, side, size):
        """

        Attempt to make a trade. Error if attempted trade is invalid, otherwise return the trade record

        Parameters: 
        tick    (TDSTick)  : current tick 
        product (str)      : '<BASE>-<QUOTE>' 
        side    (str)      : 'buy' or 'sell'
        size    (float)    : Amount of HELD currency to trade 
    
        Returns: 
        dict: record of the single trade 
    
        """ 

        side = side.lower()
        liq_instr = None
        aq_instr = None

        base = product.split('-')[0]
        quote = product.split('-')[1]

        if side.lower() == 'sell':
            liq_instr = base
            aq_instr = quote
        elif side.lower() == 'buy':
            liq_instr = quote
            aq_instr = base
        else:
            # check if side is invalid
            raise Exception(f'INVALID SIDE : {side}')

        size_to_liq = size
        if liq_instr not in self.holdings:
            # ensure holding enough funds to execute
            raise Exception(f'INSIFFICIENT FUNDS : Not holding any {liq_instr}')
    
        if size < 0:
            # liquidate entire position
            size_to_liq = self.holdings[liq_instr]
        
        if size_to_liq > self.holdings[liq_instr]:
            # ensure holding enough funds to execute
            raise Exception(f'INSUFFICIENT FUNDS : attempted to liquidate {size_to_liq} {liq_instr} only holding {self.holdings[liq_instr]} {liq_instr}')
        

        product_info = getattr(tick.p, product.lower().replace('-', '_'))

        available_volume = product_info.volume * self.max_taken_vol

        volume_moving = size_to_liq
        if side.lower() == 'buy':
            volume_moving = size_to_liq / product_info.high
        
        if available_volume < volume_moving:
            # ensure enough market volume to execute trade
            raise Exception(f'INSUFFICIENT MARKET VOLUME : attempting to move {volume_moving} {base} only {available_volume} {base} available')

        self.holdings[liq_instr] -= size_to_liq

        size_to_liq -= self.fee_rate * size_to_liq

        conv_volume = None
        exec_price = None

        # execute at the close price
        if side.lower() == 'buy':
            exec_price = product_info.close
            conv_volume = size_to_liq / exec_price
        elif side.lower() == 'sell':
            exec_price = product_info.close
            conv_volume = size_to_liq * exec_price

        # adjust holdings
        if aq_instr not in self.holdings:
            self.holdings[aq_instr] = 0
        

        self.holdings[aq_instr] += conv_volume

        # create the trade record
        trade = {
            'date'      : tick.date,
            'timestamp' : tick.timestamp,
            'side'      : side,
            'size'      : volume_moving,
            'price'     : exec_price,
            'product'   : product,
            'holdings'  : self.holdings.copy(),
         }

        self.trades.append(trade)
        return trade


    
    ################################################################################
    def dump_trades(self, filepath):
        """

        Save all trades to a json

        Parameters: 
        filepath (str) : filepath to output trades to
    
        Returns: 
        None
    
        """ 
        with open(filepath, 'w') as outfile:
            json.dump(self.trades, outfile)
        
    
    ################################################################################
    def get_btc_holdings(self, holdings, date):
        """

        Translate the current holdings to EOD btc. Should only be used internally as a helper function.

        Parameters: 
        holdings (dict) : holdingsn dict
        date     (str)  : YYYYMMDD
    
        Returns: 
        float : btc value
    
        """ 

        # traverse shortest path to BTC
        # EX. ETH->USD->BTC

        necessary_products = []
        holdings_copy = holdings.copy()
        for key in holdings_copy.keys():
            if key in ['USD', 'GBP', 'EUR']:
                necessary_products.append(f"BTC-{key}")
            else:
                necessary_products.append(f"{key}-USD")
        
        necessary_products = list(set(necessary_products))
        cb_obj = TDSCoinbaseData(cache_path='data')
        tick_gen = TDSTickGenerator(cb_obj, necessary_products, date, date, interval=86400)
        tick = tick_gen.get_tick()

        total_btc = 0.0

        for key in holdings_copy.keys():
            if key in ['USD', 'GBP', 'EUR']:
                product_info = getattr(tick.p, f'BTC_{key}'.lower())
                btc_holdings = holdings_copy[key] / product_info.close
            elif key == 'BTC':
                btc_holdings = holdings_copy[key]
            else:
                product_info = getattr(tick.p, f'{key}_USD'.lower())
                usd_info = getattr(tick.p, f'BTC_USD'.lower())

                usd_holdings = holdings_copy[key] * product_info.close
                btc_holdings = usd_holdings / usd_info.close
            total_btc += btc_holdings

        return total_btc

    

    ###############################################################################
    def get_holdings_for_date(self, date):
        """

        Get holdings for a certain date -- computed at EOD prices

        Parameters: 
        date     (str)  : YYYYMMDD
    
        Returns: 
        float : btc value
    
        """ 
        holdings = self.initial_holdings

        for trade in self.trades:
            if trade['date'] <= date:
                holdings = trade['holdings']
        
        return holdings


    ################################################################################
    def get_btc_holdings_over_time(self):
        """

        Get daily BTC holdings as a df
        
        Returns: 
        DataFrame  : df of daily BTC holdings
    
        """ 

        start_dt = datetime(int(self.start_date[:4]), int(self.start_date[4:6]), int(self.start_date[6:8]))
        end_dt = datetime(int(self.end_date[:4]), int(self.end_date[4:6]), int(self.end_date[6:8]))

        holdings_dict = {}

        while start_dt <= end_dt:
            date_str = start_dt.strftime('%Y%m%d')
            holdings = self.get_holdings_for_date(date_str)
            holdings_dict[date_str] = self.get_btc_holdings(holdings, date_str)
            start_dt += timedelta(days=1)

        dates = []
        holdings = []

        for key in holdings_dict.keys():
            dates.append(key)
            holdings.append(holdings_dict[key])
        
        df = pd.DataFrame.from_dict({'date' : dates, 'BTC' : holdings}).sort_values('date')
        return df
            
    ################################################################################
    def plot_btc_holdings(self):
        """

        Plot daily BTC holdings using plotly
        
        Returns: 
        None 

        """ 
        df = self.get_btc_holdings_over_time()
        fig = px.line(df, x="date", y="BTC", title=f'BTC from {self.start_date} to {self.end_date}')
        fig.show()
        
   
    ################################################################################
    def get_pct_change_per_day(self):
        """

        Get daily BTC holdings with day over day pct change as a df
        
        Returns: 
        DataFrame  : df of daily BTC holdings
    
        """ 

        initial_holding = self.get_btc_holdings(self.initial_holdings, self.start_date)
        df = self.get_btc_holdings_over_time()
        first = df['BTC'].values[0]

        df['pct_diff'] = df['BTC'].pct_change().fillna((first - initial_holding) / initial_holding)
        return df
    
    ################################################################################
    def get_sharpe_ratio(self):
        """

        Get Sharpe Ratio
        
        Returns: 
        float  : sharpe ratio over the period
    
        """ 
        daily_rate = self.BLOCKFI_LENDING_RATE / 365
        df = self.get_pct_change_per_day()
        excess_return_std = df['pct_diff'].std()
        actual_return = df['pct_diff'].mean()

        print('RISK FREE DAILY RETURN : ')
        print(daily_rate)
        print('ACTUAL DAILY RETURN : ')
        print(actual_return)
        print('EXCESS STD : ')
        print(excess_return_std)

        return (actual_return - daily_rate) / excess_return_std





    