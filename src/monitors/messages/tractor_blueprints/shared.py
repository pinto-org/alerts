from constants.config import SILO_TOKENS_MAP, SOURCE_TOKEN_INDEX_MAPPING, WHITELISTED_WELLS

def lp_icon_str_from_source_token_indices(source_token_indices):
    if source_token_indices[0] >= 254:
        # 254/255 are the lowest seed/price sorting strategies, supports all tokens
        return " ".join([f":{SILO_TOKENS_MAP[well.lower()].upper()}:" for well in WHITELISTED_WELLS])
    # Return the actual tokens used
    return " ".join([f":{SILO_TOKENS_MAP[SOURCE_TOKEN_INDEX_MAPPING[index].lower()].upper()}:" for index in source_token_indices])

def lp_icon_str_from_used_tokens(used_tokens):
    return " ".join([f":{SILO_TOKENS_MAP[token.lower()].upper()}:" for token in used_tokens])
