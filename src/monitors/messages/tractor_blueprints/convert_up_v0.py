from bots.util import round_num
from data_access.addresses import shorten_hash
from data_access.contracts.util import bean_to_float, stalk_to_float, token_to_float
from monitors.messages.tractor_blueprints.shared import lp_icon_str_from_source_token_indices, lp_icon_str_from_used_tokens

def publish_convert_up_v0_str(order):
    total_convert = bean_to_float(int(order['blueprintData']['totalBeanAmountToConvert']))
    lp_token_icons = lp_icon_str_from_source_token_indices(order['blueprintData']['sourceTokenIndices'])
    min_gs_bonus = token_to_float(int(order['blueprintData']['grownStalkPerBdvBonusBid']), 10)
    min_price = bean_to_float(int(order['blueprintData']['minPriceToConvertUp']))
    max_price = bean_to_float(int(order['blueprintData']['maxPriceToConvertUp']))
    bean_tip = bean_to_float(int(order['beanTip']))
    amount_funded = bean_to_float(int(order['blueprintData']['cascadeAmountFunded']))
    event_str = (
        f"🖋️🚜 Published Convert Up Order {shorten_hash(order['blueprintHash'])}"
        f"\n> 🔄 ⬆️ Convert {lp_token_icons} LP to {round_num(total_convert, precision=0, avoid_zero=True)} Pinto"
        f"\n> - 🌱 Grown Stalk bonus per PDV is at least {round_num(min_gs_bonus, precision=2, avoid_zero=True)}"
        f"\n> - Pinto price is between {round_num(min_price, precision=2, avoid_zero=True, incl_dollar=True)} and {round_num(max_price, precision=2, avoid_zero=True, incl_dollar=True)}"
        f"\n> 🤖 Operator tip: {round_num(bean_tip, precision=2, avoid_zero=True)} Pinto"
        f"\n> {round_num(amount_funded, precision=0, avoid_zero=True)} Pinto are currently funding this order"
    )
    return event_str

def cancel_convert_up_v0_str(order):
    total_convert = bean_to_float(int(order['blueprintData']['totalBeanAmountToConvert']))
    lp_token_icons = lp_icon_str_from_source_token_indices(order['blueprintData']['sourceTokenIndices'])
    min_gs_bonus = token_to_float(int(order['blueprintData']['grownStalkPerBdvBonusBid']), 10)
    min_price = bean_to_float(int(order['blueprintData']['minPriceToConvertUp']))
    max_price = bean_to_float(int(order['blueprintData']['maxPriceToConvertUp']))
    bean_tip = bean_to_float(int(order['beanTip']))
    event_str = (
        f"❌🚜 Cancelled Convert Up Order {shorten_hash(order['blueprintHash'])}"
        f"\n> 🔄 ⬆️ Convert {lp_token_icons} LP to {round_num(total_convert, precision=0, avoid_zero=True)} Pinto"
        f"\n> - 🌱 Grown Stalk bonus per PDV is at least {round_num(min_gs_bonus, precision=2, avoid_zero=True)}"
        f"\n> - Pinto price is between {round_num(min_price, precision=2, avoid_zero=True, incl_dollar=True)} and {round_num(max_price, precision=2, avoid_zero=True, incl_dollar=True)}"
        f"\n> 🤖 Operator tip: {round_num(bean_tip, precision=2, avoid_zero=True)} Pinto"
        f"\n> 🤖 Order was executed {order['executionStats']['executionCount']} time{'' if order['executionStats']['executionCount'] == 1 else 's'}"
    )
    return event_str

def execute_convert_up_v0_str(execution, order):
    beans_converted = bean_to_float(int(execution['blueprintData']['beansConverted']))
    used_lp_token_icons = lp_icon_str_from_used_tokens(execution['blueprintData']['usedTokens'])
    price_before = execution['blueprintData']['beanPriceBefore']
    price_after = execution['blueprintData']['beanPriceAfter']
    gs_bonus_stalk = stalk_to_float(int(execution['blueprintData']['gsBonusStalk']))
    gs_bonus_bdv = bean_to_float(int(execution['blueprintData']['gsBonusBdv']))
    gs_bonus_per_bdv = gs_bonus_stalk / gs_bonus_bdv

    bean_tip = bean_to_float(int(order['beanTip']))
    profit = execution['tipUsd'] - execution['gasCostUsd']

    event_str = (
        f"💥🚜 Executed Convert Up Order {shorten_hash(order['blueprintHash'])}"
        f"\n> 🔄 ⬆️ Converted {used_lp_token_icons} LP to {round_num(beans_converted, precision=0, avoid_zero=True)} Pinto"
        f"\n> - 🌱 Awarded {round_num(gs_bonus_stalk, precision=2, avoid_zero=True)} Grown Stalk bonus "
        f"({round_num(gs_bonus_per_bdv, precision=3, avoid_zero=True)} per PDV) to {round_num(gs_bonus_bdv, precision=2, avoid_zero=True)} PDV"

        f"\n> - Pinto price increased from {round_num(price_before, precision=4, avoid_zero=True, incl_dollar=True)} to {round_num(price_after, precision=4, avoid_zero=True, incl_dollar=True)}"
        f"\n> 🤖 Operator received {round_num(bean_tip, precision=2, avoid_zero=True)} Pinto"
        f" and spent ~{round_num(execution['gasCostUsd'], precision=3, incl_dollar=True)} in gas"
        f" ({'+' if profit > 0 else ''}{round_num(profit, precision=2, incl_dollar=True)})"
    )
    if not order['blueprintData']['orderComplete']:
        remaining_convert = bean_to_float(int(order['blueprintData']['beansLeftToConvert']))
        amount_funded = bean_to_float(int(order['blueprintData']['cascadeAmountFunded']))
        event_str += (
            f"\n> 🌱 Order can Convert up :PINTO: {round_num(remaining_convert, precision=0, avoid_zero=True)} more !Pinto"
            f"\n> {round_num(amount_funded, precision=0, avoid_zero=True)} Pinto are currently funding this order"
        )
    else:
        pinto_converted = bean_to_float(int(order['blueprintData']['totalBeanAmountToConvert']) - int(order['blueprintData']['beansLeftToConvert']))
        event_str += f"\n> ✅ Order is fulfilled after Converting up {round_num(pinto_converted, precision=0, avoid_zero=True)} Pinto"
    event_str += f"\n> 🤖 Order has been executed {int(execution['nonce']) + 1} time{'' if int(execution['nonce']) + 1 == 1 else 's'}"
    return event_str