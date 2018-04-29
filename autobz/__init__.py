from bfxview import GeminiClient, FybClient
from imp import load_source
from datetime import datetime
import time
import requests
import json
from .alert import GmailAlertServer
from .utils import get_exchange_rate


class FakeApp(object):
    def __init__(self):
        self.config = {}
        self.extensions = {}


suspended = False
prev_hour = datetime.now().hour - 1
app = FakeApp()
gemini = GeminiClient()
fyb = FybClient()
gmail_alert_server = GmailAlertServer()


def init_extensions():
    gemini.init_app(app)
    fyb.init_app(app)
    gmail_alert_server.init_app(app)


def get_margin_pct():
    fee_pct = float(app.config.get('FYB_FEE_PCT', 0.6) + app.config.get('GEMINI_FEE_PCT', 0.25))
    threshold_pct = float(app.config.get('THRESHOLD_PCT', 1.0))
    return fee_pct + threshold_pct


def get_delta():
    exchange_rate = get_exchange_rate()
    g_ask_usd = float(gemini.get_ticker()['ask'])
    g_ask_sgd = g_ask_usd * exchange_rate
    f_bid_sgd = float(fyb.get_ticker().json()['bid'])
    delta_pct = ((f_bid_sgd / g_ask_sgd) - 1.0) * 100.0
    return {
        'gemini_ask_usd': g_ask_usd,
        'gemini_ask_sgd': g_ask_sgd,
        'fyb_bid_sgd': f_bid_sgd,
        'exchange_rate': exchange_rate,
        'delta_pct': delta_pct
    }


def send_delta_alert():
    delta_info = get_delta()
    gmail_alert_server.send(
        'AUTOBZ delta alert {:.2f}% {}'.format(delta_info['delta_pct'], str(gmail_alert_server.today)),
        json.dumps(delta_info, indent=2)
    )


def is_profitable():
    try:
        return get_delta()['delta_pct'] > get_margin_pct()
    except:
        pass
    return False


def get_fyb_bids():
    return [
        map(float, order)
        for order in fyb.get_order_book().json()['bids']
    ]


def get_gemini_asks():
    exchange_rate = get_exchange_rate()
    return [
        [float(x['price']) * exchange_rate, float(x['amount'])]
        for x in gemini.get_order_book()['asks']
    ]


def get_cum(orders):
    total_qty = 0.0
    total_cost = 0.0
    out = []
    for order in orders:
        p, q = order
        cost = p * q
        total_qty += q
        total_cost += cost
        out.append(
            [total_qty, total_cost, total_cost/total_qty]
        )
    return out


def is_safe(f_bids, g_asks):
    scale_factor = 1.0 - float(get_margin_pct()) / 100.0
    f_bids_removed_margin = [[p * scale_factor, q] for p, q in f_bids]
    highest_asks = f_bids_removed_margin[0][0]
    g_asks_cum = get_cum(filter(lambda x: x[0] < highest_asks, g_asks))
    safety_factor = app.config.get('SAFETY_FACTOR', 10.0)
    return f_bids[0][1] * safety_factor <= g_asks_cum[-1][0]


class FYBException(Exception):
    pass


def place_fyb_sell(price, qty):
    fyb_order_id = ''
    try:
        res = fyb.place_order(qty=qty, price=price, side='S')
        fyb_order_id = str(res.json()['pending_oid'])
        if res.json()['error'] != 0:
            raise FYBException(res.json()['error'])
    except Exception as e:
        gmail_alert_server.send('[Important] AUTOBZ Place fyb order failed', str(e) + '\n' + str(res))
    done_qty = qty
    pending = {}
    cancel = {}
    if fyb_order_id:
        time.sleep(1)
        try:
            res = fyb.get_pending_orders()
            pending = res.json()
            for order in res.json()['orders']:
                if str(order['ticket']) == fyb_order_id:
                    done_qty -= float(order['qty'])
                    # cancel remaining
                    time.sleep(1)
                    cancel = fyb.cancel_pending_orders(fyb_order_id).json()
            if res.json()['error'] != 0:
                raise FYBException(res.json()['error'])
            if cancel and cancel.get('error') != 0:
                raise FYBException(cancel.get('error'))
        except Exception as e:
            gmail_alert_server.send('[Important] AUTOBZ Check fyb order failed', str(e) + '\n' + str(res))
    total_qty = 0.0
    orders = []
    history = {}
    try:
        time.sleep(1)
        res = fyb.get_order_history()
        history = res.json()
        orders = [x for x in res.json()['orders'] if str(x['ticket']) == fyb_order_id]
        total_qty = float(sum([float(x['qty'].replace('BTC', '')) for x in orders]))
        if res.json()['error'] != 0:
            raise FYBException(res.json()['error'])
    except Exception as e:
        gmail_alert_server.send('[Important] AUTOBZ Check fyb traded qty failed', str(e) + '\n' + str(res))
    if done_qty != total_qty:
        gmail_alert_server.send('[Important] AUTOBZ fyb done_qty and total_qty don\'t tally', 'done_qty: %s, total_qty: %s' % (done_qty, total_qty))
    return total_qty, fyb_order_id, orders#, pending, cancel, history


def get_fyb_balance():
    bal = 0
    try:
        res = fyb.get_account_info()
        bal = float(res.json()['btcBal'])
        if res.json()['error'] != 0:
            raise FYBException(res.json()['error'])
    except Exception as e:
        gmail_alert_server.send('[Important] AUTOBZ Check fyb balance failed', str(e) + '\n' + str(res))
    return bal


def loop():
    global suspended, prev_hour
    if prev_hour != datetime.now().hour:
        # send alert every hour
        send_delta_alert()
        prev_hour = datetime.now().hour
    if suspended:
        return
    if not is_profitable():
        return
    f_bids = get_fyb_bids()
    g_asks = get_gemini_asks()
    if not is_safe(f_bids, g_asks):
        return
    price, qty = f_bids[0]
    fyb_btc_bal = get_fyb_balance()
    if fyb_btc_bal < qty:
        qty = fyb_btc_bal
    if not qty > 0.0:
        return
    total_qty, fyb_order_id, fyb_orders = place_fyb_sell(price=price, qty=qty)
    if total_qty > 0.0:
        buy_price = price / get_exchange_rate()
        try:
            gemini_order = gemini.place_order(
                side='buy', price=buy_price, amount=total_qty,
                client_order_id='FYB' + fyb_order_id
            )
            if isinstance(gemini_order, requests.Response):
                raise FYBException(str(gemini_order.__dict__))
        except Exception as e:
            gmail_alert_server.send('[Important] AUTOBZ Place gemini order failed', str(e) + '\nFYB order: ' + fyb_order_id)
        else:
            gmail_alert_server.send('[Done] AUTOBZ done', 'FYB order:\n%s\nGemini order:\n%s\n' % (fyb_orders, gemini_order))


def main():
    import sys
    if len(sys.argv) <= 1:
        print('config_file required!')
        sys.exit(1)
    config_file = sys.argv[1]
    config = load_source('config', config_file)
    app.config = dict((k, v) for k, v in config.__dict__.items() if k[0] != '_')
    init_extensions()
    interval = getattr(config, 'LOOP_INTERVAL_SECONDS', 60)
    while True:
        try:
            loop()
        except:
            pass
    time.sleep(interval)
