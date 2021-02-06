# QL_Datathon_Rice21 -- Make-A-Trade
Repo for Rice 2021 Datathon QuantLab Challenge

Prediction
    Our program predicts the trade value of next tick using AROMA as prediction model. In the tick-and-trade loop, we first reference to previous market trade data, including usd-btc, eth-btc from the previous 24 hours; and then we feed the data into VAROMA to get the predicted mean and confidence intervals.
Business 
    Trade
        Based on the predicted data, our program calculates the probability of profiting from the next tick and choose the most feasible investment plan.
    Arbitrage
        Based on the current tick data, our program exanges our holdsing from one cureency to another multiple times if the exchange ratio between multiple currency can bring us profits.
