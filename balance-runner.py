#!/usr/bin/env python3

import json
import datetime
from pprint import pprint
from collections import defaultdict
from scipy.interpolate import interp1d
from BTrees.OOBTree import OOBTree

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
BURNERS = [
    ZERO_ADDRESS,
    "0xdcb6a51ea3ca5d3fd898fd6564757c7aaec3ca92",   # susdv2
    "0x13c1542a468319688b89e323fe9a3be3a90ebb27",   # sbtc
    "0x13b54e8271b3e45ce71d8f4fc73ea936873a34fc",   # susd (old)
    "0x0001fb050fe7312791bf6475b96569d83f695c9f",   # YFI
    "0xb81d3cb2708530ea990a287142b82d058725c092",   # YFII
    "0x95284d906ab7f1bd86f522078973771ecbb20662",   # YFFI
    "0xd5bf26cdbd0b06d3fb0c6acd73db49d21b69e34f",   # YFID
    "0x9d03A0447aa49Ab26d0229914740c18161b08386",   # simp
    "0x803687e7756aff995d3053f7ce6cc41018ef62c3",   # brr.apy.finance
    "0xe4ffd96b5e6d2b6cdb91030c48cc932756c951b5",   # YYFI
    "0x35e3ad7652c7d5798412fea629f3e768662470cd",   # xearn/black wifey
]
BURNERS = set(b.lower() for b in BURNERS)
POOL_TOKENS = [
    '0xdbe281e17540da5305eb2aefb8cef70e6db1a0a9',  # compound1
    '0x3740fb63ab7a09891d7c0d4299442a551d06f5fd',  # compound2
    '0x845838df265dcd2c412a1dc9e959c7d08537f8a2',  # compound3
    '0x9fc689ccada600b6df723d9e47d84d76664a1f23',  # USDT
    '0xdf5e0e81dff6faf3a7e52ba697820c5e32d806a8',  # y
    '0x3b3ac5386837dc563660fb6a0937dfaa5924333b',  # busd
    '0x2b645a6a426f22fb7954dc15e583e3737b8d1434',  # susd (old, meta)
    '0xc25a3a3b969415c80451098fa907ec722572917f',  # susdv2
    '0xd905e2eaebe188fc92179b6350807d8bd91db0d8',  # pax
    '0x49849c98ae39fff122806c06791fa73784fb3675',  # ren
    '0x075b1bb99792c9e1041ba13afef80c91a1e70fb3'   # sbtc
]
BTC_TOKENS = [
    '0x49849c98ae39fff122806c06791fa73784fb3675',  # ren
    '0x075b1bb99792c9e1041ba13afef80c91a1e70fb3'   # sbtc
]

POOL2TOKEN = {
    '0xe5fdbab9ad428bbb469dee4cb6608c0a8895cba5': '0xdbe281e17540da5305eb2aefb8cef70e6db1a0a9',  # compound1
    '0x2e60cf74d81ac34eb21eeff58db4d385920ef419': '0x3740fb63ab7a09891d7c0d4299442a551d06f5fd',  # compound2
    '0xa2b47e3d5c44877cca798226b7b8118f9bfb7a56': '0x845838df265dcd2c412a1dc9e959c7d08537f8a2',  # compound3
    '0x52ea46506b9cc5ef470c5bf89f17dc28bb35d85c': '0x9fc689ccada600b6df723d9e47d84d76664a1f23',  # USDT
    '0x45f783cce6b7ff23b2ab2d70e416cdb7d6055f51': '0xdf5e0e81dff6faf3a7e52ba697820c5e32d806a8',  # y
    '0x79a8c46dea5ada233abaffd40f3a0a2b1e5a4f27': '0x3b3ac5386837dc563660fb6a0937dfaa5924333b',  # busd
    '0xedf54bc005bc2df0cc6a675596e843d28b16a966': '0x2b645a6a426f22fb7954dc15e583e3737b8d1434',  # susd (old, meta)
    '0xa5407eae9ba41422680e2e00537571bcc53efbfd': '0xc25a3a3b969415c80451098fa907ec722572917f',  # susdv2
    '0x06364f10b501e868329afbc005b3492902d6c763': '0xd905e2eaebe188fc92179b6350807d8bd91db0d8',  # pax
    '0x93054188d876f558f4a66b2ef1d97d16edf0895b': '0x49849c98ae39fff122806c06791fa73784fb3675',  # ren
    '0x7fc77b5c7614e1533320ea6ddc2eb61fa00a9714': '0x075b1bb99792c9e1041ba13afef80c91a1e70fb3'   # sbtc
}

TIMESTEP = 24 * 3600


class Balances:
    def __init__(self):
        self.balances = defaultdict(lambda: defaultdict(OOBTree))  # pool -> address -> [(timestamp, block, logIndex) -> value]
        self.raw_transfers = defaultdict(list)
        self.raw_prices = defaultdict(list)
        self.lps = set()
        self.price_splines = {}
        self.min_timestamp = int(datetime.datetime(2020, 1, 11).timestamp())  # before this date is really premine
        self.max_timestamp = 0
        self.user_integrals = defaultdict(list)  # user -> (timestamp, integral)
        self.total = 0.0

    def load(self, tx_file, vp_file, btc_price_file):
        with open(tx_file) as f:
            data = json.load(f)

        with open(vp_file) as f:
            virtual_prices = json.load(f)

        with open(btc_price_file) as f:
            btc_prices = json.load(f)['prices']
        btc_prices = [(t // 1000, p) for t, p in btc_prices]
        t, btc_prices = list(zip(*btc_prices))
        self.btc_spline = interp1d(t, btc_prices, kind='linear', fill_value=(btc_prices[0], btc_prices[-1]), bounds_error=False)

        transfers = data
        for el in transfers:
            el['timestamp'] = int(el['timestamp'])
            el['block'] = int(el['block'])
            for event in el['transfers']:
                event['value'] = int(event['value'])
                event['logIndex'] = int(event['logIndex'])
                if event['to'] not in BURNERS:
                    self.lps.add(event['to'])
                if event['from'] not in BURNERS:
                    self.lps.add(event['from'])
                event['timestamp'] = el['timestamp']
                # self.min_timestamp = min(self.min_timestamp, event['timestamp'])
                self.max_timestamp = max(self.max_timestamp, event['timestamp'])
                event['block'] = el['block']
                self.raw_transfers[event['address']].append(event)

        for el in virtual_prices:
            el['timestamp'] = int(el['timestamp'])
            el['block'] = int(el['block'])
            el['virtualPrice'] = int(el['virtualPrice']) / 1e18
            self.raw_prices[POOL2TOKEN[el['address']]].append(el)

        for a in self.raw_transfers.keys():
            self.raw_transfers[a] = sorted(
                    self.raw_transfers[a],
                    key=lambda el: (el['block'], el['logIndex']))
        for a in self.raw_prices.keys():
            self.raw_prices[a] = sorted(self.raw_prices[a], key=lambda el: el['block'])

    def fill(self):
        for pool in POOL_TOKENS:
            ts = [el['timestamp'] for el in self.raw_prices[pool]]
            vp = [el['virtualPrice'] for el in self.raw_prices[pool]]
            self.price_splines[pool] = interp1d(ts, vp, kind='linear', fill_value=(min(vp), max(vp)), bounds_error=False)

        for pool in POOL_TOKENS:  # self.raw_transfers.keys():
            for el in self.raw_transfers[pool]:
                key = (-el['timestamp'], -el['block'], -el['logIndex'])
                if el['from'] not in BURNERS:
                    tree = self.balances[pool][el['from']]
                    if key not in tree:
                        value = 0
                        if len(tree) > 0:
                            value = tree.values()[0]
                        elif el['value'] > 0:
                            pprint(el)
                        value -= el['value']
                        tree[key] = value
                if el['to'] not in BURNERS:
                    tree = self.balances[pool][el['to']]
                    if key not in tree:
                        value = 0
                        if len(tree) > 0:
                            value = tree.values()[0]
                        else:
                            value = 0
                        value += el['value']
                        tree[key] = value

        self.lps = list(self.lps)

    def get_balance(self, pool, addr, timestamp):
        pool = pool.lower()
        addr = addr.lower()
        tree = self.balances[pool][addr]
        try:
            return tree.values((-timestamp,))[0]
        except IndexError:
            return 0

    def fill_integrals(self):
        for t in range(self.min_timestamp, self.max_timestamp, TIMESTEP):
            total = 0
            pool_totals = defaultdict(int)
            deposits = defaultdict(int)
            for pool in POOL_TOKENS:
                vp = float(self.price_splines[pool](t))
                if pool in BTC_TOKENS:
                    vp *= float(self.btc_spline(t))
                for addr in self.lps:
                    value = int(vp * self.get_balance(pool, addr, t))
                    total += value
                    deposits[addr] += value
                    pool_totals[pool] += value / 1e18
            pprint(pool_totals)

            rel = {addr: value / total if total else 0 for addr, value in deposits.items()}
            for addr in self.lps:
                if len(self.user_integrals[addr]) == 0:
                    integral = 0
                else:
                    integral = self.user_integrals[addr][-1][1]
                integral += rel[addr]
                self.user_integrals[addr].append((t, integral))

            print(datetime.datetime.fromtimestamp(t), total / 1e18)
            self.total += 1.0

    def export(self, fname='output.json'):
        user_fractions = {}
        for addr in self.user_integrals:
            t, integral = self.user_integrals[addr][-1]
            user_fractions[addr] = (t, integral / self.total)
        with open(fname, 'w') as f:
            json.dump(user_fractions, f)

    # Filling integrals:
    # +* iterate time
    # +* get vprice for each time (btree)
    # +* get balance for each address at each time (btree)
    # * calc total*vp across all pools, fractions
    # * add vp * balance * dt to running integral for each address
    # * add vp * total to total integral

    # For balancer pools:
    # * have mappings deposit address -> BPT token
    # * calc bpt total, bpt fractions
    # * add vp * fraction * dt * bpt_fraction to integrals of addresses


if __name__ == '__main__':
    balances = Balances()
    balances.load('json/transfer_events.json', 'json/virtual_prices.json', 'json/btc-prices.json')
    balances.fill()
    balances.fill_integrals()
    balances.export()
    import IPython
    IPython.embed()
    # '0xdf5e0e81dff6faf3a7e52ba697820c5e32d806a8'
    # '0x39415255619783A2E71fcF7d8f708A951d92e1b6',
    # 1583559445
