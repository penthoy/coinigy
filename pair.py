# Currency pair aaa
import logging
import numpy as np
import pandas as pd

class FXPair():
    def __init__(self, base, quote, exchmkt_id, exchange,
                 currentPrice = None, askBookDepth = 5, bidBookDepth = 5, orderHistoryDepth = 50):
        self.logger = logging.getLogger('FXPair')
        #self.logger.disabled = True
        self.base = base
        self.quote = quote
        self.exchmkt_id = exchmkt_id
        self.exchange = exchange
        self.currentFX = currentPrice
        self.askbookDepth = askBookDepth
        self.bidBookDepth = bidBookDepth
        self.orderHistoryDepth = orderHistoryDepth  # history
        self.tradeHistory = pd.DataFrame()
        self.asks = pd.DataFrame()
        self.bids = pd.DataFrame()


    #Trade event handler
    def tradeEventHandler(self, channel, *args):
        self.logger.info("PAIR %s/%s TRADE EVENT HANDLER %s with %d arguments" % (self.base, self.quote, channel, len(args)))
        if len(args) != 1:
            return
        d = args[0]
        #self.logger.info(d)
        #create a data frame row
        list = [{
            #"time_local" : d["timestamp"],
            "price" : d["price"],
            "quantity" : d["quantity"],
            "type" : d["type"],
            "base_ccy" : self.base,
            "counter_ccy" : self.quote
                 }]
        newRow = pd.DataFrame(list, index=[ pd.to_datetime(d["timestamp"])])
        self.tradeHistory = self.tradeHistory.append(newRow)
        self.tradeHistory.index.name = "time_local"
        self.tradeHistory.sort_index(inplace=True, ascending=False)
        self.tradeHistory = self.tradeHistory.head(self.orderHistoryDepth) # keep only first required values
        self.setCurrentFX(self.tradeHistory.ix[0]["price"]) # set current price - the latest price
        self.logger.info(self.tradeHistory)
        # notify exchange of the update
        self.exchange.tradeHandler(self)

    # exchange event handler: ORDER,
    def orderEventHandler(self, channel, *args):
        self.logger.info("PAIR EVENT HANDLER %s with %d arguments" % (channel,len(args)))
        if len(args) != 1:
            return
        # cast data types

        d = args[0]
        dat = pd.DataFrame.from_records(d)
        if dat.empty:
            return # nothing to process
        if 'price' in dat.columns:
            dat.price = dat.price.astype(np.float)
        if 'quantity' in dat.columns:
            dat.quantity = dat.quantity.astype(np.float)
        if 'total' in dat.columns:
            dat.total = dat.total.astype(np.float)
        if 'time_local' in dat.columns:
            dat.time_local = pd.to_datetime(dat.time_local)
            dat.set_index('time_local', inplace=True)
        if 'type' in dat.columns:
            dat.type = dat.type.astype(str)
        if not dat.empty:
            pass

        try:
            asks = dat.loc[dat['ordertype'] == "Sell"] \
                .drop(labels=["ordertype"], axis=1) \
                .sort_values(by="price", ascending=False)
            self.updateAskBook(asks)
        except:
            pass

        try:
            bids = dat.loc[dat['ordertype'] == "Buy"] \
                .drop(labels=["ordertype"], axis=1) \
                .sort_values(by="price", ascending=False)
            self.updateBidBook(bids)
        except:
            pass

        #notify exchange of the update
        self.exchange.orderHandler(self)

    # update asks book
    def updateAskBook(self, askDataFrame):
        '''
        ASK DATAFRAME FORMAT
        INFO:    price    quantity      total
        0       36360.0   0.13400       4872.240
        1       36300.0   1.00000       36300.000
        '''
        if not askDataFrame.empty:
            self.asks = askDataFrame.head(self.askbookDepth)
            self.logger.info("ASKS AFTER UPDATE")
            self.logger.info(self.asks)

    # update bids data
    def updateBidBook(self, bidDataFrame):
        # UPDATE BID BOOK
        if not bidDataFrame.empty:
            self.bids = bidDataFrame.head(self.bidBookDepth)
            self.logger.info("BIDS AFTER UPDATE")
            self.logger.info(self.bids)

    # set current price
    def setCurrentFX(self, fx):
        self.currentFX = fx

    def getCurrentFX(self):
        return self.currentFX

    def getBase(self):
        return self.base

    def getQuote(self):
        return self.quote

    def getPairCode(self):
        return self.getBase() + "/" + self.getQuote()

    #request ask book from the server
    def requestAskBook(self):
        self.exchange.requestAskBook(self)

    #request bid book from the server
    def requestBidBook(self):
        self.exchange.requestBidBook(self)

    def addTradingHistory(self, trades):
        pass

    def getAverageAskPrice(self, amt):
        self.logger.info("Get average ASK price for %d " % amt)
        self.logger.info(self.asks)
        if not self.isAskAvailable():
            #self.logger.info(self)
            self.requestAskBook() # request new data
            if not self.isAskAvailable():
                self.logger.debug("ASK info is not available for %s " % self.getPairCode())
                raise # no ask information yet available
        # find how deep need to go to fulfill required qnt
        a = ((self.asks['quantity']*self.asks['price']).cumsum() <= amt) # boolean vector - True : this price will be used
        a[0] = True # don't skip first row (when can fulfill the order from the first row)
        # calculate average price for the given qnt
        p = ((self.asks["quantity"]*self.asks["price"])[a].cumsum() / self.asks["quantity"][a].cumsum())[0]
        return p


    def getAverageBidPrice(self, amt):
        '''
        Get the average price for the given qnt
        BIDS DATAFRAME FORMAR
        INFO:  exchange       label       price         quantity            timestamp        total
        0     GATE          BTC/HKD     33951.1000       0.380      2017-08-25 12:54:38     12901.41800
        1     GATE          BTC/HKD     33951.0000       0.300      2017-08-25 12:54:38     10185.30000
        :param amt:
        :return:
        '''
        self.logger.info("Get average BID price for %d " % amt)
        self.logger.info(self.bids)
        if not self.isBidAvailable():
            self.logger.info("@@ Manual Bid book request for %s" % self.getPairCode())
            self.requestBidBook()
            if not self.isBidAvailable():
                self.logger.debug("BID info is not available for %s " % self.getPairCode())
                raise # no bid information yet available
        # find how deep need to go to fulfill required qnt
        a = ((self.bids['quantity'] * self.bids['price']).cumsum() <= amt) # boolean vector - True : this price will be used
        a[0] = True # don't skip first row (when can fulfill the order from the first row)
        # calculate average price for the given qnt
        p = ((self.bids["quantity"]*self.bids["price"])[a].cumsum() / self.bids["quantity"][a].cumsum())[0]
        return p

    #is bid price available?
    def isBidAvailable(self):
        return not self.bids.empty

    #is ask price available?
    def isAskAvailable(self):
        return not self.asks.empty

    # synonym names
    def isBitcoin(self, currency_name):
        return currency_name == "BTC" or currency_name == "XBT"

    # Return value of 1 BTC in Quote currency
    def get1BTCinQuote(self): # to remove
        if self.isBitcoin(self.getQuote()):
            return 1 # ETH / BTC
        elif self.isBitcoin(self.getBase()):
            return self.getCurrentFX() # BTC / HKD
        else: return 1 # TBC

    def getAskBookDepth(self):
        pass

    def getBidBookDepth(self):
        pass

