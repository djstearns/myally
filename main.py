#!/usr/bin/python3.8
#pip install ratelimit
#pip install statsmodels

#7 PM is python anywhere's midnight CST DST
### #!/usr/bin/python3.8

#!/home/djstearns/.virtualenvs/allyenv/bin/python

import requests
import json
import pandas as pd
from ratelimit import limits, sleep_and_retry
import datetime

import config as cfg

import plotly.express as px
from statsmodels.tsa.api import ExponentialSmoothing

import plotly.graph_objects as go

#strategy values:
mover_opts = ['ally','alphavantage','fmp']

#if its ally: default is volume
ally_opts = ['toplosers','toppctlosers','topvolume','topactive','topgainers','toppctgainers']

#select the number of days to predict each desired symbol
pred_freq = [10,15,30,60,90]

#how often should predictions be made?
des_pred_freq_opt = ['D','W','M','Y']


myacct = {}
#['symbol', 'date','amt','action'=['buy'/'sell']]

def get_ally(opt):

    opts = ['toplosers','toppctlosers','topvolume','topactive','topgainers','toppctgainers']

    if opt == '':
        opt = 'topvolume'

    if opt not in opts:
        return 'error'

    consumer_key = cfg.ally_config['consumer_key']
    consumer_secret=cfg.ally_config['consumer_secret']
    oauth_token=cfg.ally_config['oauth_token']
    oauth_token_secret=cfg.ally_config['oauth_token_secret']

    test = OAuth1Session(consumer_key,
              client_secret=consumer_secret,
              resource_owner_key=oauth_token,
              resource_owner_secret=oauth_token_secret)
    url = 'https://devapi.invest.ally.com/v1/market/toplists/'+opt+'.json'
    r = test.get(url)
    data = r.json()

    return data

#strategy select
#def get_alpha():
    #alphavantage.co API Key
    #return None


#input: list of symbols
#input: function [ 'TIME_SERIES_WEEKLY']
#input: use ['open','high',low','close','vol']
def get_time_series(symbols, fg = False):
    ts = {}
    key = cfg.alpha_config['key']
    for s in symbols:
        print('attempt:'+s)

        url = 'https://www.alphavantage.co/query?function=TIME_SERIES_WEEKLY&symbol='+s+'&apikey='+key
        data = call_api(url)

        if data == []:
            continue
        else:
            if 'Weekly Time Series' in data:
                dat = pd.DataFrame.from_dict(data['Weekly Time Series'], orient='index')
                dat.columns = ['open','high','low','close','vol']
                #dat.head()

                dat['close'] = dat['close'].astype(float)
                dat['DATE'] = pd.to_datetime(dat.index)

                dat_new = dat.set_index('DATE').resample('1D').ffill().reset_index()
                ts[s] = dat_new
                if fg == True:
                    fig = px.line(dat, x='DATE', y='close')
                    fig.show()
            else:
                print('skipped, no weekly series data?')
                print(data)

    return ts

TIME_PERIOD = 12   # time period in seconds

@sleep_and_retry
@limits(calls=1, period=TIME_PERIOD)
def call_api(url):
    response = requests.get(url)

    if response.status_code != 200:
        raise Exception('API response: {}'.format(response.status_code))

    data = response.json()
    if 'Error Message' in data:
        #error with symbol
        #raise Exception('API Symbol error{}'.format(url))
        data = []
    return data


def get_fmp():
    #https://site.financialmodelingprep.com/developer/docs/dashboard
    fmp_key = cfg.financial_prep_config['fmp_key']
    losers= requests.get('https://financialmodelingprep.com/api/v3/stock_market/losers?apikey='+fmp_key)
    gainers = requests.get('https://financialmodelingprep.com/api/v3/stock_market/gainers?apikey='+fmp_key)
    active = requests.get('https://financialmodelingprep.com/api/v3/stock_market/actives?apikey='+fmp_key)
    flosers = []
    losers1 = json.loads(losers.content)
    for l in losers1:
        flosers.append(l['symbol'])
        #print(l['symbol'])

    fgainers = []
    gainers1 = json.loads(gainers.content)
    for l in gainers1:
        fgainers.append(l['symbol'])
        #print(l['symbol'])

    factives = []
    active1 = json.loads(active.content)
    for l in active1:
        factives.append(l['symbol'])
        #print(l['symbol'])

    final = fgainers
    return final


#ts time series objects
#format of ts should be {symbol:[index:date,value]}
#fig (T/F): show figures

#THIS IS DRAFT 1

#ats = actual time series
#smooth = modelled time series
#main_forecasts: main dictionary for exporting symbols
def create_preds(ts, fg = False):
    pred_freq = [10,15,20,30,60,90]

    main_forecasts = {}

    #for graphing
    f = {}
    a = {}
    s = {}

    #loop through symbol time series:
    for t in ts:
        print(t)
        #regulate close data
        ats = ts[t]['close']
        ats.index = ts[t].DATE
        ats = ats.asfreq('D')

        #model Timeseries
        try:
            smooth = ExponentialSmoothing(
                ats,
                trend="add",
                use_boxcox=True,
                initialization_method="estimated",
            ).fit()
        except:
            print("Error smoothing: "+t)
        else:
            #change to include predictions as s['symbol']['90 days']
            #loop each number of days' predictions in each symbol
            for pf in pred_freq:
                forecasts = smooth.forecast(pf)
                #check for symbol
                if t not in main_forecasts:
                    main_forecasts[t] = {}

                #measure if the change was positve
                chg = forecasts[-1] - forecasts[1]

                #print('chg > 0 for '+str(pf)+' day forecast for '+t)
                if chg > 0:
                    main_forecasts[t][pf] = forecasts[-1]

                #only graph 90 day forecasts
                if pf == 90:
                    s[t] = smooth
                    a[t] = ats
                    f[t] = forecasts

    #format output to symbol by row, date by column
    tbl = pd.DataFrame.from_dict(main_forecasts)
    tbl = tbl.dropna(axis=1)

    new_cols = []
    today = datetime.datetime.today()
    tdy = today.strftime("%Y-%m-%d")

    for c in tbl.index:
        new_cols.append(str(pd.to_datetime(tdy) + datetime.timedelta(days=c)))
    tbl.index=new_cols

    tbl = tbl.T
    tbl['pred_dte'] = today.strftime("%Y-%m-%d")
    #export prediction
    tbl.to_csv('preds'+today.strftime("%Y-%m-%d")+'.csv')

    #load previous preds
    cur_pred = pd.read_csv('preds.csv', index_col=0)

    all_pred = pd.concat([tbl, cur_pred], axis=0)

    #export new all prediction
    all_pred.to_csv('preds.csv')

    #loop through forecasts to see which ones are positive slope
    # date_1 = datetime.datetime.today()
    # prediction_dates[date_1] = f[i].index[-1:][0]

    #loop through final forecasts
    for i in f:
        print(i)
        #predictions[f[i].index[-1:][0]] = []

        #print(f[i].index[-1:][0])
        #subtract the last value from the first moment to get slope
        chg = f[i][-1] - f[i][1]
        print(chg)
        if chg > 0:
            #predictions[f[i].index[-1:][0]].append(i)

            smoothData = pd.DataFrame([a[i].values, s[i].fittedvalues.values]).T
            smoothData.columns = ['Truth','smooth']
            smoothData.index = a[i].index
            if fg == True:
                fig = generate_fig(smoothData, f)
                fig.show()

# modelfitted values: aka smoothData
# forecasted values: aka f
def generate_fig(smoothData, f):
    fig = px.line(smoothData, y = ['Truth','smooth'],
            x = smoothData.index,
            color_discrete_map={"Truth": 'blue',
                                "holt":'red',
                              }
           )
    idx_len = len(smoothData.index)*-1
    fig.update_xaxes(range=[smoothData.index[idx_len], f[i].index[-1]])
    fig.update_yaxes(range=[0, f[i][-1]+(.1*f[i][-1])])

    # Incorporating the Forecasts
    fig.add_trace(go.Scatter(x=f[i].index, y = f[i].values, name='holt', line = {'color':'green'}))
    #fig.add_trace(go.Scatter(x=forecast020.index, y = forecast020.values, name='Forecast alpha=0.2', line={'color':'red'}))
    #fig.add_trace(go.Scatter(x=forecast050.index, y = forecast050.values, name='Forecast alpha=0.5', line={'color':'green'}))
    #fig.add_trace(go.Scatter(x=forecast080.index, y = forecast080.values, name='Forecast alpha=0.8', line={'color':'purple'}))

    #fig.write_html('figure.html')
    fig.show()


################ EXECUTE
#main
symbols = get_fmp()
ts = get_time_series(symbols, fg=False)
create_preds(ts)