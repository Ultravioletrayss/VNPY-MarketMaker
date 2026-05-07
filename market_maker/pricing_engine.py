from .market_data import MarketSnapshot


class PricingEngine:
    """Calculates the fair reference price from the order book."""

    def calculate_mid(self, snapshot: MarketSnapshot) -> float:
        return (snapshot.bid1 + snapshot.ask1) / 2

    def calculate_depth_adjusted_mid(self, snapshot: MarketSnapshot, levels: int = 3) -> float:
        """Reserved extension point for five-level imbalance pricing."""
        bid_volume = sum(snapshot.bid_volumes[:levels])
        ask_volume = sum(snapshot.ask_volumes[:levels])
        total_volume = bid_volume + ask_volume

        if total_volume <= 0:
            return self.calculate_mid(snapshot)

        imbalance = (bid_volume - ask_volume) / total_volume
        return self.calculate_mid(snapshot) + imbalance * 0.5

