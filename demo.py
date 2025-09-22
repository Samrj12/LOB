from engine.orderbook import OrderBook
from engine.replayer import Replayer
from strategies.market_maker import SimpleMarketMaker
from sample_data import synthetic_event_generator
import matplotlib.pyplot as plt
import os, json

def main():
    ob = OrderBook()
    mm = SimpleMarketMaker(order_size=1)
    gen = synthetic_event_generator(n_steps=500)
    rp = Replayer(ob, mm, gen)
    metrics = rp.run(max_events=10000)
    print('=== Demo metrics ===')
    for k,v in metrics.items():
        print(f'{k}: {v}')

    # persist metrics
    os.makedirs('results', exist_ok=True)
    with open('results/metrics.json', 'w') as f:
        json.dump(metrics, f, indent=2)
    print('Saved results/metrics.json')

    # equity curve plot
    eq = getattr(mm, 'equity_curve', [])
    if eq:
        times = [t for t, _ in eq]
        values = [e for _, e in eq]
        plt.figure(figsize=(7,3))
        plt.plot(times, values, label='Equity (cash + MTM)')
        plt.xlabel('time')
        plt.ylabel('equity')
        plt.title('Market-Maker Equity Curve (synthetic)')
        plt.legend()
        plt.tight_layout()
        plt.savefig('results/pnl.png')
        print('Saved results/pnl.png')
    else:
        print('No equity curve points recorded.')

if __name__ == '__main__':
    main()
