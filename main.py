import StringIO
import json
import logging
import random
import urllib
import urllib2
import time
import math
import re

import requests
import requests_toolbelt.adapters.appengine
# Use the App Engine Requests adapter. This makes sure that Requests uses
# URLFetch.
requests_toolbelt.adapters.appengine.monkeypatch()

# sending images
try:
    from PIL import Image
except:
    pass
import multipart

# standard app engineimports
from google.appengine.api import urlfetch
from google.appengine.ext import deferred
from google.appengine.ext import ndb
from google.appengine.api.taskqueue import TaskRetryOptions
import webapp2

TOKEN = '363749995:AAEMaasMVLSPqSuSr1MiEFcgQH_Yn88hlbg'

BASE_URL = 'https://api.telegram.org/bot' + TOKEN + '/'

urlfetch.set_default_fetch_deadline(60)

ALERTS = set()


def deffered_track_pair_price(pair, current_price, target_price, chat_id, message_id):
    alert_key = (pair, target_price)
    logging.info("Checking price alert..{} if {}".format(pair, target_price))
    kraken = KrakenExchange()
    ticker = kraken.getTicker(pair=ASSETPAIRS[pair])
    askPrice = float(ticker['Ask Price'][0])
    bidPrice = float(ticker['Bid Price'][0])
    live_price = (askPrice + bidPrice) / 2
    target_price = float(target_price)
    if current_price < target_price and live_price >= target_price:
        ALERTS.remove(alert_key)
        reply_message(
            chat_id=chat_id,
            message_id=message_id,
            msg="{} just hit {}!".format(
                pair, live_price
            )
        )
    elif current_price > target_price and live_price <= target_price:
        ALERTS.remove(alert_key)
        reply_message(
            chat_id=chat_id,
            message_id=message_id,
            msg="{} just hit {}!".format(
                pair, live_price
            )
        )
    else:
        raise Exception("Alert not hit, fail task so it is retried")


def track_pair_price(pair, current_price, target_price, chat_id, message_id):
    ALERTS.add(
        (pair, target_price)
    )

    deferred.defer(
        deffered_track_pair_price,
        pair, current_price, target_price, chat_id, message_id,
        _retry_options=TaskRetryOptions(
            min_backoff_seconds=60,
            task_age_limit=86400
        ) # 1 day
    )


# ================================

class EnableStatus(ndb.Model):
    # key name: str(chat_id)
    enabled = ndb.BooleanProperty(indexed=False, default=False)


# ================================

def setEnabled(chat_id, yes):
    es = EnableStatus.get_or_insert(str(chat_id))
    es.enabled = yes
    es.put()

def getEnabled(chat_id):
    es = EnableStatus.get_by_id(str(chat_id))
    if es:
        return es.enabled
    return False


# ================================

class MeHandler(webapp2.RequestHandler):
    def get(self):
        urlfetch.set_default_fetch_deadline(60)
        self.response.write(json.dumps(json.load(urllib2.urlopen(BASE_URL + 'getMe'))))


class GetUpdatesHandler(webapp2.RequestHandler):
    def get(self):
        urlfetch.set_default_fetch_deadline(60)
        self.response.write(json.dumps(json.load(urllib2.urlopen(BASE_URL + 'getUpdates'))))


class SetWebhookHandler(webapp2.RequestHandler):
    def get(self):
        urlfetch.set_default_fetch_deadline(60)
        url = self.request.get('url')
        if url:
            self.response.write(json.dumps(json.load(urllib2.urlopen(BASE_URL + 'setWebhook', urllib.urlencode({'url': url})))))


def reply_message(chat_id, message_id, msg=None, img=None):
    if msg:
        resp = urllib2.urlopen(BASE_URL + 'sendMessage', urllib.urlencode({
            'chat_id': str(chat_id),
            'text': msg.encode('utf-8'),
            'disable_web_page_preview': 'true',
            'reply_to_message_id': str(message_id),
            'parse_mode': 'Markdown'
        })).read()
    elif img:
        resp = multipart.post_multipart(BASE_URL + 'sendPhoto', [
            ('chat_id', str(chat_id)),
            ('reply_to_message_id', str(message_id)),
        ], [
            ('photo', 'image.jpg', img),
        ])
    else:
        logging.error('no msg or img specified')
        resp = None

    logging.info('send response:')
    logging.info(resp)


class WebhookHandler(webapp2.RequestHandler):
    def post(self):
        urlfetch.set_default_fetch_deadline(60)
        body = json.loads(self.request.body)
        logging.info('request body:')
        logging.info(body)
        self.response.write(json.dumps(body))

        update_id = body['update_id']
        try:
            message = body['message']
        except:
            message = body['edited_message']
        message_id = message.get('message_id')
        date = message.get('date')
        text = message.get('text')
        fr = message.get('from')
        chat = message['chat']
        chat_id = chat['id']

        def reply(msg=None, img=None):
            reply_message(msg=msg, img=img, chat_id=chat_id, message_id=message_id)

        if not text:
            logging.info('no text')
            return

        if text.startswith('/'):
            text = re.sub('(\/btc)', '/xbt', text)
            text = re.sub('(btc$)', 'xbt', text)
            text = re.sub('(btc\s+)', 'xbt ', text)
            if text == '/start':
                reply('Bot enabled')
                setEnabled(chat_id, True)
            if text == '/alerts':
                reply(
                    "*Alerts*\n{}".format(
                        "\n".join([
                            "{}: {}".format(pair, price)
                            for pair, price in ALERTS
                        ])
                    )
                )

            elif text == '/stop':
                reply('Bot disabled')
                setEnabled(chat_id, False)
            elif text == '/rules':
                reply('1. You do not talk about WHALE HUNTERS \n2. You DO NOT talk about WHALE HUNTERS \n3. Master level of TA skills required \n3.141592 Bring pie \n4. Inactive members will be banned')
            elif text == '/image':
                img = Image.new('RGB', (512, 512))
                base = random.randint(0, 16777216)
                pixels = [base+i*j for i in range(512) for j in range(512)]
                img.putdata(pixels)
                output = StringIO.StringIO()
                img.save(output, 'JPEG')
                reply(img=output.getvalue())
            elif text == '/help' or text == '/options':
                r = '/rules : show rules\n/image : generate an image\n/time(s) : get server time\n/assets : list of assets\n/pairs : list of all pairs (long)\n/<asset> : show this assets pairs\n/<assetpair> : show assetpairs price\n/alerts : show alerts'
                reply(r)
            elif text == '/time' or text == '/times':
                time = KrakenExchange().getServerTime()['rfc1123']
                r = 'Kraken server time: {}'.format(time)
                reply(r)
            elif text == '/assets':
                r = 'Reply with /<asset> to get its pairs\n{}'.format(', '.join(ASSETS))
                reply(r)
            elif text == '/pairs':
                assets = ASSETPAIRS.keys()
                assets.sort()
                r = 'Reply with /<assetpair> to get bid/ask prices\n{}'.format(', '.join(assets))
                reply(r)
            elif text[1:].upper() in ASSETS:
                pairs = []
                for pair in ASSETPAIRS:
                    if pair[:3] == text[1:].upper()[:3]:
                        pairs.append(pair)
                r = 'Reply with /<assetpair> to get bid/ask prices\n{}'.format(', '.join(pairs))
                reply(r)

            elif text.split(' ')[0][1:].upper() in ASSETPAIRS.keys():
                pair = text.split(' ')[0][1:].upper()
                kraken = KrakenExchange()
                ticker = kraken.getTicker(pair=ASSETPAIRS[pair])
                askPrice = float(ticker['Ask Price'][0])
                bidPrice = float(ticker['Bid Price'][0])
                price = (askPrice + bidPrice) / 2
                highPrice = float(ticker['High'][0])
                lowPrice = float(ticker['Low'][0])
                # time = kraken.serverTime['rfc1123']
                r = ""
                if len(text.split(' ')) > 1:
                    if text.split(' ')[1] == 'fib':
                        l_one = highPrice
                        l_two = highPrice - ((highPrice - lowPrice) * 0.236)
                        l_three = highPrice - ((highPrice - lowPrice) * 0.382)
                        l_four = highPrice - ((highPrice - lowPrice) * 0.5)
                        l_five = highPrice - ((highPrice - lowPrice) * 0.618)
                        l_six = highPrice - ((highPrice - lowPrice) * 0.786)
                        l_seven = lowPrice
                        l_eight = highPrice - ((highPrice - lowPrice) * 1.272)
                        l_nine = highPrice - ((highPrice - lowPrice) * 1.618)

                        r = '*{0}* 24h fib levels\n\n*0%*: {1}\n*23.6%*: {2}\n*38.2%*: {3}\n*50%*: {4}\n*61.8%*: {5}\n*78.6%*: {6}\n*100%*: {7}\n\n*127.2%*: {8}\n*161.8%*: {9}\n'.format(pair, l_one, l_two, l_three, l_four, l_five, l_six, l_seven, l_eight, l_nine)
                    if text.split(' ')[1] == 'book':
                        order_book = kraken.getOrderBook(pair=ASSETPAIRS[pair])
                        book = order_book[ASSETPAIRS[pair]]
                        r = "*OrderBook* {0} \n*Asks*\n{1}\n\n*Bids*\n{2}".format(
                            pair,
                            "\n".join(
                                ["{} {}".format(ask[0], ask[1]) for ask in book['asks'][:10]]
                            ),
                            "\n".join(
                                ["{} {}".format(bid[0], bid[1]) for bid in book['bids'][:10]]
                            ),
                        )
                    if text.split(' ')[1] == 'alert':
                        try:
                            target_price = text.split(' ')[2]
                            track_pair_price(pair, price, target_price, chat_id, message_id)
                            r = 'You want me to keep an eye on your {}? I will let you know if it rises or drops to {}'.format(
                                pair, target_price
                            )
                            logging.info(r)
                        except IndexError:
                            r = 'Tell me what price you want an alert for, doofus!'
                else:
                    r = '*{}* \n*Price:* {} \n*---* \n*High:* {} \n*Low:* {}'.format(pair, price, highPrice, lowPrice)
                # r += '\n\n_updated: {}_'.format(time)
                reply(r)
            elif len(text) == 4 or len(text) == 7:
                reply('This asset(pair) is not recognized. Pick one from the /assets list, stupid.')
            else:
                reply('You know, this sort of behaviour could qualify as sexual harassment.')

        # bot text reply's

        elif 'beach' in text:
            reply('dont forget to bring a towel')
        # elif ('sell' in text or 'dropping' in text or 'dumping' in text) and random.choice([True, False]):
        #     reply('weak hands!')
        # elif 'what time' in text:
        #     reply('look at the corner of your screen!')
        # elif 'moon' in text:
        #     reply('http://www.louwmanexclusive.com/nl/brands/lamborghini/')
        # elif 'bitch' in text:
        #     reply('dont talk to me like that!')
        # elif 'penny' in text:
        #     reply('Dont talk behind my back!')
        else:
            if getEnabled(chat_id):
                reply('I got your message! (but I do not know how to answer)')
            else:
                logging.info('not enabled for chat_id {}'.format(chat_id))



# ===== Kraken Exchange methods & classes ======

PUBLIC_URLS = {
    'time': 'https://api.kraken.com/0/public/Time',
    'assets': 'https://api.kraken.com/0/public/Assets',
    'assetPairs': 'https://api.kraken.com/0/public/AssetPairs',
    'ticker': 'https://api.kraken.com/0/public/Ticker',
    'ohlc': 'https://api.kraken.com/0/public/OHLC',
    'orderBook': 'https://api.kraken.com/0/public/Depth',
    'recentTrades': 'https://api.kraken.com/0/public/Trades',
    'spread': 'https://api.kraken.com/0/public/Spread',
}

TICKER_MAPPING = {
    'a': 'Ask Price',
    'b': 'Bid Price',
    'c': 'Last Trade',
    'v': 'Volume',
    'p': 'Volume weighted avg',
    't': '# Trades',
    'l': 'Low',
    'h': 'High',
    'o': 'Opening Price',
}

ASSETS = ['DASH', 'EOS', 'ETC', 'ETH', 'GNO', 'ICN', 'LTC', 'MLN', 'REP', 'USDT',
          'XBT', 'XDG', 'XLM', 'XMR', 'XRP', 'ZEC', 'BCH']

ASSETPAIRS = {
    'DASHEUR': 'DASHEUR',
    'DASHUSD': 'DASHUSD',
    'DASHXBT': 'DASHXBT',
    'EOSETH': 'EOSETH',
    'EOSEUR': 'EOSEUR',
    'EOSUSD': 'EOSUSD',
    'EOSXBT': 'EOSXBT',
    'ETCETH': 'XETCXETH',
    'ETCEUR': 'XETCZEUR',
    'ETCUSD': 'XETCZUSD',
    'ETCXBT': 'XETCXXBT',
    'ETHCAD': 'XETHZCAD',
    'ETHEUR': 'XETHZEUR',
    'ETHGBP': 'XETHZGBP',
    'ETHJPY': 'XETHZJPY',
    'ETHUSD': 'XETHZUSD',
    'ETHXBT': 'XETHXXBT',
    'GNOETH': 'GNOETH',
    'GNOEUR': 'GNOEUR',
    'GNOUSD': 'GNOUSD',
    'GNOXBT': 'GNOXBT',
    'ICNETH': 'XICNXETH',
    'ICNXBT': 'XICNXXBT',
    'LTCEUR': 'XLTCZEUR',
    'LTCUSD': 'XLTCZUSD',
    'LTCXBT': 'XLTCXXBT',
    'MLNETH': 'XMLNXETH',
    'MLNXBT': 'XMLNXXBT',
    'REPETH': 'XREPXETH',
    'REPEUR': 'XREPZEUR',
    'REPUSD': 'XREPZUSD',
    'REPXBT': 'XREPXXBT',
    'USDTUSD': 'USDTZUSD',
    'XBTCAD': 'XXBTZCAD',
    'XBTEUR': 'XXBTZEUR',
    'XBTGBP': 'XXBTZGBP',
    'XBTJPY': 'XXBTZJPY',
    'XBTUSD': 'XXBTZUSD',
    'XDGXBT': 'XXDGXXBT',
    'XLMEUR': 'XXLMZEUR',
    'XLMUSD': 'XXLMZUSD',
    'XLMXBT': 'XXLMXXBT',
    'XMREUR': 'XXMRZEUR',
    'XMRUSD': 'XXMRZUSD',
    'XMRXBT': 'XXMRXXBT',
    'XRPCAD': 'XXRPZCAD',
    'XRPEUR': 'XXRPZEUR',
    'XRPJPY': 'XXRPZJPY',
    'XRPUSD': 'XXRPZUSD',
    'XRPXBT': 'XXRPXXBT',
    'ZECEUR': 'XZECZEUR',
    'ZECUSD': 'XZECZUSD',
    'ZECXBT': 'XZECXXBT',
    'BCHEUR': 'BCHEUR',
    'BCHUSD': 'BCHUSD',
    'BCHXBT': 'BCHXBT',
}

MAXREQUESTS = 15

def _query(url, header):
    r = requests.post(url, data=header)
    if r.status_code == 200:
        return json.loads(r.text)['result']


class KrakenExchange(object):
    """
    Holds all methods for fetching Assets, Assetpairs and current Ticker
    values from the Kraken Exchange.
    Time Skew can be displayed by requesting server time.
    """
    def __init__(self):
        super(KrakenExchange, self).__init__()

    def query_public(self, type, header=None):
        return _query(PUBLIC_URLS[type], header)

    def getServerTime(self):
        serverTime = self.query_public('time')
        if type(serverTime) == ValueError:
            return serverTime.message
        self.serverTime = serverTime
        return self.serverTime

    def getServerSkew(self):
        self.serverSkew = time.time() - self.getServerTime()['unixtime']
        return self.serverSkew

    def getOrderBook(self, pair):
        header = dict(
            pair=pair,
            count=10,
        )
        r = self.query_public('orderBook', header)
        return r

    def getTicker(self, pair):
        header = {'pair': pair} if pair else None
        r = self.query_public('ticker', header)
        if type(r) == ValueError:
            return r.message
        self.ticker = {}
        ticker = r[pair]
        for t in ticker.keys():
            self.ticker[TICKER_MAPPING[t]] = ticker[t]
        return self.ticker


app = webapp2.WSGIApplication([
    ('/me', MeHandler),
    ('/updates', GetUpdatesHandler),
    ('/set_webhook', SetWebhookHandler),
    ('/webhook', WebhookHandler),
], debug=True)
