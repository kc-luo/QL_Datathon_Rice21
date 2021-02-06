from datetime import datetime
from types import SimpleNamespace

####################################################################################
class TDSTick:
####################################################################################


    ################################################################################
    def __init__(self, date, timestamp, datetime, interval, data_dict):
        """

        A class to hold all of the information contained in a tick -- should not be instantiated directly
        
        """ 

        self.date = date
        self.timestamp = timestamp
        self.datetime = datetime
        self.interval = interval

        self.p = SimpleNamespace()

        for product in list(data_dict.keys()):

            tick_data = SimpleNamespace()

            tick_data.open = data_dict[product][timestamp]['open']
            tick_data.close = data_dict[product][timestamp]['close']
            tick_data.high = data_dict[product][timestamp]['high']
            tick_data.low = data_dict[product][timestamp]['low']
            tick_data.volume = data_dict[product][timestamp]['volume']
            setattr(self.p, product.replace('-', '_').lower(), tick_data)

            
####################################################################################
class TDSTickGenerator:
####################################################################################
    
    
    ################################################################################
    def __init__(self, cb_data_obj, products, start_date, end_date, interval):
        """

        Interface to generate tick data

        Parameters: 
        cb_data_obj  (TDSCoinbaseData)  : TDSCoinbaseData obj 
        products     (list)             : list of products to include in a tick
        start_date   (str)              : YYYYMMDD start date
        end_date     (str)              : YYYYMMDD end date
        interval     (int)              : tick size -- can be one of 60, 300, 900, 3600, 21600, 86400
     
        """ 
        self.cb_data_obj = cb_data_obj
        self.products = products
        self.end_date = end_date
        self.interval = interval

        self.setup_date(start_date)


    ################################################################################
    def setup_date(self, date):
        """

        Setup dependant data for ticks on a new date

        Parameters: 
        date  (str)    : date to get data for 
    
        Returns: 
        bool : indication of whether or not date iteration is complete
    
        """ 


        if date > self.end_date:
            return False

        data_dict = {}

        for product in self.products:
            prod_df = self.cb_data_obj.get_single_day_market_data(product, date, self.interval)
            prod_df = prod_df.set_index('timestamp')
            prod_dict = prod_df.to_dict('index')
            data_dict[product] = prod_dict
        
        self.data_dict = data_dict
        self.curr_timestamp = min(list(data_dict[self.products[0]].keys()))
        self.last_timestamp = max(list(data_dict[self.products[0]].keys()))

        self.curr_date = date

        return True
        

    ################################################################################
    def timestamp_to_date(self, timestamp):
        """
        
        Convert timestamp to date

        Parameters: 
        timestamp  (int) : timestamp to convert
    
        Returns: 
        str : YYYYMMDD date

        """ 
        return datetime.utcfromtimestamp(timestamp).strftime('%Y%m%d')


    ################################################################################
    def get_tick(self):
        """
        
        Get the next available tick, if no next availbel tick return None

        Returns: 
        TDSTick : the next available tick

        """ 
        if self.curr_timestamp > self.last_timestamp:
            next_date = self.timestamp_to_date(self.curr_timestamp)
            cont = self.setup_date(next_date)
            if not cont:
                return None
        
        dt = self.data_dict[self.products[0]][self.curr_timestamp]['datetime']
        tick = TDSTick(self.curr_date, self.curr_timestamp, dt, self.interval, self.data_dict)

        self.curr_timestamp += self.interval

        return tick

    