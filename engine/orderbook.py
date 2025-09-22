import bisect
import math
from collections import defaultdict, deque

class Order:
    def __init__(self, oid, side, price, size, ts):
        self.oid = oid
        self.side = side  # 'bid' or 'ask'
        self.price = price
        self.size = size
        self.ts = ts  # timestamp when placed

class OrderBook:
    """Simple in-memory order book.
    - Maintains sorted price levels (lists) and per-price FIFO queues of orders.
    - Supports applying snapshots, processing trade events, placing limit orders, and market orders.
    This is intentionally simple for a fast MVP; replace with more accurate queue-positioning later.
    """
    def __init__(self):
        # price -> deque(Order)
        self.bids = defaultdict(deque)
        self.asks = defaultdict(deque)
        self.bid_prices = []  # sorted descending
        self.ask_prices = []  # sorted ascending
        self.next_oid = 1
        self.time = 0.0

    # --- helpers ---
    def _insert_price(self, prices, price, reverse=False):
        if price in prices:
            return
        if not prices:
            prices.append(price)
            return
        # maintain ascending list; reverse handled by view
        bisect.insort(prices, price)

    def _remove_price_if_empty(self, prices, price, book_side):
        if len(book_side[price]) == 0:
            del book_side[price]
            try:
                prices.remove(price)
            except ValueError:
                pass

    # --- snapshot/trade APIs ---
    def apply_snapshot(self, bids, asks, ts):
        """Apply a full snapshot (list of (price,size)). This will reset book contents (MVP behavior)."""
        self.time = ts
        self.bids.clear(); self.asks.clear(); self.bid_prices.clear(); self.ask_prices.clear()
        for p, s in bids:
            if s <= 0: continue
            self.bids[p] = deque([Order(0, 'bid', p, s, ts)])
            self._insert_price(self.bid_prices, p)
        for p, s in asks:
            if s <= 0: continue
            self.asks[p] = deque([Order(0, 'ask', p, s, ts)])
            self._insert_price(self.ask_prices, p)

    def top_of_book(self):
        best_bid = max(self.bid_prices) if self.bid_prices else None
        best_ask = min(self.ask_prices) if self.ask_prices else None
        return best_bid, best_ask

    def process_trade(self, price, size, ts):
        """Process an incoming trade consuming liquidity from the book.
        For simplicity: if trade price >= best_ask -> consumes asks; if <= best_bid -> consumes bids.
        """
        self.time = ts
        fills = []
        # trade hitting asks (buy trade)
        if self.ask_prices and price >= min(self.ask_prices):
            while size > 0 and self.ask_prices and price >= min(self.ask_prices):
                p = min(self.ask_prices)
                q = self.asks[p]
                while size > 0 and q:
                    o = q[0]
                    take = min(o.size, size)
                    o.size -= take
                    size -= take
                    fills.append(('sell', p, take))
                    if o.size == 0:
                        q.popleft()
                self._remove_price_if_empty(self.ask_prices, p, self.asks)
        # trade hitting bids (sell trade)
        elif self.bid_prices and price <= max(self.bid_prices):
            while size > 0 and self.bid_prices and price <= max(self.bid_prices):
                p = max(self.bid_prices)
                q = self.bids[p]
                while size > 0 and q:
                    o = q[0]
                    take = min(o.size, size)
                    o.size -= take
                    size -= take
                    fills.append(('buy', p, take))
                    if o.size == 0:
                        q.popleft()
                self._remove_price_if_empty(self.bid_prices, p, self.bids)
        return fills

    # --- simple order placement ---
    def place_limit_order(self, side, price, size, ts):
        """Place a simulated limit order that goes to the tail of the FIFO at that price level.
        Returns order id.
        """
        self.time = ts
        oid = self.next_oid; self.next_oid += 1
        o = Order(oid, side, price, size, ts)
        if side == 'bid':
            self.bids[price].append(o)
            self._insert_price(self.bid_prices, price)
        else:
            self.asks[price].append(o)
            self._insert_price(self.ask_prices, price)
        return oid

    def cancel_order(self, oid):
        # naive scan; for MVP only (improve later)
        for p, q in list(self.bids.items()):
            for o in list(q):
                if o.oid == oid:
                    q.remove(o)
                    self._remove_price_if_empty(self.bid_prices, p, self.bids)
                    return True
        for p, q in list(self.asks.items()):
            for o in list(q):
                if o.oid == oid:
                    q.remove(o)
                    self._remove_price_if_empty(self.ask_prices, p, self.asks)
                    return True
        return False

    def snapshot_for_display(self, depth=5):
        bids = sorted(self.bid_prices, reverse=True)[:depth]
        asks = sorted(self.ask_prices)[:depth]
        return ([ (p, sum([o.size for o in self.bids[p]])) for p in bids ],
                [ (p, sum([o.size for o in self.asks[p]])) for p in asks ])
