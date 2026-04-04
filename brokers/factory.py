from brokers.base import BrokerFeedAdapter, BrokerRestAdapter

class BrokerFactory:
    _rest_registry: dict = {}
    _feed_registry: dict = {}

    @classmethod
    def register_rest(cls, name: str, creator):
        cls._rest_registry[name.lower()] = creator
    
    @classmethod
    def register_feed(cls, name: str, creator):
        cls._feed_registry[name.lower()] = creator

    @classmethod
    def create_rest(cls, name: str) -> BrokerRestAdapter:
        creator = cls._rest_registry[name.lower()]

        if not creator:
            raise ValueError(f"No REST adapter registered for broker: {name}")
        return creator()

    @classmethod
    def create_feed(cls, name: str) -> BrokerFeedAdapter:
        creator = cls._feed_registry.get(name.lower())
        if not creator:
            raise ValueError(f"No feed adapter registered for broker: {name}")
        return creator()


# Register brokers — only place in the codebase that imports concrete adapters
from brokers.groww.adapter import GrowwAdapter
from brokers.groww.feed import GrowwFeed

BrokerFactory.register_rest("groww", GrowwAdapter)
BrokerFactory.register_feed("groww", GrowwFeed)
