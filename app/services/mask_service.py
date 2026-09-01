"""Auto-mask business names and phone numbers in anonymous community text (spec 2-8)."""
import re

PHONE_RE = re.compile(r"(?<!\d)(01[016789]|02|0[3-6]\d|070|080|050\d?)[-.\s]?\d{3,4}[-.\s]?\d{4}(?!\d)")
BIZ_SUFFIX = "치과|의원|병원|피부과|한의원|성형외과|안과|정형외과|내과|약국|스토어|학원|헬스장|필라테스|미용실|네일샵|펜션|호텔|모텔|카페|식당|갈비|본점|지점|점"
BIZ_RE = re.compile(rf"([가-힣A-Za-z0-9]{{2,12}})({BIZ_SUFFIX})(?![가-힣])")
CORP_RE = re.compile(r"(\(주\)|㈜|주식회사)\s?[가-힣A-Za-z0-9]{2,12}")
URL_RE = re.compile(r"https?://\S+")


def mask(text):
    if not text:
        return text
    text = PHONE_RE.sub(lambda m: m.group(0)[:3] + "-****-****", text)
    text = CORP_RE.sub(lambda m: m.group(1) + "○○", text)
    text = BIZ_RE.sub(lambda m: "○" * min(len(m.group(1)), 3) + m.group(2), text)
    return text
