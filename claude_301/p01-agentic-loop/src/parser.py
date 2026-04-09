import re

def parse_csv_line(line):
    return [field.strip() for field in line.split(",")]

def parse_key_value(line, sep="="):
    if sep not in line:
        return None, None
    key, _, value = line.partition(sep)
    return key.strip(), value.strip()

def parse_headers(raw):
    headers = {}
    for line in raw.strip().splitlines():
        k, v = parse_key_value(line, ":")
        if k:
            headers[k.lower()] = v
    return headers

def extract_emails(text):
    return re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)

def extract_urls(text):
    return re.findall(r"https?://[^\s]+", text)

def extract_numbers(text):
    return [float(x) for x in re.findall(r"-?\d+\.?\d*", text)]

def slugify(text):
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text

def truncate(text, max_len=100, suffix="..."):
    if len(text) <= max_len:
        return text
    return text[:max_len - len(suffix)] + suffix

def normalize_whitespace(text):
    return re.sub(r"\s+", " ", text).strip()

def split_sentences(text):
    return re.split(r"(?<=[.!?])\s+", text.strip())

def count_words(text):
    return len(text.split())

def count_chars(text, include_spaces=True):
    if include_spaces:
        return len(text)
    return len(text.replace(" ", ""))
