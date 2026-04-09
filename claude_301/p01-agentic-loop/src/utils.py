def add(a, b): return a + b
def subtract(a, b): return a - b
def multiply(a, b): return a * b
def divide(a, b): return a / b if b != 0 else None
def square(x): return x * x
def cube(x): return x * x * x
def is_even(n): return n % 2 == 0
def is_odd(n): return n % 2 != 0
def clamp(val, lo, hi): return max(lo, min(hi, val))
def average(nums): return sum(nums) / len(nums) if nums else 0
