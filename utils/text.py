_pairs = {
    # a
    'à':'a','á':'a','ả':'a','ã':'a','ạ':'a',
    'ă':'a','ắ':'a','ặ':'a','ằ':'a','ẳ':'a','ẵ':'a',
    'â':'a','ấ':'a','ậ':'a','ầ':'a','ẩ':'a','ẫ':'a',
    # e
    'è':'e','é':'e','ẻ':'e','ẽ':'e','ẹ':'e',
    'ê':'e','ế':'e','ệ':'e','ề':'e','ể':'e','ễ':'e',
    # i
    'ì':'i','í':'i','ỉ':'i','ĩ':'i','ị':'i',
    # o
    'ò':'o','ó':'o','ỏ':'o','õ':'o','ọ':'o',
    'ô':'o','ố':'o','ộ':'o','ồ':'o','ổ':'o','ỗ':'o',
    'ơ':'o','ớ':'o','ợ':'o','ờ':'o','ở':'o','ỡ':'o',
    # u
    'ù':'u','ú':'u','ủ':'u','ũ':'u','ụ':'u',
    'ư':'u','ứ':'u','ự':'u','ừ':'u','ử':'u','ữ':'u',
    # y
    'ỳ':'y','ý':'y','ỷ':'y','ỹ':'y','ỵ':'y',
    # d
    'đ':'d',
}

# Add uppercase variants before building the translation table
_pairs.update({k.upper(): v for k, v in _pairs.items()})

_VN_MAP = str.maketrans(_pairs)


def normalize_vn(text: str) -> str:
    """Strip Vietnamese diacritics and lowercase. 'Mưa' → 'mua', 'Đường' → 'duong'."""
    return text.translate(_VN_MAP).lower()