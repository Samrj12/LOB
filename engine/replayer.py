import time

class Replayer:
    def __init__(self, orderbook, strategy, event_generator):
        self.ob = orderbook
        self.strategy = strategy
        self.event_generator = event_generator
        self.stats = { 'fills': [], 'orders': [] }

    def run(self, max_events=10000):
        # strategy receives a reference to orderbook and can place orders via the book API.
        for i, ev in enumerate(self.event_generator()):
            if i >= max_events:
                break
            t = ev.get('ts', i*0.001)
            typ = ev['type']
            if typ == 'snapshot':
                self.ob.apply_snapshot(ev['bids'], ev['asks'], t)
            elif typ == 'trade':
                fills = self.ob.process_trade(ev['price'], ev['size'], t)
                # notify strategy of trade/fills
                if fills:
                    for f in fills:
                        side, price, qty = f
                        self.stats['fills'].append({'ts': t, 'side': side, 'price': price, 'qty': qty})
                        self.strategy.on_fill(side, price, qty, t)
            # let strategy act on each event
            self.strategy.on_event(self.ob, t)
        # persist fills log
        try:
            import os, csv
            os.makedirs('results', exist_ok=True)
            with open('results/fills.csv', 'w', newline='') as f:
                w = csv.DictWriter(f, fieldnames=['ts','side','price','qty'])
                w.writeheader()
                w.writerows(self.stats['fills'])
        except Exception:
            pass
        return self.strategy.metrics()
