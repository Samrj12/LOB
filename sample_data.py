import random, math, time

def synthetic_event_generator(n_steps=1000, base_price=10000.0, seed=42):
    random.seed(seed)
    def gen():
        nonlocal base_price
        tick = 1.0
        # Track sizes per level to keep depth consistent over time
        bid_sizes = [10 for _ in range(5)]
        ask_sizes = [10 for _ in range(5)]
        bids = [(base_price - i*tick, bid_sizes[i-1]) for i in range(1,6)]
        asks = [(base_price + i*tick, ask_sizes[i-1]) for i in range(1,6)]
        ts = 0.0
        yield {'type':'snapshot', 'bids':bids, 'asks':asks, 'ts':ts}
        for i in range(n_steps):
            ts += 0.001
            # random walk in mid/base price
            drift = random.gauss(0, 1.0)
            base_price += drift * 0.1

            # market order that may sweep multiple levels (slippage)
            if random.random() < 0.35:
                buy_side = random.random() < 0.5
                levels = 1 + int(abs(random.gauss(0.0, 1.0)))
                levels = max(1, min(5, levels))
                if buy_side:
                    price = asks[levels-1][0]
                else:
                    price = bids[levels-1][0]
                size = max(1, int(abs(random.gauss(2.0, 1.5))))
                yield {'type':'trade', 'price': price, 'size': size, 'ts': ts}

            # occasional snapshot refresh with size jitter (cancels/adds) and re-centering
            if random.random() < 0.10:
                bid_sizes = [max(0, s + random.randint(-3, 3)) for s in bid_sizes]
                ask_sizes = [max(0, s + random.randint(-3, 3)) for s in ask_sizes]
                if bid_sizes[0] == 0: bid_sizes[0] = 1
                if ask_sizes[0] == 0: ask_sizes[0] = 1
                bids = [(base_price - i*tick, bid_sizes[i-1]) for i in range(1,6)]
                asks = [(base_price + i*tick, ask_sizes[i-1]) for i in range(1,6)]
                yield {'type':'snapshot', 'bids':bids, 'asks':asks, 'ts': ts}
    return gen

if __name__ == '__main__':
    gen = synthetic_event_generator(50)
    for e in gen():
        print(e)
