from bots.util import round_num
from data_access.addresses import shorten_hash
from data_access.contracts.util import bean_to_float, token_to_float

def publish_convert_up_v0_str(order):
    total_convert = bean_to_float(int(order['blueprintData']['totalBeanAmountToConvert']))
    min_gs_bonus = token_to_float(int(order['blueprintData']['grownStalkPerBdvBonusBid']), 10)
    min_price = bean_to_float(int(order['blueprintData']['minPriceToConvertUp']))
    max_price = bean_to_float(int(order['blueprintData']['maxPriceToConvertUp']))
    bean_tip = bean_to_float(int(order['beanTip']))
    amount_funded = bean_to_float(int(order['blueprintData']['cascadeAmountFunded']))
    event_str = (
        f"🖋️🚜 Published Convert Up Order {shorten_hash(order['blueprintHash'])}"
        f"\n> 🔄 ⬆️  Convert to {round_num(total_convert, precision=0, avoid_zero=True)} Pinto"
        f"\n> - 🌱 Grown Stalk bonus per PDV is at least {round_num(min_gs_bonus, precision=2, avoid_zero=True)}"
        f"\n> - Pinto price is between {round_num(min_price, precision=2, avoid_zero=True, incl_dollar=True)} and {round_num(max_price, precision=2, avoid_zero=True, incl_dollar=True)}"
        f"\n> 🤖 Operator tip: {round_num(bean_tip, precision=2, avoid_zero=True)} Pinto"
        f"\n> {round_num(amount_funded, precision=0, avoid_zero=True)} Pinto are currently funding this order"
    )
    return event_str

def cancel_convert_up_v0_str(order):
    total_convert = bean_to_float(int(order['blueprintData']['totalBeanAmountToConvert']))
    min_gs_bonus = token_to_float(int(order['blueprintData']['grownStalkPerBdvBonusBid']), 10)
    min_price = bean_to_float(int(order['blueprintData']['minPriceToConvertUp']))
    max_price = bean_to_float(int(order['blueprintData']['maxPriceToConvertUp']))
    bean_tip = bean_to_float(int(order['beanTip']))
    event_str = (
        f"❌🚜 Cancelled Convert Up Order {shorten_hash(order['blueprintHash'])}"
        f"\n> 🔄 ⬆️  Convert to {round_num(total_convert, precision=0, avoid_zero=True)} Pinto"
        f"\n> - 🌱 Grown Stalk bonus per PDV is at least {round_num(min_gs_bonus, precision=2, avoid_zero=True)}"
        f"\n> - Pinto price is between {round_num(min_price, precision=2, avoid_zero=True, incl_dollar=True)} and {round_num(max_price, precision=2, avoid_zero=True, incl_dollar=True)}"
        f"\n> 🤖 Operator tip: {round_num(bean_tip, precision=2, avoid_zero=True)} Pinto"
        f"\n> 🤖 Order was executed {order['executionStats']['executionCount']} time{'' if order['executionStats']['executionCount'] == 1 else 's'}"
    )
    return event_str

def execute_convert_up_v0_str(execution, order):
    beans = bean_to_float(int(execution['blueprintData']['beans']))
    pods = pods_to_float(int(execution['blueprintData']['pods']))
    temperature = (pods / beans - 1) * 100
    bean_tip = bean_to_float(int(order['beanTip']))
    profit = execution['tipUsd'] - execution['gasCostUsd']
    event_str = (
        f"💥🚜 Executed Sow Order {shorten_hash(order['blueprintHash'])}"
        f"\n> {round_num(beans, precision=0, avoid_zero=True)} Pinto Sown at {round_num(temperature, precision=2, avoid_zero=True)}% Temperature for {round_num(pods, precision=0, avoid_zero=True)} Pods"
        f"\n> 🤖 Operator received {round_num(bean_tip, precision=2, avoid_zero=True)} Pinto"
        f" and spent ~{round_num(execution['gasCostUsd'], precision=3, incl_dollar=True)} in gas"
        f" ({'+' if profit > 0 else ''}{round_num(profit, precision=2, incl_dollar=True)})"
    )
    if not order['blueprintData']['orderComplete']:
        remaining_sow = bean_to_float(int(order['blueprintData']['totalAmountToSow']) - int(order['blueprintData']['pintoSownCounter']))
        amount_funded = bean_to_float(int(order['blueprintData']['cascadeAmountFunded']))
        event_str += (
            f"\n> 🌱 Order can sow :PINTO: {round_num(remaining_sow, precision=0, avoid_zero=True)} more !Pinto"
            f"\n> {round_num(amount_funded, precision=0, avoid_zero=True)} Pinto are currently funding this order"
        )
    else:
        pinto_sown = bean_to_float(int(order['blueprintData']['pintoSownCounter']))
        event_str += f"\n> ✅ Order is fulfilled after sowing {round_num(pinto_sown, precision=0, avoid_zero=True)} Pinto"
    event_str += f"\n> 🤖 Order has been executed {int(execution['nonce']) + 1} time{'' if int(execution['nonce']) + 1 == 1 else 's'}"
    return event_str