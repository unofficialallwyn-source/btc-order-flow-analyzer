"""Price-direction vs aggressive volume-delta interpretation.

Both inputs use the same rolling trade-tape window. These interpretations are
heuristic; absorption requires additional order-book or footprint evidence.
"""
def interpret_trade_window(trades, stable_threshold_pct=0.05):
    if len(trades)<2:
        return {"state":"insufficient","message":"Waiting for at least two trades in the selected window."}
    ordered=sorted(trades,key=lambda t:t["timestamp"])
    start=float(ordered[0]["price"])
    end=float(ordered[-1]["price"])
    if start<=0:
        return {"state":"insufficient","message":"Invalid start price."}
    delta=sum(float(t["size"])*(1 if t["side"]=="buy" else -1) for t in ordered)
    change=(end-start)/start*100
    if abs(delta)<1e-9:
        return {"state":"insufficient","message":"Trade delta is balanced; no dominant aggression."}
    direction="rising" if change>stable_threshold_pct else ("falling" if change< -stable_threshold_pct else "stagnant")
    if delta<0 and direction=="falling":
        state,title,msg="selling_pressure","Negative delta + falling price","Selling aggression is moving price lower."
    elif delta<0:
        state,title,msg="buyer_absorption","Negative delta + stable or rising price","Buyers may be absorbing sell orders."
    elif direction=="rising":
        state,title,msg="buying_pressure","Positive delta + rising price","Buying aggression is moving price higher."
    else:
        state,title,msg="seller_absorption","Positive delta + falling or stagnant price","Sellers may be absorbing buy orders."
    return {"state":state,"title":title,"message":msg,"net_delta":delta,"price_change_pct":change}
