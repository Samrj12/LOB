import math
import random
from collections import deque
import numpy as np


class SimpleMarketMaker:
    """
    Inventory-aware market maker with:
    - Position limits and inventory-based quote skew
    - Dynamic spread based on short-horizon volatility
    - Average-cost realized/unrealized PnL and equity curve
    - Summary metrics: Sharpe (per-step), max drawdown
    """

    def __init__(
        self,
        order_size: int = 1,
        tick: float = 1.0,
        position_limit: int = 50,
        inventory_k: float = 0.2,
        spread_ticks_min: float = 1.0,
        spread_ticks_max: float = 5.0,
        vol_window: int = 200,
        vol_to_spread_k: float = 10.0,
    ):
        self.order_size = int(order_size)
        self.tick = float(tick)
        self.position_limit = int(position_limit)
        self.inventory_k = float(inventory_k)
        self.spread_ticks_min = float(spread_ticks_min)
        self.spread_ticks_max = float(spread_ticks_max)
        self.vol_window = int(vol_window)
        self.vol_to_spread_k = float(vol_to_spread_k)

        # state
        self.our_orders = {}  # oid -> (side, price, size)
        self.inventory = 0.0
        self.cash = 0.0
        self.avg_price = 0.0  # average cost of current position; sign follows inventory
        self.realized = 0.0
        self.fills = []  # (side, price, qty, ts)

        self.mids = deque(maxlen=self.vol_window)
        self.equity_curve = []  # (ts, equity)
        self.inv_curve = []  # (ts, inventory)
        self.last_mid = None

    # --------- quoting logic ---------
    def _compute_spread_ticks(self) -> float:
        if len(self.mids) < 5:
            return self.spread_ticks_min
        arr = np.array(self.mids, dtype=float)
        rets = np.diff(arr)
        vol = np.std(rets) / (self.tick + 1e-12)  # in ticks
        raw = self.spread_ticks_min + self.vol_to_spread_k * vol
        return float(min(self.spread_ticks_max, max(self.spread_ticks_min, raw)))

    def _desired_quotes(self, mid: float) -> tuple[float, float]:
        # inventory-based skew: if long, push quotes up to encourage selling; if short, pull down to encourage buying
        skew_ticks = self.inventory_k * self.inventory
        eff_mid = mid - skew_ticks * self.tick
        half_spread_ticks = 0.5 * self._compute_spread_ticks()
        bid = math.floor((eff_mid - half_spread_ticks * self.tick) / self.tick) * self.tick
        ask = math.ceil((eff_mid + half_spread_ticks * self.tick) / self.tick) * self.tick
        return bid, ask

    def _place_quotes(self, orderbook, bid_price: float, ask_price: float, ts: float):
        # cancel previous orders (MVP)
        for oid in list(self.our_orders.keys()):
            orderbook.cancel_order(oid)
            del self.our_orders[oid]

        # respect position limits; optionally clip order size near the limit
        if self.inventory < self.position_limit:
            bid_oid = orderbook.place_limit_order('bid', bid_price, self.order_size, ts)
            self.our_orders[bid_oid] = ('bid', bid_price, self.order_size)

        if self.inventory > -self.position_limit:
            ask_oid = orderbook.place_limit_order('ask', ask_price, self.order_size, ts)
            self.our_orders[ask_oid] = ('ask', ask_price, self.order_size)

    def on_event(self, orderbook, ts):
        best_bid, best_ask = orderbook.top_of_book()
        if best_bid is None or best_ask is None:
            return
        mid = (best_bid + best_ask) / 2.0
        self.last_mid = mid
        self.mids.append(mid)

        # compute desired quotes and ensure we don't cross outside best prices in unrealistic ways
        desired_bid, desired_ask = self._desired_quotes(mid)
        # keep quotes anchored near current top-of-book to remain competitive
        bid_px = min(desired_bid, best_bid)
        ask_px = max(desired_ask, best_ask)
        self._place_quotes(orderbook, bid_px, ask_px, ts)

        # update equity curve (mark-to-market)
        equity = self.cash + self.inventory * mid
        self.equity_curve.append((ts, equity))
        self.inv_curve.append((ts, self.inventory))

    # --------- PnL accounting ---------
    def on_fill(self, side, price, qty, ts):
        # side is the book side consumed:
        # 'buy' -> bids consumed -> we bought
        # 'sell' -> asks consumed -> we sold
        self.fills.append((side, price, qty, ts))

        if side == 'buy':  # we bought
            self.cash -= price * qty
            if self.inventory >= 0:  # adding to or starting long
                total_cost = self.avg_price * self.inventory + price * qty
                self.inventory += qty
                self.avg_price = total_cost / max(self.inventory, 1e-12)
            else:  # covering short
                cover = min(qty, -self.inventory)
                self.realized += (self.avg_price - price) * cover
                self.inventory += cover
                remaining = qty - cover
                if self.inventory == 0 and remaining > 0:  # flip to long
                    self.inventory += remaining
                    self.avg_price = price

        elif side == 'sell':  # we sold
            self.cash += price * qty
            if self.inventory <= 0:  # adding to or starting short
                total_proceeds = self.avg_price * (-self.inventory) + price * qty
                self.inventory -= qty
                self.avg_price = total_proceeds / max(-self.inventory, 1e-12)
            else:  # reducing long
                reduce = min(qty, self.inventory)
                self.realized += (price - self.avg_price) * reduce
                self.inventory -= reduce
                remaining = qty - reduce
                if self.inventory == 0 and remaining > 0:  # flip to short
                    self.inventory -= remaining
                    self.avg_price = price

    # --------- metrics ---------
    def _drawdown_and_sharpe(self):
        if len(self.equity_curve) < 2:
            return 0.0, float('nan')
        eq = np.array([e for _, e in self.equity_curve], dtype=float)
        peaks = np.maximum.accumulate(eq)
        dd = eq - peaks
        max_dd = float(dd.min())
        pnl_inc = np.diff(eq)
        if pnl_inc.size > 1 and pnl_inc.std() > 1e-12:
            sharpe = float(pnl_inc.mean() / pnl_inc.std() * (252 ** 0.5))
        else:
            sharpe = float('nan')
        return max_dd, sharpe

    def metrics(self):
        mid = self.last_mid if self.last_mid is not None else 0.0
        equity = self.cash + self.inventory * mid
        unrealized = equity - self.cash - self.realized
        max_dd, sharpe = self._drawdown_and_sharpe()
        return {
            'realized_pnl': float(self.realized),
            'unrealized_pnl': float(unrealized),
            'total_pnl': float(self.realized + unrealized),
            'cash': float(self.cash),
            'inventory': float(self.inventory),
            'avg_price': float(self.avg_price),
            'fills': int(len(self.fills)),
            'max_drawdown': float(max_dd),
            'sharpe': float(sharpe),
        }
