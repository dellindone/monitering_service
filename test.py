from growwapi import GrowwAPI
import pyotp
 
api_key = "eyJraWQiOiJaTUtjVXciLCJhbGciOiJFUzI1NiJ9.eyJleHAiOjI1NjM0Njc1MzIsImlhdCI6MTc3NTA2NzUzMiwibmJmIjoxNzc1MDY3NTMyLCJzdWIiOiJ7XCJ0b2tlblJlZklkXCI6XCIxNGVlNjQ4MC1hMWY5LTQxNDMtYTk2OC1jN2IwYTY0MTkxMGJcIixcInZlbmRvckludGVncmF0aW9uS2V5XCI6XCJlMzFmZjIzYjA4NmI0MDZjODg3NGIyZjZkODQ5NTMxM1wiLFwidXNlckFjY291bnRJZFwiOlwiYjM3NzU3OTAtMTY3My00ODRiLTg2MWMtMjRlNmIwM2NjOTQ0XCIsXCJkZXZpY2VJZFwiOlwiYTM1ZDFiNDctYTEwMi01NGRkLTgxN2ItYjdlOWM3NTdhMzk2XCIsXCJzZXNzaW9uSWRcIjpcIjZmOTUxNjYyLTBjZWYtNDhhZS04ZTVhLWExYjM4NWJlNzFiYVwiLFwiYWRkaXRpb25hbERhdGFcIjpcIno1NC9NZzltdjE2WXdmb0gvS0EwYkZkVG5qbnBtOTNKRnZRVkZUNHdZcU5STkczdTlLa2pWZDNoWjU1ZStNZERhWXBOVi9UOUxIRmtQejFFQisybTdRPT1cIixcInJvbGVcIjpcImF1dGgtdG90cFwiLFwic291cmNlSXBBZGRyZXNzXCI6XCIyNDAxOjQ5MDA6ODhkYjpmYjhlOmY4ZjE6Nzc2NDpmZGE2OjkzODYsMTcyLjY5LjEzMS4yMDgsMzUuMjQxLjIzLjEyM1wiLFwidHdvRmFFeHBpcnlUc1wiOjI1NjM0Njc1MzI0MzIsXCJ2ZW5kb3JOYW1lXCI6XCJncm93d0FwaVwifSIsImlzcyI6ImFwZXgtYXV0aC1wcm9kLWFwcCJ9.7Vn9YmCVH5ZfvMEHM0I_22eXBEVmZnGHGcb-lPG2tU_YjF7IYLkNMksyK6VisdISXxfwx_sudhwYmy9_sESXQg"
secret = "*2MPScn!sFjAS^xcW$mnmJkyNRcD%e-z"
 
access_token = GrowwAPI.get_access_token(api_key=api_key, secret=secret)
# Use access_token to initiate GrowwAPI
groww = GrowwAPI(access_token)

# user_positions_response = groww.get_order_list()

# fno_positions_response = groww.get_positions_for_user(segment=groww.SEGMENT_FNO)

# print(user_positions_response)
# print(fno_positions_response)


symbols_to_try = [
    ("NSE", "CASH", "INDIA VIX"),
    ("NSE", "CASH", "INDIAVIX"),
    ("NSE", "CASH", "INDIA_VIX"),
    ("NSE", "CASH", "Nifty 50"),   # test with known index first
]

for exchange, segment, symbol in symbols_to_try:
    try:
        key = f"{exchange}_{symbol}"
        result = groww.get_ltp(segment=segment, exchange_trading_symbols=(key,))
        print(f"✅ {symbol}: {result}")
    except Exception as e:
        print(f"❌ {symbol}: {e}")