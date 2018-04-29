import requests
from bs4 import BeautifulSoup


def get_exchange_rate_xe():
    resp = requests.get('http://www.xe.com/currencyconverter/convert/?To=SGD')
    soup = BeautifulSoup(resp.content, 'html.parser')
    return float(soup.find('span', {'class': 'uccResultUnit'}).get('data-amount'))

def get_exchange_rate_dbs():
    resp = requests.get('https://www.dbs.com.sg/personal/rates-online/foreign-currency-foreign-exchange.page')
    soup = BeautifulSoup(resp.content, 'html.parser')
    return float(soup.find('tr', {'name': 'usdollar'}).find('td', {'data-before-text': "Selling TT/OD"}).text)


def get_exchange_rate():
    try:
        rate = get_exchange_rate_dbs()
    except:
        rate = get_exchange_rate_xe()
    return rate
