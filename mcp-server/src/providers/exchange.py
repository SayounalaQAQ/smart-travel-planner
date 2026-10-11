"""Frankfurter reference exchange-rate adapter."""
import urllib.parse


def get_exchange_rate(base, quote, date=None, *, registry, get_json, checked_at):
    base, quote = base.upper(), quote.upper()
    url = f"{registry.endpoint('exchange')}/{urllib.parse.quote(date or 'latest')}?base={urllib.parse.quote(base)}&symbols={urllib.parse.quote(quote)}"
    result = get_json(url)
    return {"base_currency": base, "quote_currency": quote, "rate": result.get("rates", {}).get(quote), "timestamp": result.get("date"), "source": "https://www.frankfurter.dev/", "confidence": "high", "checked_at": checked_at()}
