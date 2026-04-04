
class BrokerException(Exception):
    def __init__(self, message: str, code: int = 500):
        self.message = message
        self.code = code
        super().__init__(message)

class BrokerAuthError(BrokerException):
    def __init__(self, message: str):
        super().__init__(message, code=401)

class BrokerOrderError(BrokerException):
    def __init__(self, message: str):
        super().__init__(message, code=422)

class BrokerDataError(BrokerException):
    def __init__(self, message: str):
        super().__init__(message, code=502)

class BrokerNetworkError(BrokerException):
    def __init__(self, message: str):
        super().__init__(message, code=503)

class AppException(Exception):
    def __init__(self, message: str, code: int = 500):
        self.message = message
        self.code = code
        super().__init__(message)

class InvalidSignalError(AppException):
    def __init__(self, message: str, code = 400):
        super().__init__(message, code)

class KillSwitchActiveError(AppException):
    def __init__(self, message: str = "Trading halted for today"):
        super().__init__(message, code=403)

class TradeNotFoundError(AppException):
    def __init__(self, trade_id: str):
        super().__init__(f"Trade {trade_id} not found", code=404)

class InvalidStateTransitionError(AppException):
    def __init__(self, from_state: str, to_state: str):
        super().__init__(f"Cannot transition from {from_state} to {to_state}", code=409)