# target6.py
def check(a: bool, b: bool, c: bool) -> None:
    if (a and b) or c:
        print("yes")

check(True, True, False)   # (T∧T)∨F = True
check(True, False, False)  # (T∧F)∨F = False
check(False, False, True)  # (F∧F)∨T = True
check(False, False, False) # (F∧F)∨F = False