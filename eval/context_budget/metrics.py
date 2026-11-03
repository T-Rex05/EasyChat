"""Provider usage accounting. Rates are currency units per million tokens."""
from decimal import Decimal
from backend.utils.llm_usage import trace_usage


def normalize_usage(raw):
    normalized = trace_usage(raw)
    return {"uncached_input": normalized["input_tokens"], "cache_read": normalized["cache_read_tokens"],
            "cache_write": normalized["cache_write_tokens"], "output": normalized["output_tokens"],
            "complete": normalized["usage_complete"]}


def cost(usage, rates):
    if not usage or not usage.get("complete") or not rates:
        return None
    names = ("uncached_input", "cache_read", "cache_write", "output")
    if any(rates.get(name) is None for name in names):
        return None
    prices = {name: Decimal(str(rates[name])) for name in names}
    if any(not price.is_finite() or price < 0 for price in prices.values()):
        raise ValueError("Prices must be finite and nonnegative")
    return float(sum(Decimal(usage[name]) * prices[name] for name in names) / Decimal(1000000))


def aggregate(calls):
    values = [call.get("cost") for call in calls]
    return {"calls": len(calls), "failed_calls": sum(call.get("status") != "ok" for call in calls),
            "cost": float(sum(Decimal(str(value)) for value in values)) if all(v is not None for v in values) else None,
            "elapsed_s": sum(call.get("elapsed_s", 0) for call in calls)}
