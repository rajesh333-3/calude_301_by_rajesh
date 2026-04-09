import json
import os

class SimpleDB:
    def __init__(self, filepath):
        self.filepath = filepath
        self._data = {}
        self._load()

    def _load(self):
        if os.path.exists(self.filepath):
            with open(self.filepath) as f:
                self._data = json.load(f)

    def _save(self):
        with open(self.filepath, "w") as f:
            json.dump(self._data, f, indent=2)

    def set(self, key, value):
        self._data[key] = value
        self._save()

    def get(self, key, default=None):
        return self._data.get(key, default)

    def delete(self, key):
        if key in self._data:
            del self._data[key]
            self._save()
            return True
        return False

    def all(self):
        return dict(self._data)

    def keys(self):
        return list(self._data.keys())

    def values(self):
        return list(self._data.values())

    def exists(self, key):
        return key in self._data

    def count(self):
        return len(self._data)

    def clear(self):
        self._data = {}
        self._save()

    def update(self, mapping):
        self._data.update(mapping)
        self._save()

    def find(self, predicate):
        return {k: v for k, v in self._data.items() if predicate(k, v)}

    def find_by_value(self, field, value):
        results = {}
        for k, v in self._data.items():
            if isinstance(v, dict) and v.get(field) == value:
                results[k] = v
        return results

    def increment(self, key, amount=1):
        current = self._data.get(key, 0)
        self._data[key] = current + amount
        self._save()
        return self._data[key]

    def append_to_list(self, key, item):
        if key not in self._data:
            self._data[key] = []
        if not isinstance(self._data[key], list):
            raise ValueError(f"Key '{key}' is not a list")
        self._data[key].append(item)
        self._save()

    def remove_from_list(self, key, item):
        if key in self._data and isinstance(self._data[key], list):
            self._data[key] = [x for x in self._data[key] if x != item]
            self._save()

    def dump(self):
        return json.dumps(self._data, indent=2)

    def __len__(self):
        return len(self._data)

    def __contains__(self, key):
        return key in self._data

    def __repr__(self):
        return f"SimpleDB({self.filepath!r}, {len(self._data)} entries)"
